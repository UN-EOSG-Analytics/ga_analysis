"""One entry point: review -> discover -> classify -> aggregate -> report."""
from pathlib import Path
from contextlib import contextmanager
from collections import Counter
import importlib
import importlib.metadata
import json
import shutil
import os
from datetime import datetime,timezone

from ..io import read_jsonl,digest,stable_hash,write_jsonl
from ..pipeline import config
from ..contracts import validate_manifest
from .common import key_from_env,save,table,now
from .aggregation import coverage_guard,aggregate

STAGES=['review','discover','classify','aggregate','report']
DEPENDENCIES={'openai':'openai','numpy':'numpy','scipy':'scipy','scikit-learn':'sklearn',
              'python-docx':'docx','matplotlib':'matplotlib','PyMuPDF':'fitz','reportlab':'reportlab'}


@contextmanager
def execution_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another analysis process is using this workspace') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def inputs(root,cfg):
    manifest=validate_manifest(list(read_jsonl(root/cfg['source_manifest'])))
    selected={r['source_id']:r for r in manifest if r['status']=='accepted' and r['representative']}
    rows=list(read_jsonl(root/cfg['output_directory']/'speeches.jsonl'))
    if len(rows)!=len(selected) or {r['source_id'] for r in rows}!=set(selected) or len({r['speech_id'] for r in rows})!=len(rows):
        raise ValueError('Active analysis input must have one selected source per country-year')
    for r in rows:
        if r['sha256']!=selected[r['source_id']]['sha256'] or r['source_type'] not in ('official_transcript','automatic_transcript'):
            raise ValueError('Stale input or submitted-PDF observation in canonical input')
    counts=Counter(str(r['year']) for r in rows)
    for year,minimum in cfg['sources'].get('minimum_expected_speeches',{}).items():
        if counts[year]<minimum:raise ValueError(f'Active input is below confirmed holdings for {year}')
    return rows


def preflight(root,allow_partial=False):
    root=Path(root).resolve();cfg=config(root);rows=inputs(root,cfg)
    packages={};problems=[]
    for package,module in DEPENDENCIES.items():
        try:
            importlib.import_module(module)
            packages[package]=importlib.metadata.version(package)
        except (ImportError,importlib.metadata.PackageNotFoundError) as exc:
            packages[package]='missing';problems.append('Missing dependency: '+package)
    api_key_present=bool(key_from_env(root,cfg['discovery']['api_key_env']))
    if not api_key_present:problems.append('OPENAI_API_KEY missing from .env/environment')
    access_path=root/'output/diagnostics/model_access.json'
    access=json.loads(access_path.read_text(encoding='utf-8')) if access_path.exists() else {}
    recent=False
    if access.get('checked_at'):
        stamp=datetime.fromisoformat(access['checked_at'])
        recent=(datetime.now(timezone.utc)-stamp).total_seconds()<86400
        if (root/'.env').exists() and (root/'.env').stat().st_mtime>stamp.timestamp():recent=False
    subscription=cfg['execution'].get('text_backend')=='codex_subscription'
    models=[cfg['discovery']['model']] if subscription else [cfg['discovery']['model'],cfg['execution']['review_model']]
    access_ok=recent and all(access.get('models',{}).get(model,{}).get('accessible') for model in models)
    coverage=coverage_guard(rows,cfg,allow_partial=True)
    partial=[int(y) for y,v in coverage.items() if v['partial']]
    source_dir=root/'data/unga_general_debate_verbatim_en/automatic_transcripts_unofficial'
    raw_day6=list(source_dir.glob('UNGA2026_day6_EN_ASR.*'))
    active_origins={r.get('origin_file') for r in rows}
    unprocessed=[p.relative_to(root).as_posix() for p in raw_day6 if p.suffix in ('.txt','.json') and p.relative_to(root).as_posix() not in active_origins]
    from .costs import estimate_costs
    costs=estimate_costs(root,rows,cfg)
    rough_review=min(v['lower_usd'] for v in costs['stages']['review']['scenarios'].values())
    result=dict(checked_at_utc=now(),workflow_implemented=True,dependencies=packages,api_key_present=api_key_present,
        text_backend=cfg['execution'].get('text_backend','openai_api'),api_scope=cfg['execution'].get('api_scope','embeddings_only'),
        subscription_session_required=subscription,subscription_model_preference=cfg['execution'].get('subscription_model_preference'),
        api_access_verified=bool(access_ok),api_verification_scope='Model metadata access only; no paid inference',
        paid_inference_verified=False,problems=problems,ready_for_execution=not problems and (not partial or allow_partial),
        ready_after_final_day=not problems,partial_years=partial,coverage=coverage,day6_files_awaiting_preparation=unprocessed,
        speeches=len(rows),passages=sum(len(r['passages']) for r in rows),stages=STAGES,
        corpus_sha256=digest(root/cfg['output_directory']/'speeches.jsonl'),
        review_all_speeches=True,estimated_review_cost_usd=round(rough_review,2),
        cost_estimate=costs,estimate_scope=costs['scope'],
        estimated_total_exceeds_default_cap=costs['upper_usd']>cfg['execution']['default_cost_limit_usd'],
        default_cost_limit_usd=cfg['execution']['default_cost_limit_usd'],paid_calls_performed=0,
        price_date=cfg['execution']['pricing_checked'],code_only_validation='Actual API/model/account availability requires an authorized live run.')
    save(root/'output/workflow_readiness.json',result)
    return result


