import csv,json,tomllib,re
from collections import Counter
from pathlib import Path
from functools import lru_cache
from .contracts import validate_manifest,validate_source
from .io import read_jsonl,write_jsonl,digest,stable_hash,workspace_path
from .adapters import extract,ADAPTER_VERSION

@lru_cache(maxsize=512)
def _origin_digest(path,mtime_ns,size):
 # Many country speeches share one large meeting source; verify once per file version.
 return digest(path)

def config(root):
 with (Path(root)/'config/analysis.toml').open('rb') as f:return tomllib.load(f)

def group_mapping(root,cfg):
 path=workspace_path(root,cfg['regional_mapping'])
 with path.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
 mapping={r['iso3']:r for r in rows}
 if len(mapping)!=193 or len(rows)!=193:raise ValueError('Regional mapping must contain 193 unique Member States')
 if any(r['mapping_as_of']!=cfg['aggregation']['mapping_as_of'] for r in rows):raise ValueError('Mapping date/config mismatch')
 return mapping

def status(root):
 cfg=config(root);mp=workspace_path(root,cfg['source_manifest'])
 rows=list(read_jsonl(mp)) if mp.exists() else [];validate_manifest(rows)
 result=[]
 for year in cfg['scope']['years']:
  rr=[r for r in rows if r['year']==year]
  accepted=[r for r in rr if r['status']=='accepted' and r['representative']]
  result.append(dict(year=year,state='awaiting_user_sources' if year in cfg['scope']['awaiting_user_sources'] else 'registered' if accepted else 'missing',accepted_representatives=len(accepted),quarantined=sum(r['status']=='quarantined' for r in rr)))
 for row in result:
  rr=[r for r in rows if r['year']==row['year']]
  row['pending_sources']=sum(r['status']=='pending' for r in rr)
  row['provisional_sources']=sum(r['status']=='external_provisional' for r in rr)
  row['accepted_automatic_transcripts']=sum(r['status']=='accepted' and r['representative'] and r['source_type']=='automatic_transcript' for r in rr)
  if row['state']=='missing' and row['provisional_sources']:row['state']='provisional_only'
  row['coverage_status']='partial' if row['year'] in cfg['scope'].get('partial_years',[]) else 'see_country_year_coverage'
  if row['coverage_status']=='partial':
   days={int(r['origin_file'].split('_day')[1].split('_')[0]) for r in rr if r['status']=='accepted' and '_day' in r.get('origin_file','')}
   if set(range(1,7)).issubset(days):row['coverage_status']='all_six_day_sources_received; participation_roster_not_reconciled'
 return dict(years=result,external_provisional_enabled=cfg['scope']['include_external_provisional_sources'],regional_system=cfg['aggregation']['regional_system'],mapping_as_of=cfg['aggregation']['mapping_as_of'],report_status='Analysis workflow implemented; run analyze for readiness or analyze --execute for authorized execution. Output/analysis/latest.json records actual completion.')

