"""OpenAI vectors, cosine/average hierarchical discovery and grounded taxonomy."""
from collections import Counter
import json
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster, cophenet
from scipy.spatial.distance import pdist, squareform
from sklearn.metrics import silhouette_score
from sklearn.feature_extraction.text import TfidfVectorizer

from ..io import stable_hash
from .common import obj, arr, STR, quote_in, safe_code, ask, SYSTEM, save, table

THEME = obj(code=STR, label=STR, definition=STR, inclusion=STR, exclusion=STR,
            boundary_cases=STR, examples=arr(obj(passage_id=STR, quote=STR)))
TAXONOMY = obj(themes=arr(THEME), rationale=STR)


def taxonomy_payload(themes,source,audit=False):
    ids=sorted({e['passage_id'] for t in themes for e in t['examples']})
    examples=[dict(passage_id=p,text=source[p]) for p in ids]
    return dict(proposed={'themes':themes,'rationale':'Audit this codebook subset.'},examples=examples) if audit else dict(proposals=themes,examples=examples)


def proposal_batches(themes,source,limit,audit=False):
    batches=[];batch=[]
    for theme in themes:
        if len(json.dumps(taxonomy_payload(batch+[theme],source,audit),ensure_ascii=False))>limit:
            if not batch:raise ValueError('A single taxonomy proposal exceeds taxonomy_payload_max_chars; inspect its evidence/definition or raise the configured limit')
            batches.append(batch);batch=[]
        if len(json.dumps(taxonomy_payload([theme],source,audit),ensure_ascii=False))>limit:
            raise ValueError('A single taxonomy proposal exceeds taxonomy_payload_max_chars')
        batch.append(theme)
    if batch:batches.append(batch)
    return batches


def consolidate(proposals,source,provider,cfg,diagnostics):
    limit=cfg['discovery'].get('taxonomy_payload_max_chars',120000)
    if limit<=0:raise ValueError('taxonomy_payload_max_chars must be positive')
    requests=diagnostics.setdefault('taxonomy_requests',[])
    def request(batch,audit=False,job_only=False):
        payload=taxonomy_payload(batch,source,audit)
        subset={r['passage_id']:r['text'] for r in payload['examples']}
        stage='taxonomy_audit' if audit else 'taxonomy_merge'
        instruction=('Audit and correct this codebook subset against the supplied source examples. Keep code identifiers stable and review each definition. '
            if audit else 'Consolidate redundant proposals into a common multilabel codebook across years. Preserve distinct minority concepts and uppercase stable codes. ')
        instruction=SYSTEM+instruction+(
            'Use only supplied passage IDs and exact source examples. Keep definitions compact and at most two examples per theme. '
            'Do not infer endorsement from mention. This is automated source review, not human approval.')
        if job_only:return (stage,payload,TAXONOMY,instruction,14000)
        requests.append(dict(stage=stage,characters=len(json.dumps(payload,ensure_ascii=False)),source_passages=len(subset)))
        return ask(provider,stage,payload,TAXONOMY,instruction,
            lambda v:validate_taxonomy(v,subset),max_tokens=14000,max_payload_chars=limit)
    current=proposals;seen=set()
    for _ in range(8):
        fingerprint=stable_hash(current)
        if fingerprint in seen:raise ValueError('Bounded taxonomy consolidation did not converge; inspect proposals before retrying')
        seen.add(fingerprint)
        batches=proposal_batches(current,source,limit)
        if hasattr(provider,'collect'):provider.collect([request(batch,job_only=True) for batch in batches])
        results=[request(batch) for batch in batches]
        current=[theme for result in results for theme in result['themes']]
        if len(batches)==1:break
    else:raise ValueError('Bounded taxonomy consolidation exceeded eight rounds')
    batches=proposal_batches(current,source,limit,audit=True)
    if hasattr(provider,'collect'):provider.collect([request(batch,audit=True,job_only=True) for batch in batches])
    audits=[request(batch,audit=True) for batch in batches]
    checked=dict(themes=[t for result in audits for t in result['themes']],rationale=' '.join(r['rationale'] for r in audits))
    validate_taxonomy(checked,{p:source[p] for p in {e['passage_id'] for t in current for e in t['examples']}})
    return checked


