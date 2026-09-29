"""One entry point: review -> discover -> classify -> aggregate -> report."""
from pathlib import Path
from contextlib import contextmanager
from collections import Counter
import importlib
import importlib.metadata
import json
import shutil
import os
import re
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
    for path in raw_day6:
        if path.suffix in ('.txt','.json'):
            try:validate_final_day(path)
            except ValueError as exc:problems.append(str(exc))
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
        ready_after_final_day=not problems,readiness_scope='Offline implementation/dependency checks; source ingestion and actual subscription execution remain required',
        blockers=problems+([f'Validated final-day sources missing for years {partial}'] if partial and not allow_partial else []),
        partial_years=partial,coverage=coverage,day6_files_awaiting_preparation=unprocessed,
        speeches=len(rows),passages=sum(len(r['passages']) for r in rows),stages=STAGES,
        corpus_sha256=digest(root/cfg['output_directory']/'speeches.jsonl'),
        review_all_speeches=costs['measured']['review_unselected_speeches']==0,review_scope=cfg.get('review',{}),
        estimated_review_cost_usd=round(rough_review,2),
        cost_estimate=costs,estimate_scope=costs['scope'],
        estimated_total_exceeds_default_cap=costs['upper_usd']>cfg['execution']['default_cost_limit_usd'],
        default_cost_limit_usd=cfg['execution']['default_cost_limit_usd'],paid_calls_performed=0,
        price_date=cfg['execution']['pricing_checked'],code_only_validation='Actual API/model/account availability requires an authorized live run.')
    save(root/'output/workflow_readiness.json',result)
    return result


def validate_final_day(path,year=2026):
    path=Path(path)
    if path.suffix.lower() not in ('.txt','.json'):raise ValueError('Day 6 must be an English transcript TXT or JSON')
    text=path.read_text(encoding='utf-8-sig')
    if path.suffix.lower()=='.json':
        value=json.loads(text);video=value.get('video',{});transcript=value.get('transcript',{})
        title=video.get('title','');date=video.get('date','');language=transcript.get('language','')
        identity=' '.join(str(x) for x in [title,video.get('pv_symbol',''),value.get('url','')])
        dates=re.findall(r'\b(20\d{2})-\d{2}-\d{2}',date)
        if not transcript.get('data'):raise ValueError('Day 6 JSON contains no transcript statements')
    else:
        header=text.split('---',1)[0][:2000];title=header
        date=re.search(r'^Date:\s*(.+)$',header,re.M);dates=re.findall(r'\b20\d{2}\b',date.group(1)) if date else []
        language='en' if re.search(r'Language:\s*English',header,re.I) else ''
        identity=header
    sessions=[int(value) for group in re.findall(r'(\d+)(?:st|nd|rd|th) session|A/(\d+)/PV|/ga/(\d+)/',identity) for value in group if value]
    if not dates or any(int(y)!=year for y in dates) or any(s!=year-1945 for s in sessions):
        raise ValueError(f'Day 6 source year/session does not match {year}: dates={dates}, sessions={sessions}; source not ingested')
    if language!='en' or not re.search(r'Day\s*6\b',title,re.I):raise ValueError('Expected an explicitly English Day 6 transcript')
    return dict(year=year,session=year-1945,language=language,sha256=digest(path))


