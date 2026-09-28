"""OpenAI transport with explicit spending authorization, durable caches and usage."""
import json
import math
import time
from threading import RLock
from pathlib import Path

from ..io import stable_hash, read_jsonl
from .common import key_from_env, save, now, check_schema


class BudgetExceeded(ValueError):
    pass


class OpenAIProvider:
    def __init__(self, root, cfg, execute=False, budget=None, client=None):
        if not execute:
            raise ValueError('Paid calls require explicit --execute authorization')
        self.root = Path(root)
        self.cfg = cfg
        self.settings = cfg['execution']
        self.limit = float(budget if budget is not None else self.settings['default_cost_limit_usd'])
        if not math.isfinite(self.limit) or self.limit <= 0:
            raise ValueError('Cost limit must be a positive finite number')
        self.path = self.root/self.settings['output_directory']/'api_cache'
        self.path.mkdir(parents=True, exist_ok=True)
        self.ledger = self.path/'usage.jsonl'
        self.used = sum(r['charged_or_reserved_usd'] for r in read_jsonl(self.ledger)) if self.ledger.exists() else 0.0
        if client is None:
            key = key_from_env(root, cfg['discovery']['api_key_env'])
            if not key:
                raise ValueError('Set OPENAI_API_KEY in project .env before execution')
            from openai import OpenAI
            client = OpenAI(api_key=key, max_retries=0, timeout=self.settings['request_timeout_seconds'])
        self.client = client
        self.lock = RLock()

    def log(self, key, stage, cost, **details):
        with self.lock:
            with self.ledger.open('a', encoding='utf-8') as f:
                f.write(json.dumps(dict(at=now(), key=key, stage=stage, charged_or_reserved_usd=cost, **details))+'\n')
            self.used += cost

    def reserve(self, key, stage, upper):
        with self.lock:
            if self.used + upper > self.limit:
                raise BudgetExceeded(f'Cost cap reached: used/reserved ${self.used:.3f}, next <= ${upper:.3f}, cap ${self.limit:.2f}. Cached work is preserved.')
            self.log(key, stage, upper, state='reserved')

    def json(self, stage, payload, schema, instructions, max_tokens=None):
        cap = max_tokens or self.settings['max_output_tokens']
        model = self.settings['review_model']
        request = dict(model=model, stage=stage, payload=payload, schema=schema,
                       instructions=instructions, max_tokens=cap, reasoning=self.settings['reasoning_effort'])
        key = stable_hash(request)
        path = self.path/(key+'.json')
        if path.exists():
            value = json.loads(path.read_text(encoding='utf-8'))['value']
            check_schema(value, schema)
            return value
        encoded = json.dumps(payload, ensure_ascii=False)
        # UTF-8 bytes bound token count conservatively; include schema and protocol overhead.
        upper_input = len((encoded+instructions+json.dumps(schema)).encode('utf-8'))+4096
        upper = (upper_input*self.settings['review_input_usd_per_million'] + cap*self.settings['review_output_usd_per_million'])/1e6
        for attempt in range(3):
            self.reserve(key, stage, upper)
            try:
                response = self.client.responses.create(
                    model=model, instructions=instructions, input=encoded, store=False,
                    reasoning={'effort':self.settings['reasoning_effort']}, max_output_tokens=cap,
                    text={'format':{'type':'json_schema','name':'analysis_result','strict':True,'schema':schema}})
            except Exception as exc:
                code = getattr(exc, 'status_code', None)
                error_code=getattr(exc,'code',None)
                if code in (400,401,403,404,429):
                    self.log(key, stage, -upper, state='not_billed_http_error', http_status=code)
                # Unknown transport outcomes retain their reservation; no silent retry/double charge.
                if code == 429 and error_code!='insufficient_quota' and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                safe_code=error_code if error_code in ('insufficient_quota','rate_limit_exceeded','invalid_api_key','model_not_found') else None
                raise RuntimeError(f'OpenAI request failed ({type(exc).__name__}, HTTP {code}, code {safe_code}); credentials and response body suppressed. Resume with the same command.') from None
            usage = response.usage
            cost = (usage.input_tokens*self.settings['review_input_usd_per_million'] + usage.output_tokens*self.settings['review_output_usd_per_million'])/1e6
            self.log(key, stage, cost-upper, state='settled', input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, actual_cost_usd=cost, response_id=response.id, model=model)
            if response.status != 'completed':
                raise ValueError('OpenAI response incomplete/refused; no analytical labels published')
            value = json.loads(response.output_text)
            check_schema(value, schema)
            save(path, dict(value=value, request_hash=key, model=model, usage={'input':usage.input_tokens,'output':usage.output_tokens}))
            return value
        raise RuntimeError('Rate limit retries exhausted')

    def embed(self, records):
        cfg = self.cfg['discovery']
        values, pending = {}, []
        for record in records:
            key = stable_hash(dict(model=cfg['model'], dimensions=cfg['dimensions'],
                                   text=record['embedding_text'], source_sha256=record['source_sha256'], version='ai-context-1'))
            path = self.path/(key+'.vector.json')
            if path.exists():
                values[record['passage_id']] = json.loads(path.read_text(encoding='utf-8'))['vector']
            else:
                pending.append((record, key, path))
        for offset in range(0, len(pending), self.settings['embedding_batch_size']):
            batch = pending[offset:offset+self.settings['embedding_batch_size']]
            texts = [r[0]['embedding_text'] for r in batch]
            if any(not t or len(t.encode('utf-8'))>8000 for t in texts) or sum(len(t.encode('utf-8')) for t in texts)>250000:
                raise ValueError('Embedding batch exceeds conservative token bounds')
            key = stable_hash([r[1] for r in batch])
            upper = sum(len(t.encode('utf-8')) for t in texts)*self.settings['embedding_usd_per_million']/1e6
            self.reserve(key, 'embeddings', upper)
            try:
                response = self.client.embeddings.create(model=cfg['model'], input=texts, dimensions=cfg['dimensions'], encoding_format='float')
            except Exception as exc:
                code = getattr(exc,'status_code',None)
                if code in (400,401,403,404,429):
                    self.log(key,'embeddings',-upper,state='not_billed_http_error',http_status=code)
                raise RuntimeError(f'Embedding request failed ({type(exc).__name__}, HTTP {code}); resume preserves cached vectors.') from None
            actual = response.usage.total_tokens*self.settings['embedding_usd_per_million']/1e6
            self.log(key,'embeddings',actual-upper,state='settled',input_tokens=response.usage.total_tokens,output_tokens=0,actual_cost_usd=actual,model=cfg['model'])
            indexed = {x.index:x.embedding for x in response.data}
            if set(indexed) != set(range(len(batch))):
                raise ValueError('Embedding response index mismatch')
            for i,(record,key,path) in enumerate(batch):
                vector = indexed[i]
                if len(vector)!=cfg['dimensions'] or not all(math.isfinite(v) for v in vector):
                    raise ValueError('Invalid embedding dimensions or values')
                save(path, dict(vector=vector, model=cfg['model'], dimensions=cfg['dimensions'], key=key))
                values[record['passage_id']] = vector
        for vector in values.values():
            if len(vector)!=cfg['dimensions'] or not all(math.isfinite(v) for v in vector):
                raise ValueError('Incompatible embedding cache')
        return [values[r['passage_id']] for r in records]