def clusters(vectors, records, cfg):
    n=len(records)
    if not n:
        return [],dict(status='no_verified_AI_passages',cuts=[],clusters=[])
    if n>cfg['execution']['max_discovery_passages']:
        raise ValueError('Discovery exceeds configured memory bound; raise max_discovery_passages after checking memory')
    x=np.asarray(vectors,dtype=float)
    if x.ndim!=2 or len(x)!=n or not np.isfinite(x).all():
        raise ValueError('Invalid embedding matrix')
    if n==1:
        return [1],dict(status='single_passage',cuts=[],clusters=[{'cluster':1,'size':1}],mean_centered=False)
    centered=x-x.mean(axis=0)
    norms=np.linalg.norm(centered,axis=1)
    zero=np.flatnonzero(norms<1e-12)
    for i in zero:
        centered[i]=x[i];norms[i]=np.linalg.norm(x[i])
    if np.any(norms<1e-12):
        raise ValueError('Zero embedding vector')
    centered=centered/norms[:,None]
    distances=np.clip(pdist(centered,'cosine'),0,2)
    z=linkage(distances,method='average')
    square=squareform(distances);np.fill_diagonal(square,0)
    cuts=[];choices=[]
    levels=sorted(set(min(k,n-1) for k in cfg['discovery']['candidate_k'] if min(k,n-1)>1))
    trials=[(f'k={k}',fcluster(z,k,criterion='maxclust')) for k in levels]
    trials.append(('distance=0.7',fcluster(z,.7,criterion='distance')))
    for name,labels in trials:
        counts=Counter(int(v) for v in labels)
        score=float(silhouette_score(square,labels,metric='precomputed')) if 1<len(counts)<n else None
        valid=max(counts.values())/n<=cfg['discovery']['max_cluster_share'] and sum(v==1 for v in counts.values())<=len(counts)/2
        item=dict(cut=name,sizes=dict(counts),silhouette=score,usable=valid)
        cuts.append(item)
        choices.append((valid,score if score is not None else -2,labels))
    chosen=max(choices,key=lambda v:(v[0],v[1]))[2] if choices else np.ones(n,dtype=int)
    splits=[]
    # Refine dominant groups only; small/degenerate groups remain explicit outliers.
    for _ in range(8):
        counts=Counter(int(v) for v in chosen)
        dominant=max(counts,key=counts.get)
        if counts[dominant]/n<=cfg['discovery']['max_cluster_share'] or counts[dominant]<4:
            break
        indices=np.flatnonzero(chosen==dominant)
        sub=linkage(pdist(centered[indices],'cosine'),method='average')
        split=fcluster(sub,min(4,len(indices)-1),criterion='maxclust')
        if len(set(split))<2:
            break
        base=int(max(chosen))
        for j,index in enumerate(indices):chosen[index]=base+int(split[j])
        splits.append(dict(original_cluster=int(dominant),size=len(indices),new_sizes=dict(Counter(int(v) for v in split))))
    remap={v:i+1 for i,v in enumerate(sorted(set(chosen)))}
    labels=[remap[v] for v in chosen]
    corpus=[' '.join(r['text'].split()) for r in records]
    try:
        tfidf=TfidfVectorizer(stop_words='english',ngram_range=(1,2),min_df=1,max_features=15000)
        matrix=tfidf.fit_transform(corpus);terms=tfidf.get_feature_names_out()
    except ValueError:
        matrix=None;terms=[]
    groups=[]
    for label in sorted(set(labels)):
        ids=[i for i,v in enumerate(labels) if v==label]
        centroid=centered[ids].mean(axis=0)
        distance=1-centered[ids]@centroid/(np.linalg.norm(centroid) or 1)
        order=[ids[int(i)] for i in np.argsort(distance)]
        sampled=list(dict.fromkeys(order[:5]+list(reversed(order[-3:]))))
        words=[]
        if matrix is not None:
            scores=np.asarray(matrix[ids].mean(axis=0)).ravel()
            words=[str(terms[i]) for i in scores.argsort()[-12:][::-1] if scores[i]>0]
        groups.append(dict(cluster=label,size=len(ids),top_terms=words,
            speech_contributions=dict(Counter(records[i]['speech_id'] for i in ids)),
            samples=[dict(passage_id=records[i]['passage_id'],speech_id=records[i]['speech_id'],text=records[i]['text']) for i in sampled]))
    corr=float(cophenet(z,distances)[0]) if np.std(distances)>0 else None
    if corr is not None and not np.isfinite(corr):corr=None
    unresolved=any(g['size']/n>cfg['discovery']['max_cluster_share'] for g in groups) or sum(g['size']==1 for g in groups)>len(groups)/2
    return labels,dict(status='discovered',mean_centered=True,zero_centered_vectors=len(zero),metric='cosine',linkage='average',
        cuts=cuts,dominant_splits=splits,cophenetic_correlation=corr,clusters=groups,
        unresolved_geometry=unresolved,
        caution='Clusters aid discovery only; no cluster directly determines a theme label.')


