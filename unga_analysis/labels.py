"""Contracts for the next classification stage; never fabricate missing No values."""
from .io import stable_hash

LABELS={'Yes','No','Uncertain','Pending'}

def validate_label_record(record,codes):
 if not codes:raise ValueError('A reviewed taxonomy is required before classification')
 required={'passage_id','source_sha256','taxonomy_sha256','themes','review_status','evidence'}
 if missing:=required-record.keys():raise ValueError(f'Missing label fields: {sorted(missing)}')
 if set(record['themes'])!=set(codes):raise ValueError('Every taxonomy code needs an explicit Yes/No/Uncertain/Pending value')
 if not all(v in LABELS for v in record['themes'].values()):raise ValueError('Unknown thematic value')
 if record['review_status'] not in {'pending','reviewed','uncertain'}:raise ValueError('Unknown review status')
 for code,value in record['themes'].items():
  if value=='Yes' and not record['evidence'].get(code):raise ValueError(f'Yes requires source evidence: {code}')
 if record['review_status']=='reviewed' and 'Pending' in record['themes'].values():raise ValueError('A reviewed row cannot contain Pending values')
 return record

def validate_institution_record(record,inst):
 """inst: the [institutions] config table. Only un_role=='explicit' rows count as requests to the UN."""
 required={'year','iso3','speech_id','source_sha256','locator','quote','mechanism','reference_type','stances','requested_functions','un_role','review_status'}
 if missing:=required-record.keys():raise ValueError(f'Missing institution fields: {sorted(missing)}')
 if record['mechanism'] not in inst['mechanisms']:raise ValueError(f"Unknown mechanism: {record['mechanism']}")
 if set(record['stances'])!=set(inst['stances']) or not all(v in (0,1) for v in record['stances'].values()):raise ValueError('Every stance needs an explicit 0/1 value')
 if unknown:=set(record['requested_functions'])-set(inst['functions']):raise ValueError(f'Unknown functions: {sorted(unknown)}')
 if record['un_role'] not in inst['un_role']:raise ValueError('un_role must be explicit or generic')
 if record['stances']['commitment'] and not record.get('commitment_detail'):raise ValueError('Commitment requires actor/action detail')
 if not record['quote']:raise ValueError('Institution records require a source quote')
 return record

def embedding_cache_key(source_sha256,chunk_text,chunk_settings,model,model_revision):
 # Geographic regrouping cannot invalidate extraction/embeddings/classifications.
 return stable_hash(dict(stage='embedding',source_sha256=source_sha256,text=chunk_text,chunk_settings=chunk_settings,model=model,model_revision=model_revision))

def classification_cache_key(chunk_key,taxonomy_sha256,prompt_sha256,review_model):
 return stable_hash(dict(stage='classification',chunk_key=chunk_key,taxonomy_sha256=taxonomy_sha256,prompt_sha256=prompt_sha256,review_model=review_model))
