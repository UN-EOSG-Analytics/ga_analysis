"""Offline planning scenarios from actual request text and explicit assumptions."""
from pathlib import Path
import json
import math

from ..io import read_jsonl,digest
from .review import review_request,SCHEMA
from .classification import schema as classification_schema


def estimate_costs(root,speeches,cfg):
    root=Path(root);settings=cfg['cost_estimation'];rates=cfg['execution']
    ratio=settings['chars_per_token'];overhead=settings['protocol_overhead_tokens_per_request']
    if ratio<=0:raise ValueError('chars_per_token must be positive')
    scenarios=settings['output_tokens_per_request']
    if not scenarios or any(v<=0 for v in scenarios):raise ValueError('Output token scenarios must be positive')
    all_ids={p['passage_id'] for s in speeches for p in s['passages']}
    candidate_path=root/'output/screening/ai_candidates.jsonl';summary_path=root/'output/screening/summary.json'
    candidate_ids=all_ids;candidate_status='screening_missing_or_stale_assume_all_passages';matches=None
    if candidate_path.exists() and summary_path.exists():
        summary=json.loads(summary_path.read_text(encoding='utf-8'))
        if summary.get('input_sha256')==digest(root/cfg['output_directory']/'speeches.jsonl'):
            candidates=list(read_jsonl(candidate_path));ids={e['passage_id'] for r in candidates for e in r['evidence']}
            if ids.issubset(all_ids):candidate_ids=ids;candidate_status='unique_screening_evidence_passage_ids';matches=len(candidates)
    review_chars=0;review_calls=0;max_id_output_chars=0;batch=cfg['execution']['review_batch_passages']
    schema_chars=len(json.dumps(SCHEMA))
    for speech in speeches:
        for start in range(0,len(speech['passages']),batch):
            for pass_no in (1,2):
                payload,instructions=review_request(speech,start,min(start+batch,len(speech['passages'])),pass_no)
                review_chars+=len(json.dumps(payload,ensure_ascii=False))+len(instructions)+schema_chars
                max_id_output_chars=max(max_id_output_chars,len(json.dumps([p['passage_id'] for p in payload['passages']])))
                review_calls+=1
    focal_chars=0;classify_chars=0;embedding_chars=0
    codes=[f'THEME{i:02}' for i in range(settings['assumed_theme_codes'])]
    classification_overhead=settings['assumed_taxonomy_chars']+settings['classification_instruction_chars']+len(json.dumps(classification_schema(cfg,codes)))
    for speech in speeches:
        passages=speech['passages']
        for i,p in enumerate(passages):
            if p['passage_id'] not in candidate_ids:continue
            before=passages[i-1]['text'] if i else '';after=passages[i+1]['text'] if i+1<len(passages) else ''
            payload=dict(passage_id=p['passage_id'],source_sha256=speech['sha256'],text=p['text'],preceding_context=before,following_context=after,source_review_notes=speech.get('source_review_notes'))
            classify_chars+=2*(len(json.dumps(payload,ensure_ascii=False))+classification_overhead)
            text='\n'.join([before[-600:],p['text'],after[:600]]).strip()
            if len(text.encode('utf-8'))>8000:text=p['text']
            embedding_chars+=len(text);focal_chars+=len(p['text'])
    n=len(candidate_ids);other=settings['other_instruction_schema_chars'];stages={}
    def stage(name,low_calls,high_calls,low_chars,high_chars,embedding=False):
        low_tokens=low_chars/ratio+(0 if embedding else low_calls*overhead)
        high_tokens=high_chars/ratio+(0 if embedding else high_calls*overhead)
        values={}
        for tokens in scenarios:
            if embedding:low=low_tokens*rates['embedding_usd_per_million']/1e6;high=high_tokens*rates['embedding_usd_per_million']/1e6
            else:
                low=(low_tokens*rates['review_input_usd_per_million']+low_calls*tokens*rates['review_output_usd_per_million'])/1e6
                high=(high_tokens*rates['review_input_usd_per_million']+high_calls*tokens*rates['review_output_usd_per_million'])/1e6
            values[str(tokens)]=dict(lower_usd=round(low,6),upper_usd=round(high,6))
        stages[name]=dict(requests_lower=low_calls,requests_upper=high_calls,input_characters_lower=round(low_chars),input_characters_upper=round(high_chars),
            input_tokens_lower=round(low_tokens),input_tokens_upper=round(high_tokens),scenarios=values)
    stage('review',review_calls,review_calls,review_chars,review_chars)
    stage('embeddings',math.ceil(n/cfg['execution']['embedding_batch_size']),math.ceil(n/cfg['execution']['embedding_batch_size']),embedding_chars,embedding_chars,True)
    normal=min(n,max(cfg['discovery']['candidate_k']));fallback=math.ceil(n/24)
    lo=min(normal,fallback);hi=max(normal,fallback)
    # Discovery duplicates sampled text in cluster metadata and explicit samples.
    normal_chars=2*min(n,normal*8)*(focal_chars/n if n else 0)+normal*other
    fallback_chars=2*focal_chars+fallback*other
    stage('discovery',lo,hi,min(normal_chars,fallback_chars),max(normal_chars,fallback_chars))
    merge_chars=min(cfg['discovery']['taxonomy_payload_max_chars'],settings['assumed_taxonomy_chars']+2*len(codes)*(focal_chars/n if n else 0))
    stage('taxonomy',2 if n else 0,4 if n else 0,2*(merge_chars+other) if n else 0,4*(cfg['discovery']['taxonomy_payload_max_chars']+other) if n else 0)
    stage('classification',2*n,2*n,classify_chars,classify_chars)
    reference_calls=0;reference_chars=0;reference_status='local_documents_measured_no_network'
    try:
        from .references import reference_blocks
        blocks,_=reference_blocks(root,None,fetch_current=False)
        current=[];length=0;groups=[]
        for b in blocks:
            if current and length+len(b['text'])>22000:groups.append(current);current=[];length=0
            current.append(b);length+=len(b['text'])
        if current:groups.append(current)
        reference_calls=len(groups)
        reference_chars=sum(len(json.dumps({'blocks':[{k:v for k,v in b.items() if k!='locator'} for b in group]},ensure_ascii=False))+other for group in groups)
    except (ImportError,OSError,ValueError):
        reference_status='local_reference_measurement_unavailable_assume_20_chunks'
        reference_calls=20;reference_chars=20*(22000+other)
    web=settings['assumed_web_reference_chunks']
    stage('references',reference_calls,reference_calls+web,reference_chars,reference_chars+web*(22000+other))
    stage('report',2,2,2*(settings['assumed_report_input_chars']+other),2*(settings['assumed_report_input_chars']+other))
    totals={str(t):dict(lower_usd=round(sum(s['scenarios'][str(t)]['lower_usd'] for s in stages.values()),4),
                       upper_usd=round(sum(s['scenarios'][str(t)]['upper_usd'] for s in stages.values()),4)) for t in scenarios}
    return dict(stages=stages,total_scenarios=totals,
        lower_usd=min(v['lower_usd'] for v in totals.values()),upper_usd=max(v['upper_usd'] for v in totals.values()),
        measured=dict(speeches=len(speeches),passages=len(all_ids),review_requests=review_calls,review_input_characters=review_chars,
            max_reviewed_id_list_characters=max_id_output_chars,candidate_matches=matches,candidate_unique_passages=n,candidate_status=candidate_status,
            candidate_text_characters=focal_chars,reference_status=reference_status,local_reference_requests=reference_calls),
        assumptions=dict(settings,output_tokens_include_reasoning=True,screening_candidates_are_proxy_not_verified_AI=True,
            cache_savings_assumed=False,semantic_or_transport_retries_included=False,batch_splitting_included=False,
            discovery_request_range='Largest configured cluster cut versus all-source batches of 24; later splits can add calls',
            taxonomy_request_range='2-4 synthesis/audit calls; nonconvergence and extra hierarchy rounds are not a guaranteed bound'),
        pricing_checked=cfg['execution']['pricing_checked'],scope='Planning scenarios, not a billing guarantee or a hard upper bound. Actual AI passage count, codebook, reasoning, retries, splits and model usage can increase cost.')
