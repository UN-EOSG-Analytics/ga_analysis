import json
from pathlib import Path
from unga_analysis.analysis.common import save, check_schema

JOBS = json.loads((Path(__file__).parent / 'review_assignment_0.json').read_text())


def write(index, findings):
    job = JOBS[index]
    request = json.loads(Path(job['request']).read_text(encoding='utf-8'))
    passages = request['payload']['passages']
    rows = []
    for paragraph, status, kind, quote, rationale in findings:
        assert quote in passages[paragraph]['text'] and len(quote.split()) <= 80
        rows.append(dict(passage_id=passages[paragraph]['passage_id'], status=status,
                         mention_type=kind, quote=quote, rationale=rationale))
    value = dict(complete=True, reviewed_passage_ids=[p['passage_id'] for p in passages], findings=rows)
    check_schema(value, request['schema'])
    save(job['response'], dict(request_hash=request['request_hash'], reviewer=dict(
        environment='codex_subscription', model='not_reported', reasoning_effort='not_reported',
        human_reviewed=False, agent='root'), value=value))
    print('Saved', index, request['payload']['speech_id'], len(rows))


def read(index, start=0, end=None):
    request = json.loads(Path(JOBS[index]['request']).read_text(encoding='utf-8'))
    payload = request['payload']
    print('JOB', index, request['stage'], payload['speech_id'])
    print('BEFORE', payload['preceding_context'])
    for k, paragraph in enumerate(payload['passages']):
        if k >= start and (end is None or k < end): print(k, paragraph['text'])
    print('AFTER', payload['following_context'])