def receive_final_day(root,path):
    path=Path(path).resolve(strict=True)
    if path.suffix.lower() not in ('.txt','.json'):raise ValueError('Day 6 must be an English transcript TXT or JSON')
    destination=root/'data/unga_general_debate_verbatim_en/automatic_transcripts_unofficial'/('UNGA2026_day6_EN_ASR'+path.suffix.lower())
    destination=destination.resolve()
    if not destination.is_relative_to(root):raise ValueError('Final-day destination leaves workspace')
    if destination.exists() and digest(destination)!=digest(path):raise ValueError('A different immutable Day 6 source already exists; resolve the source version first')
    if destination!=path and not destination.exists():
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
    return destination


def run(root,execute=False,budget=None,allow_partial=False,final_day=None,stop_after='report',provider=None,fetch_current=True):
    root=Path(root).resolve();cfg=config(root)
    if stop_after not in STAGES:raise ValueError('Unknown analysis stage')
    if not execute:return preflight(root,allow_partial)
    base=root/cfg['execution']['output_directory'];base.mkdir(parents=True,exist_ok=True)
    with execution_lock(base/'execution.lock'):
        if final_day:receive_final_day(root,final_day)
        readiness=preflight(root,allow_partial)
        if readiness['day6_files_awaiting_preparation']:
            from ..preparation.publish import prepare
            prepare(root)
            readiness=preflight(root,allow_partial)
        if readiness['problems'] and provider is None:raise ValueError('; '.join(readiness['problems']))
        speeches=inputs(root,cfg)
        coverage_guard(speeches,cfg,allow_partial)
        fingerprint=stable_hash(dict(input_sha256=digest(root/cfg['output_directory']/'speeches.jsonl'),
            discovery=cfg['discovery'],classification=cfg['classification'],execution={k:v for k,v in cfg['execution'].items() if k not in ('default_cost_limit_usd','workers')},
            code={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},allow_partial=allow_partial))[:16]
        out=base/'runs'/fingerprint;out.mkdir(parents=True,exist_ok=True)
        if provider is None:
            if cfg['execution'].get('text_backend')=='codex_subscription':
                from .subscription import SubscriptionProvider
                provider=SubscriptionProvider(root,cfg,budget=budget)
            else:
                if cfg['execution'].get('api_scope')!='text_and_embeddings':raise ValueError('Text API is disabled; select codex_subscription')
                from .provider import OpenAIProvider
                provider=OpenAIProvider(root,cfg,execute=True,budget=budget)
        initial_spend=getattr(provider,'used',0.0)
        save(out/'run.json',dict(run_id=fingerprint,started_at=now(),state='running',stop_after=stop_after,allow_partial=allow_partial,
             input_sha256=digest(root/cfg['output_directory']/'speeches.jsonl'),models={'review':cfg['execution'].get('text_backend','openai_api'),'embedding':cfg['discovery']['model']},human_reviewed=False))
        def finish(stage,extra=None):
            costs=dict(new_run_charged_or_reserved_usd=getattr(provider,'used',0.0)-initial_spend,
                       cumulative_charged_or_reserved_usd=getattr(provider,'used',0.0),
                       limit_usd=getattr(provider,'limit',None),pricing_date=cfg['execution']['pricing_checked'],
                       basis='API-reported tokens at recorded rates; ambiguous transport failures retain reservations; not a billing invoice')
            save(out/'cost_summary.json',costs)
            memo=out/'methodology_and_cost.md'
            if memo.exists():
                with memo.open('a',encoding='utf-8') as handle:
                    handle.write(f"\n\n## 실행 비용\n\n현재 실행 경로의 직접 API 추정: US${readiness['cost_estimate']['lower_usd']:.2f}–${readiness['cost_estimate']['upper_usd']:.2f}. 구독 경로는 임베딩만 API 비용에 포함하며 상세 가정은 cost_estimate.json을 따른다. 보장 상한이 아니다. "
                        f"이번 실행의 정산/예약 증가분: US${costs['new_run_charged_or_reserved_usd']:.4f}. "
                        f"워크스페이스 누적 정산/예약: US${costs['cumulative_charged_or_reserved_usd']:.4f}. "
                        "실제 사용 토큰과 미확정 예약분은 cost_summary.json 및 usage.jsonl 참조. 청구서 금액으로 확정한 값은 아니다.\n")
            result=dict(run_id=fingerprint,completed_stage=stage,state='complete' if stage=='report' else 'stage_complete',
                        output=str(out),usage_ledger=str(base/'api_cache/usage.jsonl'),costs=costs,human_reviewed=False,**(extra or {}))
            save(out/'run.json',result);save(base/'latest.json',result)
            return result
        try:
            from .review import review_all,ai_chunks
            reviewed=review_all(speeches,provider,cfg,out)
            if stop_after=='review':return finish('review')
            chunks,duplicates=ai_chunks(speeches,reviewed)
            write_jsonl(out/'discovery_chunks.jsonl',chunks);table(out/'discovery_duplicates.csv',duplicates)
            from .discovery import discover
            taxonomy,membership=discover(chunks,provider,cfg,out)
            # Discovery-only deduplication never removes a passage from classification.
            for row in duplicates:membership[row['passage_id']]=membership.get(row['representative_passage_id'])
            save(root/'config/theme_taxonomy.json',taxonomy)
            if stop_after=='discover':return finish('discover')
            from .classification import classify_all
            classified=classify_all(reviewed,taxonomy,membership,provider,cfg,out)
            if stop_after=='classify':return finish('classify')
            stats,evidence,institutions,matrix=aggregate(speeches,reviewed,classified,taxonomy,cfg,out,allow_partial)
            ancillary(root,out,speeches,reviewed,classified,taxonomy,stats,readiness,cfg)
            if stop_after=='aggregate':return finish('aggregate')
            from .references import reference_blocks,summarize_references
            blocks,inventory=reference_blocks(root,out,fetch_current=fetch_current)
            facts=summarize_references(blocks,provider,out)
            from .reporting import draft_report,charts,pages,render
            content=draft_report(stats,evidence,institutions,taxonomy,facts,provider,out)
            destination=root/'deliverables'/fingerprint;destination.mkdir(parents=True,exist_ok=True)
            figures=charts(stats,destination)
            publication=render(pages(content,stats,institutions,facts,inventory,figures),destination,cfg['report']['basename'],use_word=cfg['report'].get('render_with_word',True))
            save(destination/'publication_checks.json',publication)
            save(root/'deliverables/latest.json',dict(run_id=fingerprint,**publication,evidence_directory=str(out)))
            return finish('report',dict(publication=publication,coverage=stats['coverage']))
        except Exception as exc:
            from .subscription import AwaitingSubscriptionWork
            if isinstance(exc,AwaitingSubscriptionWork):
                result=dict(run_id=fingerprint,state='awaiting_subscription_review',output=str(out),
                    pending=list(provider.pending.values()),text_api_calls=0,subscription_session_required=True,
                    cumulative_api_charged_or_reserved_usd=provider.used,
                    resume='Codex reads each request, saves a response envelope with actual model metadata, and repeats the command. No automatic text API fallback.')
                save(out/'run.json',result);save(base/'latest.json',result)
                return result
            save(out/'run.json',dict(run_id=fingerprint,state='stopped',exception_type=type(exc).__name__,message=str(exc),
                 resume='Repeat the same command; exact model requests and vectors are cached. Input changes create a new run.',updated_at=now()))
            raise


