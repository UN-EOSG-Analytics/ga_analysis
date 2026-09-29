"""Reproducible synthetic layout check; no real model client or corpus mutation."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.helpers import TemporaryWorkspace
from tests.test_analysis_workflow import fixture,FixtureProvider
from tests.test_report_flow import long_report
from unga_analysis.analysis.workflow import run
from unga_analysis.analysis.reporting import pages,charts,render,source_notes
from unga_analysis.analysis.common import save

destination=Path(__file__).parent/'layout'
destination.mkdir(parents=True,exist_ok=True)
with patch('openai.OpenAI',side_effect=AssertionError('Real client forbidden')):
    with TemporaryWorkspace() as tmp:
        root=Path(tmp);fixture(root)
        result=run(root,execute=True,provider=FixtureProvider(),fetch_current=False,stop_after='aggregate')
        stats=json.loads((Path(result['output'])/'aggregates.json').read_text())
        stats['theme_prevalence']=[dict(year=2026,theme=f'Synthetic theme {i}',code=f'T{i}',n=3,N=5,pct=None) for i in range(6)]
        stats['institution_stance_counts']=[dict(year=2026,mechanism=f'Synthetic mechanism {i}',stance='mention',n=3,countries=['SYNTHETIC']*3) for i in range(9)]
        institutions=[dict(year=2026,review_status='reviewed',mechanism='New body / synthetic',iso3='FIXTURE',requested_functions=['scientific assessment'],quote='Synthetic source quotation for layout testing only.',evidence_id=f'E{i:05}') for i in range(4)]
        report=long_report();figures=charts(stats,destination)
        checks=render(pages(report,stats,institutions,[],[],figures),destination,'SYNTHETIC_FINAL_LAYOUT',use_word=True)
        checks['synthetic_only']=True;checks['paid_api_calls']=0
        source_notes(report,destination);save(destination/'checks.json',checks)
        print(json.dumps(checks,indent=2))
