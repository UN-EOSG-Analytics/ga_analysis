"""Whole selected speeches, stratified negative audits and explicit unreviewed rows."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

from ..io import write_jsonl, stable_hash
from .common import obj, arr, STR, BOOL, quote_in, ask, SYSTEM, save
from .provider import ResponseUnavailable

SCHEMA = obj(complete=BOOL, reviewed_passage_ids=arr(STR), findings=arr(obj(
    passage_id=STR, status={'type':'string','enum':['Yes','Uncertain']},
    mention_type={'type':'string','enum':['explicit','contextual','uncertain']}, quote=STR, rationale=STR)))



def review_request(speech,start,end,pass_no):
    passages=speech['passages'];batch=passages[start:end]
    payload = dict(speech_id=speech['speech_id'], source_sha256=speech['sha256'],
                   source_type=speech['source_type'], source_review_notes=speech.get('source_review_notes'),
                   passages=[{'passage_id':p['passage_id'],'text':p['text']} for p in batch],
                   preceding_context=passages[start-1]['text'] if start else '',
                   following_context=passages[end]['text'] if end<len(passages) else '')

    instructions=SYSTEM+('Review EVERY passage for substantive AI discussion, including variants such as superintelligence, '
        'machine learning, AI systems and AI governance institutions. Generic digitalization, military intelligence, '
        'ordinary algorithms or autonomous weapons without an AI link are not sufficient. The list of reviewed IDs '
        'must cover all passages. Return findings for Yes or Uncertain ONLY; omission from findings means you '
        'reviewed that passage and found No AI evidence. Never omit an unreviewed passage. Use exact quotes of at most 80 words. '
        'A source-review note is a limitation, not evidence of delivered wording. ')
    instructions += ('First reviewer: inspect full context and detect indirect but unambiguous AI discussions.' if pass_no==1 else
                     'Second reviewer: independently audit the full text, including possible keyword misses and ambiguous abbreviations. Do not assume a prior verdict.')
    return payload,instructions


def review_speech(speech, provider, cfg,pass_count=2):
    passages = speech['passages']
    results = []
    size = cfg['execution']['review_batch_passages']
    def review_batch(start,end,pass_no):
        batch = passages[start:end]
        by_id = {p['passage_id']:p for p in batch}
        payload,instructions=review_request(speech,start,end,pass_no)

        def validate(result):
            ids = result['reviewed_passage_ids']
            if not result['complete'] or set(ids)!=set(by_id) or len(ids)!=len(by_id):
                raise ValueError('Must explicitly review every supplied passage exactly once')
            findings = result['findings']
            if len({x['passage_id'] for x in findings}) != len(findings):
                raise ValueError('Duplicate finding')
            for f in findings:
                if f['passage_id'] not in by_id or len(f['quote'].split())>80 or not quote_in(f['quote'],by_id[f['passage_id']]['text']):
                    raise ValueError('Every finding must quote a contiguous exact span from its identified passage')
                if not f['rationale'].strip():
                    raise ValueError('Missing rationale')
        try:
            value=ask(provider, f'review_{pass_no}', payload, SCHEMA, instructions, validate)
            return {f['passage_id']:f for f in value['findings']}
        except ResponseUnavailable as exc:
            if exc.reason not in ('max_output_tokens','refusal','content_filter'):raise
            if end-start>1:
                middle=(start+end)//2
                return {**review_batch(start,middle,pass_no),**review_batch(middle,end,pass_no)}
            return {batch[0]['passage_id']:dict(status='Uncertain',mention_type='uncertain',quote='',
                rationale='Automated review unavailable; no source judgement made.',reviewed=False,review_failure=exc.reason)}

    for start in range(0,len(passages),size):
        batch=passages[start:start+size]
        reviews=[review_batch(start,min(start+size,len(passages)),pass_no) for pass_no in range(1,pass_count+1)]
        for local_index,p in enumerate(batch):
            absolute_index=start+local_index
            a=reviews[0].get(p['passage_id'],{'status':'No','mention_type':'none','quote':'','rationale':'Entire supplied passage reviewed; no substantive AI discussion identified.'})
            b=reviews[1].get(p['passage_id'],{'status':'No','mention_type':'none','quote':'','rationale':'Independent complete text review found no substantive AI discussion.'}) if pass_count==2 else a
            status=a['status'] if a['status']==b['status'] else 'Uncertain'
            results.append(dict(passage_id=p['passage_id'], speech_id=speech['speech_id'], year=speech['year'],
                country_iso3=speech['country_iso3'], region=speech['analytical_group'], source_sha256=speech['sha256'],
                source_file=speech['path'], source_type=speech['source_type'], text_accuracy=speech.get('text_accuracy'),
                origin_file=speech.get('origin_file'), locator=p['locator'], text=p['text'],
                context_before=passages[absolute_index-1]['text'] if absolute_index else '',
                context_after=passages[absolute_index+1]['text'] if absolute_index+1<len(passages) else '',
                ai_status=status, review_status='reviewed' if status!='Uncertain' else 'uncertain',
                review_method=f'{pass_count}_automated_full_text_review_passes_exact_quote_checked', human_reviewed=False,
                reviews=[a,b] if pass_count==2 else [a], source_review_notes=speech.get('source_review_notes')))
    return results


def review_all(speeches, provider, cfg, out,plan=None):
    from .scope import review_plan,stratum
    plan=plan or review_plan(speeches,cfg,getattr(provider,'root',None))
    selection={r['speech_id']:r for r in plan['rows']};size=cfg['execution']['review_batch_passages']
    save(out/'review_selection.json',plan)
    def execute(selected):
        if hasattr(provider,'collect'):
            jobs=[]
            for s in selected:
                for start in range(0,len(s['passages']),size):
                    for n in range(1,selection[s['speech_id']]['passes']+1):
                        payload,instructions=review_request(s,start,min(start+size,len(s['passages'])),n)
                        jobs.append((f'review_{n}',payload,SCHEMA,instructions,None))
            provider.collect(jobs)
        records=[]
        with ThreadPoolExecutor(max_workers=cfg['execution']['workers']) as pool:
            for result in pool.map(lambda s:review_speech(s,provider,cfg,selection[s['speech_id']]['passes']),selected):records.extend(result)
        for r in records:r['review_selection']=selection[r['speech_id']]['selection']
        return records
    records=execute([s for s in speeches if selection[s['speech_id']]['passes']])
    hits={r['speech_id'] for r in records if r['review_selection']=='negative_audit_sample' and r['ai_status'] in ('Yes','Uncertain')}
    strata={stratum(s) for s in speeches if s['speech_id'] in hits}
    expansion=[s for s in speeches if not selection[s['speech_id']]['passes'] and stratum(s) in strata] if cfg.get('review',{}).get('expand_on_audit_hit',True) else []
    for s in expansion:selection[s['speech_id']].update(selection='audit_hit_expansion',passes=cfg.get('review',{}).get('primary_passes',2))
    plan.update(audit_hit_speeches=sorted(hits),expanded_speeches=len(expansion),rows=list(selection.values()),
        selected_speeches=sum(bool(r['passes']) for r in selection.values()),unselected_speeches=sum(not r['passes'] for r in selection.values()))
    save(out/'review_selection.json',plan)
    records.extend(execute(expansion))
    for s in speeches:
        if selection[s['speech_id']]['passes']:continue
        for p in s['passages']:
            records.append(dict(passage_id=p['passage_id'],speech_id=s['speech_id'],year=s['year'],country_iso3=s['country_iso3'],
                ai_status='Pending',review_status='not_reviewed',review_selection='not_selected',reviews=[],human_reviewed=False))
    order={p['passage_id']:i for i,p in enumerate(p for s in speeches for p in s['passages'])}
    records.sort(key=lambda r:order[r['passage_id']])
    write_jsonl(out/'passage_ai_review.jsonl',records)
    summary=dict(passages=len(records), counts=dict(Counter(r['ai_status'] for r in records)),
                 all_passages_attempted=not any(r['ai_status']=='Pending' for r in records),
                 all_passages_reviewed=all(r['reviews'] and all(v.get('reviewed',True) for v in r['reviews']) for r in records),
                 review_scope=plan['scope'],audit_hit_speeches=sorted(hits),expanded_speeches=len(expansion),
                 human_reviewed=False, corpus_fingerprint=stable_hash([(s['source_id'],s['sha256']) for s in speeches]))
    save(out/'ai_review_summary.json',summary)
    return records


def ai_chunks(speeches, reviews):
    from difflib import SequenceMatcher
    verdict={r['passage_id']:r for r in reviews}
    chunks=[];duplicates=[]
    for speech in speeches:
        prior=[]
        for index,p in enumerate(speech['passages']):
            if verdict[p['passage_id']]['ai_status']!='Yes':
                continue
            normalized=' '.join(p['text'].lower().split())
            duplicate=next((q for text,q in prior if SequenceMatcher(None,text,normalized,autojunk=False).ratio()>=.97),None)
            if duplicate:
                duplicates.append(dict(passage_id=p['passage_id'],representative_passage_id=duplicate,scope='discovery_only'))
                continue
            prior.append((normalized,p['passage_id']))
            before=speech['passages'][index-1]['text'][-600:] if index else ''
            after=speech['passages'][index+1]['text'][:600] if index+1<len(speech['passages']) else ''
            embedding_text='\n'.join([before,p['text'],after]).strip()
            if len(embedding_text.encode('utf-8'))>8000:
                embedding_text=p['text']
            chunks.append(dict(verdict[p['passage_id']],embedding_text=embedding_text))
    return chunks,duplicates
