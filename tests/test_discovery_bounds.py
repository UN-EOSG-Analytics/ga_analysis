from pathlib import Path
import json
import unittest

from tests.helpers import TemporaryWorkspace
from tests.test_analysis_workflow import fixture
from tests.defect_fixtures import DiscoveryCapture
from unga_analysis.analysis.discovery import discover,consolidate


class DiscoveryBoundsTests(unittest.TestCase):
    def test_900_passage_fallback_bounds_merge_and_audit_to_cited_sources(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=fixture(tmp);provider=DiscoveryCapture()
            rows=[dict(passage_id=f'p{i}',speech_id=f's{i}',text=('Artificial intelligence governance. '*50)[:1500],source_sha256='fixture') for i in range(900)]
            discover(rows,provider,cfg,Path(tmp)/'out')
            requests=[(stage,p) for stage,p in provider.payloads if stage in ('taxonomy_merge','taxonomy_audit')]
            self.assertGreater(sum(stage=='taxonomy_merge' for stage,_ in requests),1)
            for stage,payload in requests:
                themes=payload['proposals'] if stage=='taxonomy_merge' else payload['proposed']['themes']
                cited={e['passage_id'] for t in themes for e in t['examples']}
                self.assertEqual({r['passage_id'] for r in payload['examples']},cited)
                self.assertLessEqual(len(json.dumps(payload,ensure_ascii=False)),cfg['discovery']['taxonomy_payload_max_chars'])
                self.assertLess(len(cited),900)

    def test_uncited_source_is_rejected_even_if_present_in_original_corpus(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=fixture(tmp);provider=DiscoveryCapture();original=provider.json
            theme=original('taxonomy_merge',{'examples':[{'passage_id':'p0','text':'AI governance.'}]},None,None)['themes'][0]
            def bad(stage,payload,*args,**kwargs):
                result=original(stage,payload,*args,**kwargs)
                result['themes'][0]['examples']=[dict(passage_id='p1',quote='Uncited original source.')]
                return result
            provider.json=bad
            with self.assertRaisesRegex(ValueError,'exact source quotation'):
                consolidate([theme],{'p0':'AI governance.','p1':'Uncited original source.'},provider,cfg,{})

    def test_single_oversize_proposal_stops_before_any_request(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=fixture(tmp);provider=DiscoveryCapture()
            theme=provider.json('taxonomy_merge',{'examples':[dict(passage_id='p0',text='AI governance.')]},None,None)['themes'][0]
            provider.calls.clear();cfg['discovery']['taxonomy_payload_max_chars']=20
            with self.assertRaisesRegex(ValueError,'single taxonomy proposal'):
                consolidate([theme],{'p0':'AI governance.'},provider,cfg,{})
            self.assertEqual(provider.calls,[])

    def test_nonshrinking_merge_cannot_loop_forever(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=fixture(tmp);provider=DiscoveryCapture();themes=[];source={}
            for i in range(4):
                source[f'p{i}']='AI governance. '*100
                t=provider.json('taxonomy_merge',{'examples':[dict(passage_id=f'p{i}',text=source[f'p{i}'])]},None,None)['themes'][0]
                t['code']=f'CODE{i}';themes.append(t)
            cfg['discovery']['taxonomy_payload_max_chars']=5000;calls=[]
            def unchanged(stage,payload,*args,**kwargs):
                calls.append(stage);return dict(themes=payload['proposals'],rationale='Unchanged distinct concepts.')
            provider.json=unchanged
            with self.assertRaisesRegex(ValueError,'did not converge'):consolidate(themes,source,provider,cfg,{})
            self.assertEqual(len(calls),4)
