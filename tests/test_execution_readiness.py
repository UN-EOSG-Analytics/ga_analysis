from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import unittest

from tests.helpers import TemporaryWorkspace,PROJECT
from tests.test_analysis_workflow import fixture,FixtureProvider
from unga_analysis.io import digest,write_jsonl
from unga_analysis.analysis.common import save
from unga_analysis.analysis.scope import review_plan,stratum
from unga_analysis.analysis.review import review_all
from unga_analysis.analysis.subscription import SubscriptionProvider,AwaitingSubscriptionWork
from unga_analysis.analysis.classification import classify_all
from unga_analysis.analysis.aggregation import aggregate
from unga_analysis.analysis.workflow import receive_final_day,validate_final_day


def screened_fixture(root):
    rows,cfg=fixture(root)
    for index in range(20):
        row=deepcopy(rows[0]);row.update(speech_id=f'2017_X{index}',source_id=f'fixture_X{index}',country_iso3=f'X{index}')
        for j,p in enumerate(row['passages']):p.update(passage_id=f'x{index}:{j}',text='Peace and health are priorities.')
        rows.append(row)
    write_jsonl(Path(root)/'output/pipeline/speeches.jsonl',rows)
    write_jsonl(Path(root)/'output/screening/ai_candidates.jsonl',[dict(evidence=[dict(passage_id=rows[0]['passages'][0]['passage_id'])])])
    save(Path(root)/'output/screening/summary.json',{'input_sha256':digest(Path(root)/'output/pipeline/speeches.jsonl')})
    cfg['review'].update(scope='screened_speeches',primary_passes=1,negative_sample_per_stratum=1,second_review_percent=0)
    return rows,cfg


