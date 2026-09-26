import csv,json,shutil,tempfile,unittest,zipfile
from pathlib import Path
from unga_analysis.io import write_jsonl,read_jsonl,digest
from unga_analysis.contracts import validate_manifest
from unga_analysis.pipeline import normalize_source,config,group_mapping,status,register,ingest
from unga_analysis.aggregate import country_theme_value,classification_complete,yearly_theme_share,requests_to_un
from unga_analysis.labels import validate_label_record,validate_institution_record

PROJECT=Path(__file__).resolve().parents[1]

class PipelineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  (self.root/'config').mkdir();(self.root/'data').mkdir()
  for n in ['analysis.toml','un_regional_groups.csv']:shutil.copy2(PROJECT/'config'/n,self.root/'config'/n)
  self.cfg=config(self.root);self.cfg['scope']['awaiting_user_sources']=[]
 def tearDown(self):self.temp.cleanup()
 def source(self,fmt='txt',content='First paragraph.\n\nSecond paragraph.'):
  path=self.root/'data'/('example.'+fmt)
  if isinstance(content,bytes):path.write_bytes(content)
  else:path.write_text(content,encoding='utf8')
  return dict(source_id='test_2026_KIR',speech_id='2026_KIR',country_iso3='KIR',year=2026,path=path.relative_to(self.root).as_posix(),format=fmt,source_type='official_transcript',speech_kind='main_general_debate',entity_type='member_state',status='accepted',representative=True,sha256=digest(path),speaker_name=None,speaker_rank='unknown')
 def test_text_lines_and_cache(self):
  s=self.source();r=normalize_source(self.root,s,self.cfg)
  self.assertEqual(len(r['passages']),2);self.assertEqual(r['passages'][1]['locator'],{'line_start':3,'line_end':3})
  self.assertEqual(r['passages'][0]['ai_status'],'Pending');self.assertFalse(r['extraction_cache_hit'])
  self.assertTrue(normalize_source(self.root,s,self.cfg)['extraction_cache_hit'])
 def test_json_pointer_and_timestamps(self):
  s=self.source('json',json.dumps({'meeting':[{'paragraphs':[{'text':'Example parser text, not a national statement.','start':'00:04:12','end':'00:04:18'}]}]}));s['selector']={'json_pointer':'/meeting/0'}
  p=normalize_source(self.root,s,self.cfg)['passages'][0]
  self.assertEqual(p['locator']['start'],'00:04:12');self.assertNotIn('pdf_page',p['locator'])
 def test_json_mixed_speakers_rejected(self):
  s=self.source('json',json.dumps({'segments':[{'text':'x','speaker_country':'USA'}]}))
  with self.assertRaisesRegex(ValueError,'Mixed speakers'):normalize_source(self.root,s,self.cfg)
 def test_right_of_reply_rejected(self):
  s=self.source('json',json.dumps({'segments':[{'text':'x','kind':'right_of_reply'}]}))
  with self.assertRaisesRegex(ValueError,'right-of-reply'):normalize_source(self.root,s,self.cfg)
 def test_jsonl_unicode_separator_preserved(self):
  s=self.source('jsonl',json.dumps({'text':'A\u0085B'},ensure_ascii=False)+'\n'+json.dumps({'text':'Second'})+'\n')
  rr=normalize_source(self.root,s,self.cfg)['passages'];self.assertEqual(len(rr),2);self.assertEqual(rr[0]['text'],'A\u0085B')
 def test_docx_paragraph_locations(self):
  s=self.source('docx',b'');path=self.root/s['path']
  with zipfile.ZipFile(path,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Example text.</w:t></w:r></w:p></w:body></w:document>')
  s['sha256']=digest(path);p=normalize_source(self.root,s,self.cfg)['passages'][0]
  self.assertEqual(p['locator'],{'paragraph':1})
 def test_pdf_reuses_verified_text_cache(self):
  s=self.source('pdf',b'%PDF test stub; extraction intentionally cached');s['source_type']='submitted_statement';s['cached_pages']='data/pages.jsonl';s['cache_file_key']='example.pdf'
  write_jsonl(self.root/s['cached_pages'],[dict(file='example.pdf',pdf_page=7,text='Previously extracted source text.',method='tesseract')]);s['cached_pages_sha256']=digest(self.root/s['cached_pages'])
  p=normalize_source(self.root,s,self.cfg)['passages'][0]
  self.assertEqual(p['locator']['pdf_page'],7);self.assertEqual(p['locator']['text_method'],'tesseract')
 def test_changed_source_rejected(self):
  s=self.source();(self.root/s['path']).write_text('Changed',encoding='utf8')
  with self.assertRaisesRegex(ValueError,'hash changed'):normalize_source(self.root,s,self.cfg)
 def test_empty_source_unresolved(self):
  s=self.source(content='\n\n')
  with self.assertRaisesRegex(ValueError,'No readable'):normalize_source(self.root,s,self.cfg)
 def test_pending_year_blocked(self):
  s=self.source()
  with self.assertRaisesRegex(ValueError,'awaiting user'):normalize_source(self.root,s)
  write_jsonl(self.root/'config/source_manifest.jsonl',[])
  with self.assertRaisesRegex(ValueError,'awaiting user'):ingest(self.root,year=2026)
 def test_duplicate_versions_blocked(self):
  s=self.source();second=dict(s,source_id='other')
  with self.assertRaisesRegex(ValueError,'Multiple accepted'):validate_manifest([s,second])
 def test_no_automatic_NA_to_zero(self):
  self.assertIsNone(country_theme_value([]));self.assertIsNone(country_theme_value([{'value':'Uncertain','review_status':'reviewed'}]))
  self.assertIsNone(country_theme_value([{'value':'Yes','review_status':'pending'}]))
  self.assertEqual(country_theme_value([{'value':'Yes','review_status':'reviewed'},{'value':'Pending','review_status':'pending'}]),1)
  self.assertEqual(country_theme_value([{'value':'No','review_status':'reviewed'}]),0)
  self.assertFalse(classification_complete([{'themes':{'GOV':'Yes'},'review_status':'reviewed'}],['GOV','ACCESS']))
 def test_labels_need_evidence(self):
  r=dict(passage_id='x',source_sha256='h',taxonomy_sha256='t',themes={'GOV':'Yes'},review_status='reviewed',evidence={})
  with self.assertRaisesRegex(ValueError,'requires source evidence'):validate_label_record(r,['GOV'])
 def test_yearly_share_threshold(self):
  self.assertIsNone(yearly_theme_share(3,6,20)['pct']);self.assertTrue(yearly_theme_share(3,6,20)['below_threshold'])
  self.assertEqual(yearly_theme_share(10,40,20)['pct'],25.0)
 def institution(self,**kw):
  inst=self.cfg['institutions'];r=dict(year=2026,iso3='KOR',speech_id='2026_KOR',source_sha256='h',locator='p3',quote='q',mechanism='Panel',reference_type='explicit name',stances={s:0 for s in inst['stances']},requested_functions=['scientific assessment'],un_role='explicit',review_status='reviewed')
  r.update(kw);return r
 def test_institution_records(self):
  inst=self.cfg['institutions'];r=self.institution();r['stances']['commitment']=1
  with self.assertRaisesRegex(ValueError,'Commitment requires'):validate_institution_record(r,inst)
  with self.assertRaisesRegex(ValueError,'Unknown functions'):validate_institution_record(self.institution(requested_functions=['enforcement']),inst)
  explicit=self.institution();explicit['stances']['request']=1
  generic=self.institution(un_role='generic');generic['stances']['request']=1
  self.assertEqual(requests_to_un([validate_institution_record(explicit,inst),validate_institution_record(generic,inst)]),[explicit])
 def test_regional_edge_cases(self):
  m=group_mapping(self.root,self.cfg);self.assertEqual(len(m),193)
  self.assertEqual(m['USA']['analytical_group'],'Not a formal member of any regional group')
  self.assertEqual(m['TUR']['analytical_group'],'Western European and other States')
  self.assertEqual(m['KIR']['analytical_group'],'Asia-Pacific States')
  self.assertEqual(m['ISR']['analytical_group'],'Western European and other States')
 def test_path_escape_rejected(self):
  s=self.source();s['path']='../outside.txt'
  with self.assertRaisesRegex(ValueError,'leaves project'):normalize_source(self.root,s,self.cfg)

if __name__=='__main__':unittest.main()
