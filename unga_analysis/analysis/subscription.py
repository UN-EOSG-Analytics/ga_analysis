"""File handoff to an interactive Codex session; only embeddings use an API."""
from pathlib import Path
from threading import RLock
import json
import math

from ..io import stable_hash,read_jsonl
from .common import save,check_schema


class AwaitingSubscriptionWork(RuntimeError):
    pass


class SubscriptionProvider:
    def __init__(self,root,cfg,budget=None,embedding_provider=None):
        self.root=Path(root);self.cfg=cfg;settings=cfg['execution']
        self.path=self.root/settings['output_directory']/'subscription_queue'
        self.path.mkdir(parents=True,exist_ok=True)
        self.limit=float(budget if budget is not None else settings['default_cost_limit_usd'])
        if not math.isfinite(self.limit) or self.limit<=0:raise ValueError('Cost limit must be positive and finite')
        self.embedding_provider=embedding_provider;self.lock=RLock()
        self.pending_limit=settings.get('subscription_pending_limit',16)
        if self.pending_limit<1:raise ValueError('subscription_pending_limit must be positive')
        self.pending={}
        ledger=self.root/settings['output_directory']/'api_cache/usage.jsonl'
        self.initial_used=sum(r['charged_or_reserved_usd'] for r in read_jsonl(ledger)) if ledger.exists() else 0.0

    @property
    def used(self):return getattr(self.embedding_provider,'used',self.initial_used)

    def collect(self,jobs):
        """Export every independent request before yielding to the subscription session."""
        original=self.pending_limit;self.pending_limit=float('inf')
        try:
            for stage,payload,schema,instructions,max_tokens in jobs:
                try:self.json(stage,payload,schema,instructions,max_tokens)
                except AwaitingSubscriptionWork:pass
        finally:self.pending_limit=original
        if self.pending:raise AwaitingSubscriptionWork('Complete the stage request manifest, then resume')

    def json(self,stage,payload,schema,instructions,max_tokens=None):
        request=dict(backend='codex_subscription',stage=stage,payload=payload,schema=schema,instructions=instructions,
            model_preference=self.cfg['execution'].get('subscription_model_preference','gpt-6-astra'),
            reasoning_preference=self.cfg['execution'].get('subscription_reasoning_preference','high'),max_tokens=max_tokens)
        key=stable_hash(request);job=self.path/(key+'.request.json');answer=self.path/(key+'.response.json')
        if answer.exists():
            result=json.loads(answer.read_text(encoding='utf-8'))
            reviewer=result.get('reviewer',{})
            if result.get('request_hash')!=key:raise ValueError('Subscription response request hash mismatch')
            if reviewer.get('environment')!='codex_subscription' or reviewer.get('human_reviewed') is not False or not reviewer.get('model'):
                raise ValueError('Record actual subscription reviewer model/environment; never claim human verification')
            check_schema(result['value'],schema)
            return result['value']
        with self.lock:
            if key not in self.pending and len(self.pending)<self.pending_limit:
                if not job.exists():save(job,dict(request_hash=key,**request,response_path=answer.name,
                    response_contract={'request_hash':key,'reviewer':{'environment':'codex_subscription','model':'ACTUAL_MODEL_OR_not_reported','reasoning_effort':'ACTUAL_SETTING_OR_not_reported','human_reviewed':False},'value':'Fill according to schema after reading all supplied source text.'}))
                self.pending[key]=dict(stage=stage,request=str(job),response=str(answer))
        raise AwaitingSubscriptionWork('Read pending request files in the subscribed Codex session, write validated response envelopes, then resume; no text API fallback')

    def embed(self,records):
        if not records:return []
        if self.embedding_provider is None:
            from .provider import OpenAIProvider
            self.embedding_provider=OpenAIProvider(self.root,self.cfg,execute=True,budget=self.limit)
        return self.embedding_provider.embed(records)