def passage_blocks(blocks,max_words=350,max_chars=3000):
 """Bound long transcript paragraphs; retain exact offsets in extracted text."""
 if max_words<1 or max_chars<1:raise ValueError('Passage limits must be positive')
 for block_no,(text,locator) in enumerate(blocks,1):
  words=list(re.finditer(r'\S+',text));i=0
  while i<len(words):
   stop=min(i+max_words,len(words));begin=words[i].start()
   while stop>i+1 and words[stop-1].end()-begin>max_chars:stop-=1
   if words[stop-1].end()-begin>max_chars:raise ValueError('Overlong unsplittable text token; source review required')
   if stop<len(words):
    boundaries=[j+1 for j in range(i+(stop-i)//2,stop) if re.search(r'[.!?]["\u201d\u2019\)]?$',words[j].group())]
    if boundaries:stop=boundaries[-1]
   end=words[stop-1].end()
   yield text[begin:end],dict(locator,extracted_block=block_no,char_start=begin,char_end=end)
   i=stop

def normalize_source(root,source,cfg=None,allow_provisional=False):
 root=Path(root);cfg=cfg or config(root);validate_source(source)
 provisional=allow_provisional and source['status']=='external_provisional'
 if not provisional and (source['status']!='accepted' or not source['representative']):raise ValueError('Only explicitly accepted representative sources can be ingested; provisional normalization requires an explicit separate output')
 if source['year'] in cfg['scope']['awaiting_user_sources']:raise ValueError(f"{source['year']} is awaiting user sources; complete registration and update config before ingestion")
 source_path=workspace_path(root,source['path']);sha=digest(source_path)
 if source.get('sha256') and sha!=source['sha256']:raise ValueError('Source hash changed; verify new version before reusing extraction')
 if source.get('origin_file') and source.get('origin_sha256'):
  origin=workspace_path(root,source['origin_file']);stat=origin.stat()
  if _origin_digest(str(origin),stat.st_mtime_ns,stat.st_size)!=source['origin_sha256']:raise ValueError('Original verbatim source changed; rebuild source-located speech')
 mapping=group_mapping(root,cfg)
 if source['source_type']=='automatic_transcript' and not provisional:
  if source['year'] not in cfg.get('sources',{}).get('accepted_automatic_transcript_years',[]) or source.get('source_acceptance')!='user_confirmed_primary':raise ValueError('Automatic transcript requires explicit canonical-source acceptance')
 if source['country_iso3'] not in mapping:raise ValueError('Country is not in the Member State mapping')
 cache_input={k:source.get(k) for k in ['format','source_type','selector','encoding','cached_pages','cache_file_key','country_iso3','year']}
 cache_input.update(source_sha256=sha,adapter_version=ADAPTER_VERSION)
 if source.get('cached_pages'):
  cache_input['cached_pages_sha256']=digest(workspace_path(root,source['cached_pages']))
  if source.get('cached_pages_sha256') and cache_input['cached_pages_sha256']!=source['cached_pages_sha256']:raise ValueError('Extraction cache changed; re-register verified cache')
 key=stable_hash(cache_input);out=workspace_path(root,cfg['output_directory']);cache=out/'cache/text'/f'{key}.json'
 hit=cache.exists()
 if hit:blocks=json.loads(cache.read_text(encoding='utf8'))['blocks']
 else:
  blocks=extract(root,source)
  cache.parent.mkdir(parents=True,exist_ok=True)
  tmp=cache.with_suffix('.tmp');tmp.write_text(json.dumps(dict(key=key,input=cache_input,blocks=blocks),ensure_ascii=False),encoding='utf8');tmp.replace(cache)
 passages=[]
 limits=cfg.get('preprocessing',{})
 for n,(text,locator) in enumerate(passage_blocks(blocks,limits.get('passage_max_words',350),limits.get('passage_max_chars',3000)),1):
  if not text.strip():continue
  if source.get('origin_file'):
   if locator.get('origin_file')!=source['origin_file'] or locator.get('origin_sha256')!=source['origin_sha256']:raise ValueError('Passage lost its original source provenance')
   origin_format=source.get('origin_format',Path(source['origin_file']).suffix.lstrip('.'))
   if origin_format=='pdf' and not locator.get('pdf_page'):raise ValueError('Missing physical PDF page')
   if origin_format=='json' and not locator.get('json_pointer'):raise ValueError('Missing original JSON pointer')
   if origin_format=='txt' and not (locator.get('line_start') and locator.get('line_end')):raise ValueError('Missing original transcript line range')
  passages.append(dict(passage_id=f"{source['source_id']}:{n}",speech_id=source['speech_id'],source_id=source['source_id'],text=text,locator=locator,source_sha256=sha,source_file=source['path'],source_type=source['source_type'],text_accuracy=source.get('text_accuracy','unverified'),text_review_status='Pending',ai_status='Pending',theme_labels={}))
 if not passages:raise ValueError('No readable passages; source remains unresolved, not AI-negative')
 row=dict(source)
 row.pop('speaker_rank',None) # Legacy metadata must not become an analytical dimension.
 row.update(schema_version='1.0',sha256=sha,analytical_group=mapping[source['country_iso3']]['analytical_group'],mapping_as_of=mapping[source['country_iso3']]['mapping_as_of'],passages=passages,extraction_cache_key=key,extraction_cache_hit=hit,classification_status='Pending',passage_settings=limits)
 return row

def ingest(root,year=None,source_id=None):
 root=Path(root);cfg=config(root);rows=list(read_jsonl(workspace_path(root,cfg['source_manifest'])));validate_manifest(rows)
 if year in cfg['scope']['awaiting_user_sources']:raise ValueError(f'{year} is awaiting user sources; no ingestion or classification has been performed')
 selected=[r for r in rows if r['status']=='accepted' and r['representative'] and (year is None or r['year']==year) and (source_id is None or r['source_id']==source_id)]
 if source_id and not selected:raise ValueError('No accepted representative matches source_id')
 selected=[r for r in selected if r['year'] not in cfg['scope']['awaiting_user_sources']]
 out=workspace_path(root,cfg['output_directory']);normalized=[];issues=[]
 for source in selected:
  try:normalized.append(normalize_source(root,source,cfg))
  except (ValueError,OSError,KeyError,RuntimeError) as e:issues.append(dict(source_id=source['source_id'],speech_id=source['speech_id'],status='unresolved',error=str(e)))
 # A scoped run updates that partition and preserves already ingested other years/sources.
 existing=list(read_jsonl(out/'speeches.jsonl')) if (out/'speeches.jsonl').exists() else []
 target_ids={r['source_id'] for r in selected}
 active_ids={r['source_id'] for r in rows if r['status']=='accepted' and r['representative']}
 merged=[r for r in existing if r['source_id'] in active_ids and r['source_id'] not in target_ids]+normalized
 write_jsonl(out/'speeches.jsonl',sorted(merged,key=lambda r:(r['year'],r['country_iso3'])))
 write_jsonl(out/'ingestion_issues.jsonl',issues)
 return dict(selected=len(selected),normalized=len(normalized),cache_hits=sum(r['extraction_cache_hit'] for r in normalized),unresolved=len(issues),output=str(out/'speeches.jsonl'))

def register(root,manifest_path):
 root=Path(root);cfg=config(root);target=workspace_path(root,cfg['source_manifest'])
 current=list(read_jsonl(target)) if target.exists() else [];new=list(read_jsonl(manifest_path));validate_manifest(current+new)
 mapping=group_mapping(root,cfg)
 for r in new:
  if r['country_iso3'] not in mapping:raise ValueError('Source country is not in the 193-member mapping')
  path=workspace_path(root,r['path'])
  if not path.is_file():raise ValueError(f"Missing source file: {r['path']}")
  actual=digest(path)
  if r.get('sha256') and r['sha256']!=actual:raise ValueError('Supplied source hash mismatch')
  r['sha256']=actual
 write_jsonl(target,current+new)
 return dict(registered=len(new),note='Awaiting-year flags remain until corpus completeness is explicitly updated in config.')