def discover(records, provider, cfg, out):
    if not records:
        taxonomy=dict(status='no_verified_AI_passages',version='empty-corpus',codes={})
        save(out/'taxonomy.json',taxonomy)
        save(out/'discovery_diagnostics.json',{'status':'no_verified_AI_passages'})
        return taxonomy,{}
    vectors=provider.embed(records)
    labels,diagnostics=clusters(vectors,records,cfg)
    groups=diagnostics['clusters']
    if diagnostics.get('unresolved_geometry'):
        # Failed geometry must not reduce discovery to eight examples of one giant cluster.
        # Read all passages in bounded source batches; geometric memberships remain diagnostic.
        groups=[dict(source_review_batch=i//24+1,samples=[dict(passage_id=r['passage_id'],speech_id=r['speech_id'],text=r['text']) for r in records[i:i+24]]) for i in range(0,len(records),24)]
        diagnostics['taxonomy_sampling']='all_source_passages_in_batches_due_to_unusable_geometry'
    else:
        diagnostics['taxonomy_sampling']='representative_and_boundary_passages'
    save(out/'discovery_diagnostics.json',diagnostics)
    table(out/'discovery_membership.csv',[dict(passage_id=r['passage_id'],speech_id=r['speech_id'],cluster_id=c) for r,c in zip(records,labels)])
    instruction=SYSTEM+(
        'Read every representative and boundary passage. Propose analytical theme definitions grounded in these statements. '
        'Separate technical AI safety from military/security concerns when warranted. Include minority positions; do not force '
        'one theme per cluster or a predetermined number. Every theme needs exact source examples, inclusion/exclusion and boundary cases.')
    if hasattr(provider,'collect'):
        provider.collect([('discover_cluster',{'cluster':g,'samples':g.get('samples') or [dict(passage_id=r['passage_id'],speech_id=r['speech_id'],text=r['text']) for r in records]},TAXONOMY,instruction,9000) for g in groups])
    proposals=[];all_samples={}
    for group in groups:
        samples=group.get('samples') or [dict(passage_id=r['passage_id'],speech_id=r['speech_id'],text=r['text']) for r in records]
        source={r['passage_id']:r['text'] for r in samples};all_samples.update(source)
        def validate(value,source=source):
            validate_taxonomy(value,source)
        proposal=ask(provider,'discover_cluster',{'cluster':group,'samples':samples},TAXONOMY,instruction,validate,max_tokens=9000)
        proposals.extend(proposal['themes'])
    cited={e['passage_id'] for t in proposals for e in t['examples']}
    try:checked=consolidate(proposals,{p:all_samples[p] for p in cited},provider,cfg,diagnostics)
    finally:save(out/'discovery_diagnostics.json',diagnostics)
    codes={t['code']:{k:v for k,v in t.items() if k!='code'} for t in checked['themes']}
    taxonomy=dict(status='automated_source_reviewed',human_reviewed=False,version=stable_hash(codes)[:16],codes=codes,
                  rationale=checked['rationale'],source_passage_hash=stable_hash([(r['passage_id'],r['source_sha256']) for r in records]))
    save(out/'taxonomy.json',taxonomy)
    return taxonomy,{r['passage_id']:c for r,c in zip(records,labels)}


def validate_taxonomy(value, source):
    themes=value['themes']
    if not themes or len(themes)>30 or len({t['code'] for t in themes})!=len(themes):
        raise ValueError('Need 1-30 unique, source-grounded theme codes')
    for t in themes:
        if not safe_code(t['code']) or len(t['label'].split())>8 or any(not t[k].strip() for k in ('label','definition','inclusion','exclusion','boundary_cases')):
            raise ValueError('Invalid theme code or missing definition')
        if not t['examples']:
            raise ValueError('Every theme needs source examples')
        for e in t['examples']:
            if e['passage_id'] not in source or not quote_in(e['quote'],source[e['passage_id']]):
                raise ValueError('Taxonomy example must be an exact source quotation')