class ExecutionReadinessTests(unittest.TestCase):
    def test_transient_windows_output_lock_retries_without_deleting_output(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);path=root/'result.jsonl';write_jsonl(path,[{'old':True}])
            original=Path.replace;calls=[]
            def replace(source,destination):
                calls.append(True)
                if len(calls)==1:
                    self.assertIn('old',Path(destination).read_text());raise PermissionError('Temporary Windows lock')
                return original(source,destination)
            with patch.object(Path,'replace',autospec=True,side_effect=replace),patch('unga_analysis.io.time.sleep'):
                write_jsonl(path,[{'new':True}])
            self.assertEqual(len(calls),2);self.assertIn('new',path.read_text())

    def test_selection_is_stratified_deterministic_and_missing_screen_falls_back(self):
        with TemporaryWorkspace() as tmp:
            rows,cfg=screened_fixture(tmp);a=review_plan(rows,cfg,tmp);b=review_plan(list(reversed(rows)),cfg,tmp)
            self.assertEqual({r['speech_id']:r for r in a['rows']},{r['speech_id']:r for r in b['rows']})
            self.assertEqual(sum(r['selection']=='negative_audit_sample' for r in a['rows']),len({stratum(s) for s in rows}))
            self.assertGreater(a['unselected_speeches'],0)
            save(Path(tmp)/'output/screening/summary.json',{'input_sha256':'stale'})
            self.assertEqual(review_plan(rows,cfg,tmp)['selected_speeches'],len(rows))

    def test_unreviewed_are_pending_and_annual_share_is_a_lower_bound(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=screened_fixture(root);plan=review_plan(rows,cfg,root)
            reviewed=review_all(rows,FixtureProvider(),cfg,root/'review',plan)
            pending=[r for r in reviewed if r['ai_status']=='Pending'];self.assertTrue(pending)
            self.assertTrue(all(r['reviews']==[] for r in pending))
            taxonomy={'codes':{'GOV':{'label':'Governance'}}}
            classified=classify_all(reviewed,taxonomy,{},FixtureProvider(),cfg,root/'labels')
            stats,_,_,matrix=aggregate(rows,reviewed,classified,taxonomy,cfg,root/'aggregate')
            annual=next(r for r in stats['annual'] if r['year']==2017)
            self.assertEqual(annual['measure'],'verified_detection_lower_bound');self.assertEqual(annual['N'],annual['obtained'])
            self.assertLess(annual['resolved_N'],annual['N'])
            unknown=next(r for r in matrix if r['speech_id']==pending[0]['speech_id'])
            self.assertEqual(unknown['ai_status'],'Uncertain');self.assertIsNone(unknown['GOV'])

    def test_audit_hit_expands_entire_stratum(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=screened_fixture(root);plan=review_plan(rows,cfg,root)
            sample=next(r for r in plan['rows'] if r['selection']=='negative_audit_sample' and r['stratum'][0]==2017)
            hit=next(s for s in rows if s['speech_id']==sample['speech_id'])
            hit['passages'][0]['text']='We support governance of artificial intelligence.'
            reviewed=review_all(rows,FixtureProvider(),cfg,root/'review',plan)
            self.assertFalse(any(r['year']==2017 and r['ai_status']=='Pending' for r in reviewed))
            saved=json.loads((root/'review/review_selection.json').read_text())
            self.assertIn(hit['speech_id'],saved['audit_hit_speeches']);self.assertGreater(saved['expanded_speeches'],0)

    def test_all_review_jobs_export_before_first_pause_including_second_pass(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=screened_fixture(root);cfg['review'].update(scope='full',primary_passes=2)
            provider=SubscriptionProvider(root,cfg)
            with patch('openai.OpenAI',side_effect=AssertionError('Forbidden')):
                with self.assertRaises(AwaitingSubscriptionWork):review_all(rows,provider,cfg,root/'review')
            self.assertEqual(len(provider.pending),2*len(rows));self.assertGreater(len(provider.pending),16)
            self.assertEqual({p['stage'] for p in provider.pending.values()},{'review_1','review_2'})
            self.assertFalse(list(provider.path.glob('*.response.json')))

    def test_batch_classification_exports_both_passes_and_preserves_labels(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=fixture(root);reviewed=review_all(rows,FixtureProvider(),cfg,root/'review')
            cfg['classification']['batch_passages']=8;taxonomy={'codes':{'GOV':{'label':'Governance'}}}
            provider=SubscriptionProvider(root,cfg)
            with self.assertRaises(AwaitingSubscriptionWork):classify_all(reviewed,taxonomy,{},provider,cfg,root/'labels')
            self.assertEqual(len(provider.pending),2)
            for job in provider.pending.values():
                request=json.loads(Path(job['request']).read_text());payload=request['payload']
                self.assertEqual(len(payload['passages']),6);self.assertTrue(all('taxonomy' not in r for r in payload['passages']))
                value=FixtureProvider().json(request['stage'],payload,request['schema'],request['instructions'])
                save(job['response'],dict(request_hash=request['request_hash'],reviewer={'environment':'codex_subscription','model':'offline_fixture','human_reviewed':False},value=value))
            result=classify_all(reviewed,taxonomy,{},SubscriptionProvider(root,cfg),cfg,root/'labels')
            self.assertEqual(len(result),6);self.assertTrue(all(r['themes']=={'GOV':'Yes'} for r in result))

    def test_batch_rejects_wrong_ids_and_quotes(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=fixture(root);reviewed=review_all(rows,FixtureProvider(),cfg,root/'review')
            cfg['classification']['batch_passages']=8
            for bad in ('id','quote'):
                provider=FixtureProvider();original=provider.json
                def reply(stage,*args,**kwargs):
                    value=original(stage,*args,**kwargs)
                    if stage.startswith('classify_batch'):
                        if bad=='id':value['results'][0]['passage_id']='unrelated'
                        else:value['results'][0]['classification']['themes'][0]['quote']='invented wording'
                    return value
                provider.json=reply
                with self.assertRaises(ValueError):classify_all(reviewed,{'codes':{'GOV':{'label':'Governance'}}},{},provider,cfg,root/'labels')

    def test_batch_disagreement_is_uncertain_and_refusal_splits(self):
        from unga_analysis.analysis.provider import ResponseUnavailable
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=fixture(root);reviewed=review_all(rows,FixtureProvider(),cfg,root/'review')
            cfg['classification']['batch_passages']=8;provider=FixtureProvider();original=provider.json
            def reply(stage,payload,*args,**kwargs):
                if stage.startswith('classify_batch') and len(payload['passages'])>1:raise ResponseUnavailable('max_output_tokens')
                value=original(stage,payload,*args,**kwargs)
                if stage=='classify_batch_2':value['results'][0]['classification']['themes'][0].update(value='No',quote='',rationale='')
                return value
            provider.json=reply
            result=classify_all(reviewed,{'codes':{'GOV':{'label':'Governance'}}},{},provider,cfg,root/'labels')
            self.assertEqual(len(result),6);self.assertTrue(all(r['themes']['GOV']=='Uncertain' for r in result))

    def test_reference_stage_exports_all_groups_in_one_pause(self):
        from unga_analysis.analysis.references import summarize_references
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);_,cfg=fixture(root);provider=SubscriptionProvider(root,cfg)
            blocks=[dict(reference_id=f'R{i}',text='Background fixture. '*1400,locator={'line':i+1}) for i in range(20)]
            with self.assertRaises(AwaitingSubscriptionWork):summarize_references(blocks,provider,root/'refs')
            self.assertEqual(len(provider.pending),20)

    def test_office_owner_file_is_not_a_reference_or_fingerprint_input(self):
        from unga_analysis.analysis.references import reference_blocks,reference_files
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);(root/'reference').mkdir()
            (root/'reference/~$open_document.docx').write_bytes(b'Office owner lock, not a ZIP archive')
            (root/'reference/real.txt').write_text('Supplied background.')
            self.assertEqual([p.name for p in reference_files(root)],['real.txt'])
            blocks,inventory=reference_blocks(root,None,fetch_current=False)
            self.assertEqual(len(blocks),1);self.assertEqual(len(inventory),1)

    def test_scoped_batched_subscription_run_reaches_report_with_fake_responses(self):
        from unga_analysis.analysis.workflow import run
        from tests.test_subscription_workflow import subscription_fixture
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);rows,cfg=subscription_fixture(root)
            cp=root/'config/analysis.toml';cp.write_text(cp.read_text().replace('scope = "full"','scope = "screened_speeches"').replace('primary_passes = 2','primary_passes = 1').replace('batch_passages = 1','batch_passages = 8'))
            from unga_analysis.pipeline import config
            cfg=config(root)
            write_jsonl(root/'output/screening/ai_candidates.jsonl',[dict(evidence=[dict(passage_id=s['passages'][0]['passage_id'])]) for s in rows if s['country_iso3']!='USA'])
            save(root/'output/screening/summary.json',{'input_sha256':digest(root/'output/pipeline/speeches.jsonl')})
            before=digest(root/'output/pipeline/speeches.jsonl');stages=set()
            with patch('openai.OpenAI',side_effect=AssertionError('Forbidden')):
                for cycle in range(15):
                    provider=SubscriptionProvider(root,cfg,embedding_provider=FixtureProvider())
                    result=run(root,execute=True,provider=provider,fetch_current=False)
                    if result['state']=='complete':break
                    for job in result['pending']:
                        request=json.loads(Path(job['request']).read_text());stages.add(request['stage'])
                        value=FixtureProvider().json(request['stage'],request['payload'],request['schema'],request['instructions'])
                        save(job['response'],dict(request_hash=request['request_hash'],reviewer={'environment':'codex_subscription','model':'offline_fixture','human_reviewed':False},value=value))
                else:self.fail('Scoped subscription workflow did not finish')
            self.assertIn('classify_batch_1',stages);self.assertIn('report_fact_check',stages)
            self.assertLess(cycle,12);self.assertEqual(digest(root/'output/pipeline/speeches.jsonl'),before)
            self.assertTrue(Path(result['publication']['source_notes']).exists())

    def test_wrong_year_day6_is_rejected_before_copy(self):
        with TemporaryWorkspace() as tmp:
            root=Path(tmp);source=root/'day6.json'
            save(source,dict(url='https://transcripts.un.org/en/ga/80/15',video={'date':'2025-09-29','title':'Day 6, 80th session','pv_symbol':'A/80/PV.15'},transcript={'language':'en','data':[{}]}))
            with self.assertRaisesRegex(ValueError,'year/session'):receive_final_day(root,source)
            self.assertFalse((root/'data').exists())
            value=json.loads(source.read_text());value['video'].update(date='2026-09-29',title='Day 6, 81st session',pv_symbol='A/81/PV.15');value['url']='https://transcripts.un.org/en/ga/81/15'
            save(source,value);destination=receive_final_day(root,source)
            self.assertEqual(digest(source),digest(destination));self.assertEqual(validate_final_day(destination)['year'],2026)

    def test_actual_attached_2025_file_cannot_unlock_2026(self):
        path=PROJECT/'data/intake_pending_year_confirmation/2025-09-29_09-00_Day_6_General_Debate_General_Assembly_14th_an_en.json'
        if not path.exists():self.skipTest('Local intake source absent')
        with self.assertRaisesRegex(ValueError,'year/session'):validate_final_day(path)
