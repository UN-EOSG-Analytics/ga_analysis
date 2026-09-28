"""Offline fixtures for the pre-execution defect audit; no real client."""
from copy import deepcopy
from tests.test_analysis_workflow import fixture,FixtureProvider


class DisagreementProvider(FixtureProvider):
    def json(self,stage,payload,*args,**kwargs):
        result=super().json(stage,payload,*args,**kwargs)
        if stage.startswith('classify_'):
            result['themes'][0]['value']='No' if stage=='classify_1' else 'Yes'
        return result


def disagreement_fixture(root,n=24):
    rows,cfg=fixture(root);speeches=[]
    for i in range(n):
        row=deepcopy(rows[0]);row.update(speech_id=f'2026_T{i:02}',country_iso3=f'T{i:02}',year=2026,origin_file=f'fixture_day{i%6+1}_EN.json')
        for j,p in enumerate(row['passages']):p.update(speech_id=row['speech_id'],passage_id=f'{row["speech_id"]}:{j}')
        speeches.append(row)
    taxonomy={'version':'fixture','codes':{f'THEME{i:02}':dict(label=f'Theme {i}',definition='AI governance.',inclusion='AI governance.',exclusion='Other.',boundary_cases='Read source.',examples=[]) for i in range(20)}}
    return speeches,cfg,taxonomy


class DiscoveryCapture(FixtureProvider):
    def __init__(self):super().__init__();self.payloads=[]
    def embed(self,rows):return [[1.,0.] for _ in rows]
    def json(self,stage,payload,*args,**kwargs):
        self.payloads.append((stage,deepcopy(payload)))
        return super().json(stage,payload,*args,**kwargs)
