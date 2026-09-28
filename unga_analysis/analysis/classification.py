"""Multilabel and institutional review; exact quotes and cross-pass agreement."""
from concurrent.futures import ThreadPoolExecutor

from ..io import stable_hash, write_jsonl
from .common import obj, arr, STR, BOOL, LABEL, SYSTEM, ask, quote_in, table


def schema(cfg,codes):
    inst=cfg['institutions']
    return obj(themes=arr(obj(code={'type':'string','enum':list(codes)},value=LABEL,quote=STR,rationale=STR)),
        institutions=arr(obj(mechanism={'type':'string','enum':inst['mechanisms']},
            reference_type={'type':'string','enum':['explicit name','name variant','inferred description']},
            stances=obj(**{k:BOOL for k in inst['stances']}),
            requested_functions=arr({'type':'string','enum':inst['functions']}),
            un_role={'type':'string','enum':inst['un_role']},quote=STR,commitment_detail=STR,rationale=STR)),
        keywords=arr(obj(normalized_term=STR,original_term=STR,quote=STR)),uncovered_concept=STR)


def classify_one(record,provider,taxonomy,cfg,cluster_id):
    codes=taxonomy['codes'];contract=schema(cfg,codes)
    payload=dict(passage_id=record['passage_id'],source_sha256=record['source_sha256'],text=record['text'],
                 preceding_context=record.get('context_before',''),following_context=record.get('context_after',''),
                 taxonomy=taxonomy,source_review_notes=record.get('source_review_notes'))
    def validate(value):
        if len(value['themes'])!=len(codes) or {t['code'] for t in value['themes']}!=set(codes):
            raise ValueError('Every taxonomy code requires exactly one explicit label')
        for theme in value['themes']:
            if theme['value']=='Yes' and (len(theme['quote'].split())>80 or not quote_in(theme['quote'],record['text'])):
                raise ValueError('Yes needs an exact quote from this passage')
            if not theme['rationale'].strip():raise ValueError('Theme rationale missing')
        if len({v['mechanism'] for v in value['institutions']})!=len(value['institutions']):
            raise ValueError('Return one combined record per mechanism for this passage')
        for institution in value['institutions']:
            if len(institution['quote'].split())>80 or not quote_in(institution['quote'],record['text']):raise ValueError('Institution quote must be an exact span of at most 80 words')
            if institution['stances']['commitment'] and not institution['commitment_detail'].strip():
                raise ValueError('Commitment requires actor/action detail')
        for word in value['keywords']:
            if not word['normalized_term'].strip() or not quote_in(word['quote'],record['text']) or not quote_in(word['original_term'],word['quote']):
                raise ValueError('Keyword must have original wording in a source quote')
    passes=[]
    for pass_no in (1,2):
        instructions=SYSTEM+('Apply every code independently to this AI passage; allow multiple Yes labels. '
            'Use exact quotes of at most 80 words and do not infer themes from a cluster, country identity or frequency. '
            'Extract every AI governance institution/model and distinguish mention, welcome, support, request, concern, opposition and commitment. '
            'A named model (FSB/IAEA/IPCC/CERN) must actually relate to AI. Record requested functions exactly. '
            'Return one record per mechanism in this passage; adjacent context may resolve references but quotations must come from the focal text. '
            'Commitment needs this State as actor and a concrete undertaking, not a generic request or completed action inferred from support. '
            'Identify distinctive AI-related original terms, including institutional names, without merging substantively different concepts. '
            'If the codebook misses a substantive theme, describe it in uncovered_concept, otherwise use an empty string. '
            'Source-review notes never authorize importing prepared-only words into the delivered passage. ')
        instructions+=f'Independent automated classification pass {pass_no}; read the source afresh.'
        passes.append(ask(provider,f'classify_{pass_no}',payload,contract,instructions,validate,max_tokens=9000))
    a,b=passes
    aa={x['code']:x for x in a['themes']};bb={x['code']:x for x in b['themes']}
    labels={c:aa[c]['value'] if aa[c]['value']==bb[c]['value'] else 'Uncertain' for c in codes}
    evidence={c:aa[c]['quote'] for c in codes if labels[c]=='Yes'}
    institutions=[]
    # One passage may discuss several named institutions; retain disagreements as uncertain.
    for mechanism in sorted({x['mechanism'] for v in passes for x in v['institutions']}):
        left=[x for x in a['institutions'] if x['mechanism']==mechanism]
        right=[x for x in b['institutions'] if x['mechanism']==mechanism]
        base=(left or right)[0]
        flags={k:any(x['stances'][k] for x in left) for k in cfg['institutions']['stances']}
        other={k:any(x['stances'][k] for x in right) for k in flags}
        agreed=bool(left and right) and flags==other and {f for x in left for f in x['requested_functions']}=={f for x in right for f in x['requested_functions']} and {x['un_role'] for x in left}=={x['un_role'] for x in right}
        institutions.append(dict(base,stances={k:int(v) for k,v in flags.items()},
            requested_functions=sorted({f for x in (left or right) for f in x['requested_functions']}),
            review_status='reviewed' if agreed else 'uncertain'))
    left={w['normalized_term'].strip().casefold():w for w in a['keywords']}
    right={w['normalized_term'].strip().casefold():w for w in b['keywords']}
    keywords=[dict((left.get(k) or right[k]),normalized_term=k,review_status='reviewed' if k in left and k in right else 'uncertain') for k in sorted(set(left)|set(right))]
    note=record.get('source_review_notes')
    issue=note and note.get('status')=='pending_delivery_verification'
    return dict(record, themes=labels,evidence=evidence,taxonomy_sha256=stable_hash(taxonomy),
        review_status='reviewed' if all(v!='Uncertain' for v in labels.values()) and not issue and not a['uncovered_concept'] and not b['uncovered_concept'] else 'uncertain',
        classification_complete=all(v!='Uncertain' for v in labels.values()) and not issue and not a['uncovered_concept'] and not b['uncovered_concept'],
        keyword_review_complete=set(left)==set(right) and not issue,
        institutions=institutions,keywords=keywords,classification_reviews=passes,
        uncovered_concepts=list(dict.fromkeys(v for v in [a['uncovered_concept'],b['uncovered_concept']] if v)),
        discovery_cluster_id=cluster_id,human_reviewed=False)


def classify_all(reviews,taxonomy,membership,provider,cfg,out):
    records=[r for r in reviews if r['ai_status']=='Yes']
    if records and not taxonomy['codes']:raise ValueError('Cannot classify AI passages without a source-grounded taxonomy')
    classified=[]
    with ThreadPoolExecutor(max_workers=cfg['execution']['workers']) as pool:
        for i,r in enumerate(pool.map(lambda r:classify_one(r,provider,taxonomy,cfg,membership.get(r['passage_id'])),records),1):
            classified.append(r)
            if i%20==0 or i==len(records):print(f'Classification {i}/{len(records)} AI passages',flush=True)
    write_jsonl(out/'classified_passages.jsonl',classified)
    table(out/'paragraph_theme_labels.csv',[{k:r[k] for k in ['passage_id','speech_id','source_file','source_sha256','locator','taxonomy_sha256','themes','evidence','review_status','classification_complete','discovery_cluster_id','human_reviewed']} for r in classified])
    return classified
