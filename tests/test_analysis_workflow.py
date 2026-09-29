from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import json
import shutil
import unittest
from unittest.mock import Mock

from tests.helpers import PROJECT,TemporaryWorkspace
from unga_analysis.io import write_jsonl,digest,read_jsonl
from unga_analysis.pipeline import config
from unga_analysis.analysis.common import key_from_env,quote_in,save
from unga_analysis.analysis.provider import OpenAIProvider,BudgetExceeded
from unga_analysis.analysis.aggregation import coverage_guard,aggregate
from unga_analysis.analysis.review import review_all
from unga_analysis.analysis.discovery import clusters,validate_taxonomy,discover
from unga_analysis.analysis.workflow import run,inputs


class FixtureProvider:
    """Synthetic responses only. Never imports or calls the OpenAI client."""
    def __init__(self):self.calls=[]
    def json(self,stage,payload,schema,instructions,max_tokens=None):
        self.calls.append(stage)
        if stage.startswith('classify_batch_'):
            return dict(results=[dict(passage_id=p['passage_id'],classification=self.json('classify_'+stage[-1],dict(p,taxonomy=payload['taxonomy']),{},instructions)) for p in payload['passages']])
        if stage.startswith('review_'):
            findings=[]
            for p in payload['passages']:
                if 'artificial intelligence' in p['text'].lower():
                    findings.append(dict(passage_id=p['passage_id'],status='Yes',mention_type='explicit',quote=p['text'],rationale='Synthetic fixture has an explicit AI mention.'))
            return dict(complete=True,reviewed_passage_ids=[p['passage_id'] for p in payload['passages']],findings=findings)
        if stage in ('discover_cluster','taxonomy_merge','taxonomy_audit'):
            examples=payload.get('samples') or payload.get('examples')
            example=examples[0]
            return dict(themes=[dict(code='GOV',label='AI governance',definition='Explicit AI governance needs.',inclusion='AI governance action.',
                exclusion='Unrelated digital infrastructure.',boundary_cases='Generic AI mentions need context.',
                examples=[dict(passage_id=example['passage_id'],quote=example['text'])])],rationale='Synthetic codebook for execution tests only.')
        if stage.startswith('classify_'):
            return dict(themes=[dict(code=c,value='Yes',quote=payload['text'],rationale='Synthetic explicit governance statement.') for c in payload['taxonomy']['codes']],
                        institutions=[],keywords=[dict(normalized_term='artificial intelligence',original_term='artificial intelligence',quote=payload['text'])],uncovered_concept='')
        if stage=='reference_context':return dict(facts=[])
        if stage.startswith('report_'):
            from unga_analysis.analysis.reporting import TITLES
            return dict(sections=[dict(title=t,paragraphs=[dict(text='Synthetic workflow fixture. This is not a finding about any actual Member State.',evidence_ids=[],reference_ids=[],metric_keys=['annual:1'])]) for t in TITLES],
                        recommendations=[dict(addressee='SPMU',action='Inspect the accompanying synthetic evidence ledger.',rationale='This recommendation exists only to exercise the reporting layout.',evidence_ids=[],metric_keys=['annual:1']) for _ in range(3)])
        raise AssertionError(stage)
    def embed(self,records):
        import numpy as np
        return np.random.default_rng(7).normal(size=(len(records),12)).tolist()


