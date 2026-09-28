from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import json
import unittest

from tests.helpers import TemporaryWorkspace
from tests.test_analysis_workflow import fixture,FixtureProvider
from unga_analysis.analysis.provider import OpenAIProvider,ResponseUnavailable
from unga_analysis.analysis.review import review_speech,review_all
from unga_analysis.analysis.classification import classify_one
from unga_analysis.analysis.common import obj,STR
from unga_analysis.io import read_jsonl


def response(value=None,reason=None,refusal=False):
    return NS(status='incomplete' if reason else 'completed',incomplete_details=NS(reason=reason),
        output=[{'type':'message','content':[{'type':'refusal','refusal':'fixture'}]}] if refusal else [],
        output_text=json.dumps(value),id='fixture',usage=NS(input_tokens=100,output_tokens=6000 if reason else 100))


class ResponseRecoveryTests(unittest.TestCase):
    def test_incomplete_request_is_cached_and_charged_once_across_resume(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=fixture(tmp);client=Mock();client.responses.create.return_value=response(reason='max_output_tokens')
            for _ in range(2):
                provider=OpenAIProvider(tmp,cfg,execute=True,budget=2,client=client)
                with self.assertRaises(ResponseUnavailable):provider.json('fixture',{},obj(value=STR),'fixture')
            self.assertEqual(client.responses.create.call_count,1)
            ledger=list(read_jsonl(provider.ledger))
            self.assertEqual(len(ledger),2)
            self.assertAlmostEqual(sum(r['charged_or_reserved_usd'] for r in ledger),.027075)

    def test_truncation_splits_with_context_and_resume_reuses_all_requests(self):
        with TemporaryWorkspace() as tmp:
            rows,cfg=fixture(tmp);client=Mock();captured=[]
            def reply(**kwargs):
                payload=json.loads(kwargs['input']);captured.append(payload)
                if len(payload['passages'])>1:return response(reason='max_output_tokens')
                p=payload['passages'][0]
                return response(dict(complete=True,reviewed_passage_ids=[p['passage_id']],findings=[dict(passage_id=p['passage_id'],status='Yes',mention_type='explicit',quote=p['text'],rationale='Fixture review.')]))
            client.responses.create.side_effect=reply
            provider=OpenAIProvider(tmp,cfg,execute=True,budget=2,client=client)
            rr=review_speech(rows[0],provider,cfg)
            self.assertEqual([r['ai_status'] for r in rr],['Yes','Yes'])
            self.assertEqual(client.responses.create.call_count,6)
            children=[p for p in captured if len(p['passages'])==1]
            self.assertEqual(children[0]['following_context'],rows[0]['passages'][1]['text'])
            self.assertEqual(children[1]['preceding_context'],rows[0]['passages'][0]['text'])
            spent=provider.used
            resumed=OpenAIProvider(tmp,cfg,execute=True,budget=2,client=client)
            self.assertEqual(review_speech(rows[0],resumed,cfg),rr)
            self.assertEqual(client.responses.create.call_count,6);self.assertAlmostEqual(resumed.used,spent)
            ledger=list(read_jsonl(provider.ledger))
            self.assertAlmostEqual(spent,sum(r['actual_cost_usd'] for r in ledger if r['state']=='settled'))

    def test_single_passage_truncation_or_refusal_is_uncertain_not_no(self):
        for reason,refusal in [('max_output_tokens',False),(None,True)]:
            with self.subTest(reason=reason,refusal=refusal),TemporaryWorkspace() as tmp:
                root=Path(tmp);rows,cfg=fixture(root);client=Mock()
                client.responses.create.return_value=response(reason=reason,refusal=refusal)
                provider=OpenAIProvider(tmp,cfg,execute=True,budget=2,client=client)
                rr=review_all(rows[:1],provider,cfg,root/'review')
                self.assertTrue(all(r['ai_status']=='Uncertain' and not r['human_reviewed'] for r in rr))
                self.assertTrue(all(not v['reviewed'] and v['quote']=='' for r in rr for v in r['reviews']))
                summary=json.loads((root/'review/ai_review_summary.json').read_text())
                self.assertFalse(summary['all_passages_reviewed']);self.assertTrue(summary['all_passages_attempted'])

    def test_unclassified_refusal_does_not_become_empty_keyword_negative(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=fixture(root)
            record=review_speech(rows[0],FixtureProvider(),cfg)[0]
            client=Mock();client.responses.create.return_value=response(refusal=True)
            provider=OpenAIProvider(tmp,cfg,execute=True,budget=2,client=client)
            result=classify_one(record,provider,{'codes':{'GOV':{'label':'Governance'}}},cfg,None)
            self.assertEqual(result['themes'],{'GOV':'Uncertain'})
            self.assertFalse(result['keyword_review_complete']);self.assertFalse(result['classification_complete'])

    def test_unknown_incomplete_reason_stops_without_inventing_verdict(self):
        with TemporaryWorkspace() as tmp:
            rows,cfg=fixture(tmp);client=Mock();client.responses.create.return_value=response(reason='unknown_failure')
            provider=OpenAIProvider(tmp,cfg,execute=True,budget=2,client=client)
            with self.assertRaises(ResponseUnavailable):review_speech(rows[0],provider,cfg)