def ancillary(root,out,speeches,reviewed,classified,taxonomy,stats,readiness,cfg):
    table(out/'source_inventory.csv',[{k:s.get(k) for k in ('speech_id','year','country_iso3','analytical_group','source_type','text_accuracy','path','sha256','origin_file','origin_sha256','speech_date')} for s in speeches])
    issues=[dict(speech_id=r['speech_id'],passage_id=r['passage_id'],issue='AI review uncertain') for r in reviewed if r['ai_status']=='Uncertain']
    issues.extend(dict(speech_id=r['speech_id'],passage_id=r['passage_id'],issue='Theme, keyword, uncovered-concept or source-note review unresolved') for r in classified if not r['classification_complete'] or not r['keyword_review_complete'])
    issues.extend(dict(speech_id=r['speech_id'],passage_id=r['passage_id'],issue='Uncovered concept: '+concept) for r in classified for concept in r.get('uncovered_concepts',[]))
    issues.extend(dict(speech_id=s['speech_id'],passage_id='',issue='Prepared-versus-delivered source note awaits delivery verification') for s in speeches if (s.get('source_review_notes') or {}).get('status')=='pending_delivery_verification')
    table(out/'review_queue.csv',issues)
    missing=root/'output/corpus_preparation/missing_country_years.csv'
    if missing.exists():shutil.copy2(missing,out/'missing_country_years.csv')
    text=['# Missing or uncertain sources','',f"Obtained speeches: {len(speeches)}. Unresolved analytical items: {len(issues)}.",
          'Unrepresented country-years are not automatically missing files or AI negatives. Participation rosters have not been independently reconciled.',
          'English editions retain the four previously documented non-English greetings/quotations. ASR accuracy is unverified.',
          'See review_queue.csv, source_inventory.csv and the project source-review notes.']
    (out/'missing_or_uncertain_sources.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')
    lines=['# Common theme taxonomy','',f"Version: {taxonomy['version']}; automated source review, not human approval."]
    for code,t in taxonomy['codes'].items():
        lines += [f"## {code}: {t['label']}",t['definition'],'Include: '+t['inclusion'],'Exclude: '+t['exclusion'],'Boundary cases: '+t['boundary_cases'],json.dumps(t['examples'],ensure_ascii=False)]
    (out/'theme_taxonomy.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    memo=['# 방법과 비용', '',
        '전사 DB를 변경하지 않고 국가–연도 단위로 분석했다. 전체 연설 텍스트를 두 번 자동 검토하며 검색 미적중을 자동 No로 채우지 않는다. 판정 불일치는 Uncertain이다.',
        f"문맥·분류·보고서 실행 경로: {cfg['execution'].get('text_backend','openai_api')}. 구독 경로의 실제 모델은 subscription_queue 응답별 reviewer 메타데이터에 기록한다. 임베딩: {cfg['discovery']['model']}, {cfg['discovery']['dimensions']}차원.",
        '임베딩은 AI Yes 구절과 필요한 문맥에만 적용한다. 로컬 평균 중심화·cosine 거리·average linkage를 사용하고 여러 절단과 군집별 대표/경계 구절을 검토해 공통 taxonomy를 만든다. 군집 ID를 최종 주제값으로 쓰지 않는다.',
        '분류는 구절별 복수 판정이며 국가–연도·코드별 OR로 집계한다. 해당 코드에 Yes가 있으면 1, AI 검토가 완료되고 모든 AI 구절에서 해당 코드가 No이면 0, 그 밖에는 NA이다. 주제별 N은 AI 양성 국가 중 해당 코드가 확정된 국가 수이며 공동 언급은 두 코드가 모두 확정된 국가를 분모로 한다. 같은 국가의 연도 비교도 코드별 공통 표본을 사용한다. 미검토·미확보를 0으로 바꾸지 않는다. 새 개념은 검토 대기표에 남기며 기존 코드의 분류 완료를 막지 않는다. 지역은 고정 UN 매핑을 사용한다.',
        '동일 모델의 별도 호출은 자동 재검토이며 사람 간 일치도가 아니다. 원음 검증과 인간 검토 완료를 주장하지 않는다. 자동 검토 보고서는 이 한계를 표시한다.',
        f"사용량·비용 원장: {cfg['execution']['output_directory']}/api_cache/usage.jsonl. 실제 응답 토큰 사용량에 기록된 단가를 적용한다. 불명확한 전송 실패는 비용 예약분을 유지한다. 단가 확인일: {cfg['execution']['pricing_checked']}.",
        '무임베딩 방식은 가능하나 별도 주제 발견 절차가 필요하며, 이전 MiniLM 결과는 재사용하지 않는다. 이번 경로는 사용자가 지정한 OpenAI 임베딩과 근거 검토를 연결한다.',
        '원문·프롬프트·모델·taxonomy가 바뀌면 관련 캐시 키가 바뀐다. Word와 PDF는 같은 내용으로 생성하며 PDF 페이지 경계와 섹션을 검사한다. Word의 실제 렌더링 검증 여부는 publication_checks.json을 따른다.']
    (out/'methodology_and_cost.md').write_text('\n\n'.join(memo)+'\n',encoding='utf-8')
    save(out/'environment.json',readiness['dependencies'])
    if 'cost_estimate' in readiness:save(out/'cost_estimate.json',readiness['cost_estimate'])
    save(out/'analysis_config.json',cfg)