def receive_final_day(root,path):
    root=Path(root).resolve()
    path=Path(path).resolve(strict=True)
    validate_final_day(path)
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
        from .references import reference_files
        fingerprint=stable_hash(dict(input_sha256=digest(root/cfg['output_directory']/'speeches.jsonl'),
            discovery=cfg['discovery'],classification=cfg['classification'],review=cfg.get('review',{}),report=cfg['report'],
            references={p.name:digest(p) for p in reference_files(root)},
            execution={k:v for k,v in cfg['execution'].items() if k not in ('default_cost_limit_usd','workers')},
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
                    handle.write(f"\n\n## Run cost\n\nEstimated direct API cost for the current execution path: US${readiness['cost_estimate']['lower_usd']:.2f}–${readiness['cost_estimate']['upper_usd']:.2f}. On the subscription path only embeddings incur API cost; assumptions are in cost_estimate.json. This is not a guaranteed ceiling. "
                        f"Charged/reserved increase in this run: US${costs['new_run_charged_or_reserved_usd']:.4f}. "
                        f"Cumulative workspace charged/reserved: US${costs['cumulative_charged_or_reserved_usd']:.4f}. "
                        "Actual token usage and unresolved reservations are in cost_summary.json and usage.jsonl. These are not invoiced amounts.\n")
            result=dict(run_id=fingerprint,completed_stage=stage,state='complete' if stage=='report' else 'stage_complete',
                        output=str(out),usage_ledger=str(base/'api_cache/usage.jsonl'),costs=costs,human_reviewed=False,**(extra or {}))
            save(out/'run.json',result);save(base/'latest.json',result)
            return result
        try:
            from .review import review_all,ai_chunks
            from .scope import review_plan
            reviewed=review_all(speeches,provider,cfg,out,review_plan(speeches,cfg,root))
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
            if (out/'reference_blocks.json').exists() and (out/'reference_inventory.json').exists():
                blocks=json.loads((out/'reference_blocks.json').read_text(encoding='utf-8'));inventory=json.loads((out/'reference_inventory.json').read_text(encoding='utf-8'))
            else:blocks,inventory=reference_blocks(root,out,fetch_current=fetch_current)
            facts=summarize_references(blocks,provider,out)
            from .reporting import draft_report,charts,pages,render,source_notes
            content=draft_report(stats,evidence,institutions,taxonomy,facts,provider,out)
            destination=root/'deliverables'/fingerprint;destination.mkdir(parents=True,exist_ok=True)
            figures=charts(stats,destination)
            for attempt in range(3):
                try:
                    publication=render(pages(content,stats,institutions,facts,inventory,figures),destination,cfg['report']['basename'],use_word=cfg['report'].get('render_with_word',True))
                    break
                except ValueError as exc:
                    if 'page' not in str(exc).lower() or attempt==2:raise
                    content=draft_report(stats,evidence,institutions,taxonomy,facts,provider,out,layout_feedback=dict(attempt=attempt+1,reason=str(exc)))
            notes=source_notes(content,destination)
            publication['source_notes']=notes
            save(destination/'publication_checks.json',publication)
            save(root/'deliverables/latest.json',dict(run_id=fingerprint,**publication,evidence_directory=str(out)))
            return finish('report',dict(publication=publication,coverage=stats['coverage']))
        except Exception as exc:
            from .subscription import AwaitingSubscriptionWork
            if isinstance(exc,AwaitingSubscriptionWork):
                result=dict(run_id=fingerprint,state='awaiting_subscription_review',output=str(out),
                    pending=list(provider.pending.values()),pending_count=len(provider.pending),text_api_calls=0,subscription_session_required=True,
                    cumulative_api_charged_or_reserved_usd=provider.used,
                    resume='Codex reads each request, saves a response envelope with actual model metadata, and repeats the command. No automatic text API fallback.')
                save(out/'pending_requests.json',result['pending'])
                result['pending_manifest']=str(out/'pending_requests.json')
                save(out/'run.json',result);save(base/'latest.json',result)
                return result
            save(out/'run.json',dict(run_id=fingerprint,state='stopped',exception_type=type(exc).__name__,message=str(exc),
                 resume='Repeat the same command; exact model requests and vectors are cached. Input changes create a new run.',updated_at=now()))
            raise


def ancillary(root,out,speeches,reviewed,classified,taxonomy,stats,readiness,cfg):
    table(out/'source_inventory.csv',[{k:s.get(k) for k in ('speech_id','year','country_iso3','analytical_group','source_type','text_accuracy','path','sha256','origin_file','origin_sha256','speech_date')} for s in speeches])
    issues=[dict(speech_id=r['speech_id'],passage_id=r['passage_id'],issue='AI review '+r['ai_status']) for r in reviewed if r['ai_status'] in ('Uncertain','Pending')]
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
    memo=['# Methods and cost', '',
        'The analysis uses the country–year as the unit and does not modify the transcript database. Reviewers read the full context of every speech with a search candidate, plus a sample of search-negative speeches stratified by year, region and source. Each selected speech is reviewed automatically once; the negative-audit sample and a fixed hash-selected 10% are reviewed twice. If a sample finds Yes/Uncertain, review expands to that stratum. The actual selection, pass counts and expansions are recorded in review_selection.json. Unreviewed passages stay Pending; disagreements become Uncertain.',
        'While unreviewed speeches remain, the year/region n/N is a lower bound: confirmed AI-positive countries over obtained country speeches. It is not an estimate of the population mention rate and does not treat unreviewed text as No. resolved_N and fully_reviewed are reported separately. Because of search/sampling bias and different review coverage by year, changes in rates are not asserted as policy shifts. Theme shares are computed within detected and reviewed AI-positive speeches and are not generalised to undetected AI remarks.',
        f"Execution path for context review, classification and report: {cfg['execution'].get('text_backend','openai_api')}. On the subscription path the actual model is recorded in the reviewer metadata of each subscription_queue response. Embeddings: {cfg['discovery']['model']}, {cfg['discovery']['dimensions']} dimensions.",
        'Embeddings are applied only to AI-Yes passages and required context. Local mean-centring, cosine distance and average linkage are used; several cut levels and representative/boundary passages per cluster are reviewed to build a common taxonomy. Cluster IDs are never used as final theme values.',
        'Classification is multi-label per passage and aggregated per country–year and code with OR. A code is 1 if any passage is Yes; 0 if AI review is complete and every AI passage is No for that code; otherwise NA. The theme N is the number of AI-positive countries with a resolved value for that code; co-occurrence uses countries resolved on both codes as denominator. Same-country year comparisons use the per-code common sample. Unreviewed or unobtained data are never converted to 0. New concepts go to the review queue and do not block completion of existing codes. Regions use the fixed UN mapping.',
        'Separate calls to the same model are automated re-review, not inter-human agreement. No audio verification or completed human review is claimed. Reports produced from automated review state this limitation.',
        f"Usage and cost ledger: {cfg['execution']['output_directory']}/api_cache/usage.jsonl. Recorded rates are applied to API-reported token usage. Ambiguous transport failures keep their cost reservation. Rates checked: {cfg['execution']['pricing_checked']}.",
        'An embedding-free approach is possible but would need a separate theme-discovery procedure; earlier MiniLM results are not reused. This path links the user-specified OpenAI embeddings to source-grounded review.',
        'Cache keys change when sources, prompts, models or the taxonomy change. Word and PDF are generated from the same content; PDF page boundaries and sections are checked. Whether the Word rendering was verified is recorded in publication_checks.json.']
    (out/'methodology_and_cost.md').write_text('\n\n'.join(memo)+'\n',encoding='utf-8')
    save(out/'environment.json',readiness['dependencies'])
    if 'cost_estimate' in readiness:save(out/'cost_estimate.json',readiness['cost_estimate'])
    save(out/'analysis_config.json',cfg)