def fixture(root):
    root=Path(root);(root/'config').mkdir(parents=True,exist_ok=True)
    for file in ('analysis.toml','un_regional_groups.csv'):
        shutil.copy2(PROJECT/'config'/file,root/'config'/file)
    import re
    cp=root/'config/analysis.toml'
    # Legacy transport tests use fake clients only; production remains embeddings-only.
    cp.write_text(re.sub(r'^minimum_expected_speeches = .*$', 'minimum_expected_speeches = {}',cp.read_text(encoding='utf-8'),flags=re.M).replace('render_with_word = true','render_with_word = false').replace('text_backend = "codex_subscription"','text_backend = "openai_api"').replace('api_scope = "embeddings_only"','api_scope = "text_and_embeddings"'),encoding='utf-8')
    # Legacy tests retain exhaustive two-pass semantics; scoped/batched tests opt in explicitly.
    cp.write_text(cp.read_text(encoding='utf-8').replace('scope = "screened_speeches"','scope = "full"').replace('primary_passes = 1','primary_passes = 2').replace('batch_passages = 8','batch_passages = 1'),encoding='utf-8')
    (root/'reference').mkdir(exist_ok=True)
    cfg=config(root)
    rows=[]
    for index,(year,country) in enumerate([(2017,'CAN'),(2017,'USA')]+[(2026,c) for c in ['CAN','USA','FRA','GBR','KOR','BRA']]):
        sid=f'{year}_{country}';source_id='fixture_'+sid
        texts=['We support governance of artificial intelligence.','This fixture contains no substantive technology discussion.']
        if country=='USA':texts=['Health and peace are our priorities.','Education is essential.']
        source=dict(source_id=source_id,speech_id=sid,year=year,country_iso3=country,
            path=f'data/{sid}.json',format='json',source_type='official_transcript' if year==2017 else 'automatic_transcript',
            status='accepted',representative=True,speech_kind='main_general_debate',entity_type='member_state',language='en',
            origin_file=f'data/UNGA2026_day{index-1}_EN_ASR.json' if year==2026 else 'data/official.pdf',
            text_accuracy='synthetic_fixture',analytical_group='Fixture region',speech_date=f'{year}-09-25')
        p=root/source['path'];p.parent.mkdir(parents=True,exist_ok=True);save(p,dict(synthetic=True,texts=texts));source['sha256']=digest(p)
        source['passages']=[dict(passage_id=f'{source_id}:{i+1}',speech_id=sid,text=text,source_sha256=source['sha256'],
            ai_status='Pending',locator={'extracted_block':i+1,'char_start':0,'char_end':len(text)}) for i,text in enumerate(texts)]
        rows.append(source)
    write_jsonl(root/'config/source_manifest.jsonl',[{k:v for k,v in r.items() if k!='passages'} for r in rows])
    write_jsonl(root/'output/pipeline/speeches.jsonl',rows)
    return rows,cfg


