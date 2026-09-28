from pathlib import Path
from unittest.mock import patch
import json
import unittest

from tests.helpers import TemporaryWorkspace
from tests.test_analysis_workflow import fixture,FixtureProvider
from unga_analysis.io import digest,write_jsonl
from unga_analysis.analysis.common import save
from unga_analysis.analysis.costs import estimate_costs
from unga_analysis.analysis.review import review_speech
from unga_analysis.analysis.classification import classify_one
from unga_analysis.analysis.workflow import preflight


class CostEstimateTests(unittest.TestCase):
    def test_unique_screening_passages_and_all_stages_are_counted(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=fixture(root);pid=rows[0]['passages'][0]['passage_id']
            write_jsonl(root/'output/screening/ai_candidates.jsonl',[{'evidence':[{'passage_id':pid}]}]*2)
            save(root/'output/screening/summary.json',{'input_sha256':digest(root/'output/pipeline/speeches.jsonl')})
            with patch('openai.OpenAI',side_effect=AssertionError('Real client forbidden')):result=estimate_costs(root,rows,cfg)
            self.assertEqual(result['measured']['candidate_unique_passages'],1)
            self.assertEqual(result['stages']['classification']['requests_lower'],2)
            self.assertEqual(result['measured']['review_requests'],16)
            self.assertEqual(set(result['stages']),{'review','embeddings','discovery','taxonomy','classification','references','report'})
            self.assertEqual(set(result['total_scenarios']),{'900','2000','3000'})
            for scenario,total in result['total_scenarios'].items():
                self.assertAlmostEqual(total['lower_usd'],sum(s['scenarios'][scenario]['lower_usd'] for s in result['stages'].values()),places=4)

    def test_preflight_measures_exact_review_payload_and_does_not_call_client(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=fixture(root);provider=FixtureProvider();original=provider.json;counts=[]
            def capture(stage,payload,schema,instructions,**kwargs):
                counts.append(len(json.dumps(payload,ensure_ascii=False))+len(instructions)+len(json.dumps(schema)))
                return original(stage,payload,schema,instructions,**kwargs)
            provider.json=capture
            for row in rows:review_speech(row,provider,cfg)
            before=digest(root/'output/pipeline/speeches.jsonl')
            with patch('openai.OpenAI',side_effect=AssertionError('Real client forbidden')):result=preflight(root)
            self.assertEqual(result['cost_estimate']['measured']['review_input_characters'],sum(counts))
            self.assertEqual(digest(root/'output/pipeline/speeches.jsonl'),before)
            self.assertEqual(result['paid_calls_performed'],0)

    def test_missing_screening_does_not_estimate_zero_classification(self):
        with TemporaryWorkspace() as tmp:
            rows,cfg=fixture(tmp);costs=estimate_costs(tmp,rows,cfg)
            self.assertEqual(costs['measured']['candidate_unique_passages'],16)
            review=costs['stages']['review'];difference=review['scenarios']['3000']['lower_usd']-review['scenarios']['900']['lower_usd']
            self.assertAlmostEqual(difference,16*2100*cfg['execution']['review_output_usd_per_million']/1e6)

    def test_no_can_omit_rationale_but_yes_and_uncertain_need_evidence(self):
        with TemporaryWorkspace() as tmp:
            rows,cfg=fixture(tmp);record=review_speech(rows[0],FixtureProvider(),cfg)[0]
            for label in ('No','Yes','Uncertain'):
                provider=FixtureProvider();original=provider.json
                def reply(stage,*args,**kwargs):
                    value=original(stage,*args,**kwargs)
                    for t in value['themes']:t.update(value=label,quote='',rationale='')
                    return value
                provider.json=reply;taxonomy={'codes':{'GOV':{'label':'Governance'}}}
                if label=='No':self.assertEqual(classify_one(record,provider,taxonomy,cfg,None)['themes'],{'GOV':'No'})
                else:
                    with self.assertRaises(ValueError):classify_one(record,provider,taxonomy,cfg,None)
