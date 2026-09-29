"""Deterministic screening-led speech review; omissions never become negatives."""
from collections import defaultdict
from pathlib import Path
import json

from ..io import digest,read_jsonl,stable_hash


def stratum(speech):return (speech['year'],speech['analytical_group'],speech['source_type'])


def review_plan(speeches,cfg,root=None):
    settings=cfg.get('review',{});mode=settings.get('scope','full')
    primary=settings.get('primary_passes',2);seed=settings.get('sample_seed','unga-review-v1')
    if primary not in (1,2):raise ValueError('Review primary_passes must be 1 or 2')
    candidates=None;reason='full review requested'
    if mode not in ('full','screened_speeches'):raise ValueError('Unknown review scope')
    if mode=='screened_speeches' and root is not None:
        root=Path(root);summary=root/'output/screening/summary.json';path=root/'output/screening/ai_candidates.jsonl'
        corpus=root/cfg['output_directory']/'speeches.jsonl'
        if summary.exists() and path.exists() and corpus.exists() and json.loads(summary.read_text(encoding='utf-8')).get('input_sha256')==digest(corpus):
            ids={p['passage_id'] for row in read_jsonl(path) for p in row['evidence']}
            known={p['passage_id'] for s in speeches for p in s['passages']}
            if not ids.issubset(known):raise ValueError('Screening references unknown passages')
            candidates={s['speech_id'] for s in speeches if any(p['passage_id'] in ids for p in s['passages'])}
        reason='current screening' if candidates is not None else 'screening unavailable/stale; full review fallback'
    elif mode=='screened_speeches':reason='screening unavailable; full review fallback'
    selected={};groups=defaultdict(list)
    for s in speeches:
        if candidates is None or s['speech_id'] in candidates:selected[s['speech_id']]='full' if candidates is None else 'screen_candidate'
        else:groups[stratum(s)].append(s)
    count=settings.get('negative_sample_per_stratum',2)
    if count<1:raise ValueError('At least one negative speech per stratum must be sampled')
    rank=lambda s:stable_hash([seed,s['speech_id'],s['sha256']])
    for group in groups.values():
        for s in sorted(group,key=rank)[:count]:selected[s['speech_id']]='negative_audit_sample'
    audit_percent=settings.get('second_review_percent',10)
    if not 0<=audit_percent<=100:raise ValueError('Invalid second review percentage')
    rows=[]
    for s in speeches:
        why=selected.get(s['speech_id'],'not_selected')
        double=why=='negative_audit_sample' or int(rank(s)[:8],16)%100<audit_percent
        passes=2 if primary==2 or double else 1
        rows.append(dict(speech_id=s['speech_id'],selection=why,passes=passes if why!='not_selected' else 0,stratum=list(stratum(s))))
    return dict(scope=mode,screening_status=reason,seed=seed,rows=rows,
        selected_speeches=len(selected),unselected_speeches=len(speeches)-len(selected),
        infer_population_prevalence=False,negative_sample_per_stratum=count)
