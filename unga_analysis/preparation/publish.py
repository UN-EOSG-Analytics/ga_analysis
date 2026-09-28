"""Single local preparation workflow for the user-confirmed English corpus."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json

from . import segment
from .segment import ROOT, OUT, RAW, dump, table
from ..contracts import validate_manifest
from ..io import digest, read_jsonl, write_jsonl
from ..pipeline import ingest, status, config


def prepare(root=ROOT):
    if Path(root).resolve()!=ROOT.resolve():
        raise ValueError('Run prepare from this project checkout; alternate --root is unsupported')
    rows=segment.main()
    validate_manifest(rows)
    cfg=config(ROOT)
    issues=json.loads((OUT/'segmentation_issues.json').read_text(encoding='utf8'))
    unresolved=[r for r in issues if not r['reason'].startswith('excluded_')]
    unresolved += [dict(source_id=r['source_id'],reason=r['readiness_issue']) for r in rows if r['status']!='accepted']
    counts=Counter(str(r['year']) for r in rows if r['status']=='accepted')
    for year,minimum in cfg['sources'].get('minimum_expected_speeches',{}).items():
        if counts[year]<minimum:unresolved.append(dict(year=year,reason='speech_count_below_confirmed_holdings',count=counts[year],minimum=minimum))
    if unresolved:
        dump(OUT/'preparation_blockers.json',unresolved)
        raise ValueError(f'{len(unresolved)} unresolved source boundaries/versions; see preparation_blockers.json')
    for r in rows:
        if digest(ROOT/r['path'])!=r['sha256']:raise ValueError('Derived source changed before publication')
    write_jsonl(ROOT/'config/source_manifest.jsonl',rows)
    result=ingest(ROOT)
    if result['unresolved']:raise ValueError('Ingestion errors; see output/pipeline/ingestion_issues.jsonl')
    inventory=[]
    for p in sorted(RAW.glob('UNGA*/*.pdf')):
        year=int(p.parent.name[-4:]);meeting=int(p.stem.split('_')[3]);excluded=year==2021 and meeting in (5,8)
        inventory.append(dict(year=year,source_type='official_transcript',path=p.relative_to(ROOT).as_posix(),
            sha256=digest(p),eligible=not excluded,detail=f'A/{year-1945}/PV.{meeting}'+('; Durban anniversary' if excluded else '')))
    for p in sorted((RAW/'automatic_transcripts_unofficial').glob('*_ASR.*')):
        if p.suffix not in ('.json','.txt'):continue
        inventory.append(dict(year=int(p.name[4:8]),source_type='automatic_transcript',path=p.relative_to(ROOT).as_posix(),
            sha256=digest(p),eligible=True,detail='user-confirmed primary; automated text accuracy unverified'))
    table(OUT/'meeting_inventory.csv',inventory)
    # The retrieval manifest records reception; current processing status is explicit.
    mp=RAW/'automatic_transcripts_unofficial/manifest.json'
    if mp.exists():
        m=json.loads(mp.read_text(encoding='utf8'))
        used={r['origin_file'] for r in rows}
        for day in m.get('days',[]):
            stem=f"UNGA{day['year']}_day{day['day']}_EN_ASR"
            files=[p for p in used if Path(p).stem==stem]
            if files:
                day.update(canonical_files=sorted(files),preprocessing_status='segmented_and_ingested',
                    source_acceptance='user_confirmed_primary',review_status='unverified_ASR')
        dump(mp,m)
    from .audit import main as audit
    integrity=audit()
    from ..screening import screen
    screening=screen(ROOT)
    report=dict(prepared_at_utc=datetime.now(timezone.utc).isoformat(),ingestion=result,status=status(ROOT),
        manifest='config/source_manifest.jsonl',analysis_input='output/pipeline/speeches.jsonl',
        counts_by_year=dict(Counter(str(r['year']) for r in rows)),source_counts=dict(Counter(r['source_type'] for r in rows)),
        source_policy='All selected English transcripts are canonical originals; retain official/automatic source identity.',
        partial_years=cfg['scope']['partial_years'],integrity_issues=len(integrity['issues']),
        candidate_screening=screening,paid_api_calls=0,classification_performed=False)
    dump(OUT/'release_status.json',report)
    dump(OUT/'preparation_blockers.json',[])
    return report