class WorkflowTests(unittest.TestCase):
    def test_env_file_wins_and_quotes_supported(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);(root/'.env').write_text('OPENAI_API_KEY="fixture-only"\n',encoding='utf-8')
            self.assertEqual(key_from_env(root),'fixture-only')

    def test_partial_report_blocked_but_explicit_interim_allowed(self):
        with TemporaryWorkspace() as temp:
            rows,cfg=fixture(temp);rows=[r for r in rows if '_day6_' not in r['origin_file']]
            with self.assertRaisesRegex(ValueError,'Final report blocked'):coverage_guard(rows,cfg)
            self.assertTrue(coverage_guard(rows,cfg,True)['2026']['partial'])

    def test_six_received_days_unlocks_session_report(self):
        with TemporaryWorkspace() as temp:
            rows,cfg=fixture(temp)
            self.assertFalse(coverage_guard(rows,cfg)['2026']['partial'])

    def test_execute_flag_required_even_with_client(self):
        with TemporaryWorkspace() as temp:
            _,cfg=fixture(temp)
            with self.assertRaisesRegex(ValueError,'--execute'):OpenAIProvider(temp,cfg,client=Mock())

    def test_provider_budget_and_cache(self):
        with TemporaryWorkspace() as temp:
            _,cfg=fixture(temp);client=Mock()
            client.responses.create.return_value=SimpleNamespace(status='completed',output_text='{"value":"ok"}',id='fixture-response',usage=SimpleNamespace(input_tokens=10,output_tokens=10))
            p=OpenAIProvider(temp,cfg,execute=True,budget=1,client=client)
            schema={'type':'object','properties':{'value':{'type':'string'}},'required':['value'],'additionalProperties':False}
            self.assertEqual(p.json('test',{},schema,'Return test JSON'),{'value':'ok'})
            p.json('test',{},schema,'Return test JSON');self.assertEqual(client.responses.create.call_count,1)
            tiny=OpenAIProvider(temp,cfg,execute=True,budget=.000001,client=client)
            with self.assertRaises(BudgetExceeded):tiny.json('new',{},schema,'Different request')

    def test_negative_review_disagreement_is_unknown(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,cfg=fixture(root);provider=FixtureProvider();original=provider.json
            def disagreement(stage,payload,*args,**kw):
                r=original(stage,payload,*args,**kw)
                if stage=='review_2':r['findings']=[]
                return r
            provider.json=disagreement
            reviewed=review_all(rows[:1],provider,cfg,root/'review')
            self.assertEqual(reviewed[0]['ai_status'],'Uncertain');self.assertEqual(reviewed[1]['ai_status'],'No')

    def test_bad_taxonomy_quote_rejected(self):
        with self.assertRaises(ValueError):validate_taxonomy({'themes':[{'code':'GOV','label':'Governance','definition':'x','inclusion':'x','exclusion':'x','boundary_cases':'x','examples':[{'passage_id':'p','quote':'invented'}]}]}, {'p':'real source'})

    def test_embedding_adapter_maps_indices_and_reuses_cache(self):
        with TemporaryWorkspace() as temp:
            _,cfg=fixture(temp);cfg['discovery']['dimensions']=3
            client=Mock();client.embeddings.create.return_value=SimpleNamespace(
                data=[SimpleNamespace(index=1,embedding=[0.,1.,0.]),SimpleNamespace(index=0,embedding=[1.,0.,0.])],
                usage=SimpleNamespace(total_tokens=8))
            p=OpenAIProvider(temp,cfg,execute=True,budget=1,client=client)
            records=[{'passage_id':'a','embedding_text':'AI governance','source_sha256':'1'},
                     {'passage_id':'b','embedding_text':'AI capacity','source_sha256':'2'}]
            self.assertEqual(p.embed(records),[[1.,0.,0.],[0.,1.,0.]])
            p.embed(records);self.assertEqual(client.embeddings.create.call_count,1)

    def test_bad_embedding_dimension_rejected(self):
        with TemporaryWorkspace() as temp:
            _,cfg=fixture(temp);client=Mock()
            client.embeddings.create.return_value=SimpleNamespace(data=[SimpleNamespace(index=0,embedding=[1.])],usage=SimpleNamespace(total_tokens=2))
            p=OpenAIProvider(temp,cfg,execute=True,budget=1,client=client)
            with self.assertRaisesRegex(ValueError,'dimensions'):
                p.embed([{'passage_id':'a','embedding_text':'AI','source_sha256':'1'}])

    def test_partial_execution_stops_before_model_calls(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,_=fixture(root)
            rows=[r for r in rows if '_day6_' not in r['origin_file']]
            write_jsonl(root/'config/source_manifest.jsonl',[{k:v for k,v in r.items() if k!='passages'} for r in rows])
            write_jsonl(root/'output/pipeline/speeches.jsonl',rows)
            provider=FixtureProvider()
            with self.assertRaisesRegex(ValueError,'Final report blocked'):run(root,execute=True,provider=provider,fetch_current=False)
            self.assertEqual(provider.calls,[])

    def test_no_ai_is_reviewed_no_not_a_taxonomy_error(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,_=fixture(root)
            for row in rows:
                for passage in row['passages']:passage['text']='Education and public health.'
            write_jsonl(root/'output/pipeline/speeches.jsonl',rows)
            result=run(root,execute=True,provider=FixtureProvider(),fetch_current=False,stop_after='aggregate')
            out=Path(result['output']);stats=json.loads((out/'aggregates.json').read_text(encoding='utf-8'))
            self.assertEqual(stats['annual'][1]['n'],0);self.assertEqual(stats['annual'][1]['N'],6)
            self.assertEqual(json.loads((out/'taxonomy.json').read_text())['status'],'no_verified_AI_passages')

    def test_missing_review_coverage_cannot_be_aggregated(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,cfg=fixture(root)
            with self.assertRaisesRegex(ValueError,'review coverage'):aggregate(rows,[],[],{'codes':{}},cfg,root/'aggregate')

    def test_no_execution_means_no_model_calls(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);fixture(root);provider=FixtureProvider()
            result=run(root,provider=provider)
            self.assertEqual(provider.calls,[]);self.assertEqual(result['paid_calls_performed'],0)

    def test_degenerate_discovery_reads_every_source(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);_,cfg=fixture(root);provider=FixtureProvider()
            records=[dict(passage_id=f'p{i}',speech_id=f's{i}',text='Artificial intelligence requires governance.',source_sha256='fixture') for i in range(30)]
            provider.embed=lambda rows:[[1.0,0.0] for _ in rows]
            discover(records,provider,cfg,root/'discovery')
            diagnostics=json.loads((root/'discovery/discovery_diagnostics.json').read_text())
            self.assertTrue(diagnostics['unresolved_geometry'])
            self.assertEqual(diagnostics['taxonomy_sampling'],'all_source_passages_in_batches_due_to_unusable_geometry')
            self.assertEqual(provider.calls.count('discover_cluster'),2)

    def test_pending_delivery_note_prevents_negative_country_verdict(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,cfg=fixture(root)
            rows[1]['source_review_notes']={'status':'pending_delivery_verification'}
            reviewed=review_all(rows,FixtureProvider(),cfg,root/'review')
            from unga_analysis.analysis.classification import classify_all
            taxonomy={'codes':{'GOV':{'label':'Governance'}}}
            classified=classify_all(reviewed,taxonomy,{},FixtureProvider(),cfg,root/'classified')
            _,_,_,matrix=aggregate(rows,reviewed,classified,taxonomy,cfg,root/'aggregate')
            negative=next(r for r in matrix if r['speech_id']==rows[1]['speech_id'])
            self.assertEqual(negative['ai_status'],'Uncertain');self.assertIsNone(negative['GOV'])
            clear=next(r for r in matrix if r['speech_id']=='2026_USA')
            self.assertEqual(clear['ai_status'],'No');self.assertEqual(clear['GOV'],0)

    def test_generic_requests_do_not_count_as_requests_to_un(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,cfg=fixture(root)
            reviewed=review_all(rows,FixtureProvider(),cfg,root/'review')
            from unga_analysis.analysis.classification import classify_all
            taxonomy={'codes':{'GOV':{'label':'Governance'}}}
            classified=classify_all(reviewed,taxonomy,{},FixtureProvider(),cfg,root/'classified')
            flags={k:k in ('mention','request') for k in cfg['institutions']['stances']}
            classified[0]['institutions']=[dict(mechanism='Other model',stances=flags,quote=classified[0]['text'],un_role='generic',review_status='reviewed')]
            stats,_,_,_=aggregate(rows,reviewed,classified,taxonomy,cfg,root/'aggregate')
            self.assertTrue(any(r['stance']=='mention' for r in stats['institution_stance_counts']))
            self.assertFalse(any(r['stance']=='request' for r in stats['institution_stance_counts']))

    def test_full_workflow_renders_without_changing_corpus(self):
        with TemporaryWorkspace() as temp:
            root=Path(temp);rows,cfg=fixture(root);before=digest(root/'output/pipeline/speeches.jsonl')
            result=run(root,execute=True,provider=FixtureProvider(),fetch_current=False)
            self.assertEqual(result['state'],'complete');self.assertEqual(result['publication']['pdf_pages'],4)
            self.assertEqual(before,digest(root/'output/pipeline/speeches.jsonl'))
            out=Path(result['output']);stats=json.loads((out/'aggregates.json').read_text(encoding='utf-8'))
            self.assertEqual(stats['annual'][1]['n'],5);self.assertEqual(stats['annual'][1]['N'],6)
            self.assertTrue(Path(result['publication']['docx']).is_file())
            for name in ['evidence_register.csv','theme_taxonomy.md','country_year_theme_matrix.csv','yearly_keyword_trends.csv','institution_stances.csv','methodology_and_cost.md','reference_inventory.json']:
                self.assertTrue((out/name).is_file(),name)
