from pathlib import Path
from copy import deepcopy
import unittest

from tests.helpers import TemporaryWorkspace
from tests.defect_fixtures import disagreement_fixture,DisagreementProvider
from tests.test_analysis_workflow import FixtureProvider
from unga_analysis.analysis.review import review_all
from unga_analysis.analysis.classification import classify_all
from unga_analysis.analysis.aggregation import aggregate
from unga_analysis.analysis.workflow import ancillary
from unga_analysis.analysis.reporting import charts


class ThemeDenominatorTests(unittest.TestCase):
    def prepare(self,root,n=24,provider=None):
        speeches,cfg,tax=disagreement_fixture(root,n)
        provider=provider or DisagreementProvider()
        reviewed=review_all(speeches,provider,cfg,root/'review')
        classified=classify_all(reviewed,tax,{},provider,cfg,root/'classify')
        return speeches,cfg,tax,reviewed,classified

    def test_one_disputed_code_preserves_other_code_denominators(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg,tax,rr,cc=self.prepare(root)
            stats,_,_,matrix=aggregate(rows,rr,cc,tax,cfg,root/'out',allow_partial=True)
            by_code={r['code']:r for r in stats['theme_prevalence']}
            self.assertEqual(by_code['THEME00']['N'],0)
            self.assertEqual(by_code['THEME01']['N'],24)
            self.assertEqual(by_code['THEME01']['n'],24)
            self.assertTrue(all(r['THEME00'] is None for r in matrix))
            pair=next(r for r in stats['cooccurrence'] if r['theme_a']=='THEME01' and r['theme_b']=='THEME02')
            self.assertEqual((pair['N'],pair['n_both']),(24,24))
            self.assertTrue(all(r['N']==0 for r in stats['cooccurrence'] if r['theme_a']=='THEME00'))
            charts(stats,root/'out') # Mixed percentage availability must remain renderable.

    def test_zero_requires_only_its_code_no_and_complete_ai_review(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg,tax,rr,cc=self.prepare(root,2)
            for r in cc:r['themes']['THEME01']='No'
            rr[-1]['ai_status']='Uncertain'
            _,_,_,matrix=aggregate(rows,rr,cc,tax,cfg,root/'out',allow_partial=True)
            self.assertEqual(matrix[0]['THEME01'],0)
            self.assertIsNone(matrix[1]['THEME01'])
            self.assertEqual(matrix[1]['THEME02'],1) # Reviewed Yes survives another uncertain passage.

    def test_uncovered_concept_is_queued_without_invalidating_codes(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);provider=FixtureProvider();original=provider.json
            def reply(stage,*args,**kwargs):
                result=original(stage,*args,**kwargs)
                if stage.startswith('classify_'):result['uncovered_concept']='A possible new concept'
                return result
            provider.json=reply
            rows,cfg,tax,rr,cc=self.prepare(root,1,provider)
            self.assertTrue(cc[0]['classification_complete'])
            stats,*_=aggregate(rows,rr,cc,tax,cfg,root/'out',allow_partial=True)
            ancillary(root,root/'out',rows,rr,cc,tax,stats,{'dependencies':{}},cfg)
            self.assertIn('Uncovered concept: A possible new concept',(root/'out/review_queue.csv').read_text(encoding='utf-8-sig'))
            self.assertTrue(all(r['N']==1 for r in stats['theme_prevalence']))

    def test_matched_panel_uses_each_codes_common_resolved_countries(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg,tax,rr,cc=self.prepare(root,2)
            old_rows=deepcopy(rows);old_rr=deepcopy(rr);old_cc=deepcopy(cc)
            for s in old_rows:
                s.update(year=2025,speech_id=s['speech_id'].replace('2026','2025'))
                for p in s['passages']:p.update(speech_id=s['speech_id'],passage_id=p['passage_id'].replace('2026','2025'))
            for r in old_rr+old_cc:r.update(year=2025,speech_id=r['speech_id'].replace('2026','2025'),passage_id=r['passage_id'].replace('2026','2025'))
            stats,*_=aggregate(old_rows+rows,old_rr+rr,old_cc+cc,tax,cfg,root/'out',allow_partial=True)
            panel={r['code']:r for r in stats['matched_panel']}
            self.assertEqual(panel['THEME00']['N'],0);self.assertEqual(panel['THEME01']['N'],2)
