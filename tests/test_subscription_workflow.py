from pathlib import Path
from unittest.mock import Mock,patch
import json
import unittest

from tests.helpers import TemporaryWorkspace
from tests.test_analysis_workflow import fixture,FixtureProvider
from unga_analysis.analysis.common import save,obj,STR
from unga_analysis.analysis.subscription import SubscriptionProvider,AwaitingSubscriptionWork
from unga_analysis.analysis.provider import OpenAIProvider
from unga_analysis.analysis.costs import estimate_costs
from unga_analysis.analysis.workflow import run
from unga_analysis.io import digest


def subscription_fixture(root):
    rows,cfg=fixture(root);cfg['execution'].update(text_backend='codex_subscription',api_scope='embeddings_only',subscription_pending_limit=16)
    cp=Path(root)/'config/analysis.toml'
    cp.write_text(cp.read_text(encoding='utf-8').replace('text_backend = "openai_api"','text_backend = "codex_subscription"').replace('api_scope = "text_and_embeddings"','api_scope = "embeddings_only"'),encoding='utf-8')
    return rows,cfg


class SubscriptionWorkflowTests(unittest.TestCase):
    def test_text_api_is_blocked_even_with_an_injected_client(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=subscription_fixture(tmp);client=Mock()
            provider=OpenAIProvider(tmp,cfg,execute=True,client=client)
            with self.assertRaisesRegex(ValueError,'Text-generation API is disabled'):provider.json('review',{},obj(text=STR),'Review')
            client.responses.create.assert_not_called()

    def test_queue_and_response_hash_validation_need_no_api_client(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=subscription_fixture(tmp)
            with patch('openai.OpenAI',side_effect=AssertionError('No real client')):
                provider=SubscriptionProvider(tmp,cfg)
                with self.assertRaises(AwaitingSubscriptionWork):provider.json('review',{'text':'Source'},obj(text=STR),'Read source')
                job=next(iter(provider.pending.values()));request=json.loads(Path(job['request']).read_text())
                save(job['response'],dict(request_hash='wrong',reviewer={'environment':'codex_subscription','model':'fixture','human_reviewed':False},value={'text':'Source'}))
                with self.assertRaisesRegex(ValueError,'hash mismatch'):provider.json('review',{'text':'Source'},obj(text=STR),'Read source')
                save(job['response'],dict(request_hash=request['request_hash'],reviewer={'environment':'codex_subscription','model':'fixture','human_reviewed':False},value={'text':'Source'}))
                self.assertEqual(provider.json('review',{'text':'Source'},obj(text=STR),'Read source'),{'text':'Source'})

    def test_subscription_estimate_bills_embeddings_only(self):
        with TemporaryWorkspace() as tmp:
            rows,cfg=subscription_fixture(tmp);cost=estimate_costs(tmp,rows,cfg)
            for stage,details in cost['stages'].items():
                if stage!='embeddings':self.assertEqual(details['direct_api_requests_upper'],0)
            self.assertEqual(cost['upper_usd'],round(cost['stages']['embeddings']['scenarios']['3000']['upper_usd'],4))

    def test_pending_queue_is_bounded_without_fabricating_answers(self):
        with TemporaryWorkspace() as tmp:
            _,cfg=subscription_fixture(tmp);cfg['execution']['subscription_pending_limit']=2;provider=SubscriptionProvider(tmp,cfg)
            for i in range(5):
                with self.assertRaises(AwaitingSubscriptionWork):provider.json('review',{'id':i},obj(text=STR),'Read')
            self.assertEqual(len(list(provider.path.glob('*.request.json'))),2)
            self.assertEqual(len(list(provider.path.glob('*.response.json'))),0)

    def test_subscription_handoffs_resume_through_report_with_fake_embeddings(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);_,cfg=subscription_fixture(root);fake=FixtureProvider();before=digest(root/'output/pipeline/speeches.jsonl')
            with patch('openai.OpenAI',side_effect=AssertionError('No real client')):
                for _ in range(30):
                    provider=SubscriptionProvider(root,cfg,embedding_provider=fake)
                    result=run(root,execute=True,provider=provider,fetch_current=False)
                    if result['state']=='complete':break
                    self.assertEqual(result['state'],'awaiting_subscription_review')
                    self.assertTrue(result['pending'])
                    for job in result['pending']:
                        request=json.loads(Path(job['request']).read_text(encoding='utf-8'))
                        value=fake.json(request['stage'],request['payload'],request['schema'],request['instructions'],max_tokens=request['max_tokens'])
                        save(job['response'],dict(request_hash=request['request_hash'],reviewer={'environment':'codex_subscription','model':'offline_fixture','reasoning_effort':'none','human_reviewed':False},value=value))
                else:self.fail('Subscription handoff did not finish')
            self.assertEqual(result['publication']['pdf_pages'],4)
            self.assertEqual(digest(root/'output/pipeline/speeches.jsonl'),before)
