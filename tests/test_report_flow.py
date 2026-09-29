from pathlib import Path
from unittest.mock import patch
import unittest
import json

from tests.helpers import TemporaryWorkspace
from tests.test_analysis_workflow import fixture,FixtureProvider
from unga_analysis.analysis.workflow import run
from unga_analysis.analysis.reporting import TITLES,pages,charts,render,source_notes,draft_report


def long_report():
    sections=[]
    counts=[2,6,4,2]
    for title,count in zip(TITLES,counts):
        paragraphs=[dict(text=' '.join(['Synthetic layout fixture only; no actual country finding is represented.']*10),
            evidence_ids=[],reference_ids=[],metric_keys=['annual:1']) for _ in range(count)]
        sections.append(dict(title=title,paragraphs=paragraphs))
    return dict(sections=sections,recommendations=[dict(addressee='SPMU',action='Inspect synthetic evidence.',rationale=' '.join(['This is a layout fixture, not a real policy recommendation.']*5),evidence_ids=[],metric_keys=['annual:1']) for _ in range(5)],
        citations={'annual:1':{'number':1,'source':{'year':2017,'n':1,'N':2}}})


class ReportFlowTests(unittest.TestCase):
    def test_dense_content_can_use_five_or_six_pages(self):
        with TemporaryWorkspace() as tmp:
            sections=[[('title',title)]+[('paragraph',' '.join(['Synthetic source grounded assessment supports this layout check.']*12)) for _ in range(8)] for title in TITLES]
            publication=render(sections,Path(tmp)/'dense','synthetic_dense',use_word=False)
            self.assertIn(publication['pdf_pages'],(5,6))

    def test_six_theme_paragraphs_flow_beyond_four_pages_without_shrinking(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);fixture(root);result=run(root,execute=True,provider=FixtureProvider(),fetch_current=False,stop_after='aggregate')
            out=Path(result['output']);stats=json.loads((out/'aggregates.json').read_text())
            destination=root/'layout';destination.mkdir();report=long_report()
            figures=charts(stats,destination);sections=pages(report,stats,[],[],[],figures)
            publication=render(sections,destination,'synthetic_long',use_word=False)
            self.assertGreaterEqual(publication['pdf_pages'],4);self.assertLessEqual(publication['pdf_pages'],6)
            self.assertTrue(all(s==10.5 for s in publication['font_sizes']))
            from docx import Document
            document=Document(publication['docx'])
            drawing_paragraphs=[p for p in document.paragraphs if p._p.xpath('.//w:drawing')]
            self.assertEqual(len(drawing_paragraphs),2)
            self.assertTrue(all(p.paragraph_format.line_spacing==1.0 for p in drawing_paragraphs))
            import fitz
            with fitz.open(publication['pdf']) as doc:
                text='\n'.join(p.get_text() for p in doc)
                self.assertNotIn('annual:1',text);self.assertIn('[1]',text)
            note=source_notes(report,destination);self.assertIn('2017',Path(note).read_text())

    def test_theme_budget_accepts_six_grounded_paragraphs_and_rejects_thin_themes(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);fixture(root);result=run(root,execute=True,provider=FixtureProvider(),fetch_current=False,stop_after='aggregate')
            out=Path(result['output']);stats=json.loads((out/'aggregates.json').read_text())
            taxonomy={'codes':{f'THEME{i}':{'label':f'Theme {i}'} for i in range(6)}}
            class ReportProvider:
                def __init__(self,thin=False):self.thin=thin
                def json(self,*args,**kwargs):
                    report=long_report();report.pop('citations')
                    if self.thin:report['sections'][1]['paragraphs']=report['sections'][1]['paragraphs'][:1]
                    return report
            report=draft_report(stats,[],[],taxonomy,[],ReportProvider(),out)
            self.assertEqual(len(report['sections'][1]['paragraphs']),6)
            with self.assertRaisesRegex(ValueError,'Themes needs'):draft_report(stats,[],[],taxonomy,[],ReportProvider(True),out)

    def test_layout_overflow_requests_a_grounded_revision(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);fixture(root)
            from unga_analysis.analysis import reporting
            original=reporting.render;calls=[]
            def first_overflows(*args,**kwargs):
                calls.append(True)
                if len(calls)==1:raise ValueError('Report has 7 pages; revise within 4-6 pages')
                return original(*args,**kwargs)
            provider=FixtureProvider()
            with patch.object(reporting,'render',side_effect=first_overflows):result=run(root,execute=True,provider=provider,fetch_current=False)
            self.assertEqual(result['state'],'complete');self.assertIn('report_layout_revision',provider.calls)

    def test_report_rejects_fabricated_quotation_even_with_valid_metric_key(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);fixture(root);result=run(root,execute=True,provider=FixtureProvider(),fetch_current=False,stop_after='aggregate')
            out=Path(result['output']);stats=json.loads((out/'aggregates.json').read_text())
            provider=FixtureProvider();original=provider.json
            def reply(*args,**kwargs):
                value=original(*args,**kwargs);value['sections'][0]['paragraphs'][0]['text']='An invented "source quotation".'
                return value
            provider.json=reply
            with self.assertRaisesRegex(ValueError,'quotation must match'):draft_report(stats,[],[],{'codes':{}},[],provider,out)
