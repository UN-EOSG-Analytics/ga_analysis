"""Validation shared by PDF and transcript ingestion; unknown is explicit."""
from datetime import date
import re
from .selection import language_code

FORMATS={'pdf','txt','json','jsonl','docx'}
SOURCE_TYPES={'submitted_statement','official_transcript','automatic_transcript'}
STATUSES={'accepted','pending','quarantined','external_provisional'}

def validate_source(r):
 required=['source_id','speech_id','country_iso3','year','path','format','source_type','speech_kind','entity_type','status','representative']
 missing=[k for k in required if k not in r]
 if missing:raise ValueError(f'Missing manifest fields: {missing}')
 if not isinstance(r['country_iso3'],str) or not re.fullmatch('[A-Z]{3}',r['country_iso3']):raise ValueError('country_iso3 must be an explicit uppercase three-letter code')
 if type(r['year']) is not int or not 2017<=r['year']<=2100:raise ValueError('Invalid explicit year')
 if r['speech_id']!=f"{r['year']}_{r['country_iso3']}":raise ValueError('speech_id must be YEAR_ISO3')
 if r['format'] not in FORMATS:raise ValueError('Unsupported format; add a documented adapter')
 if r['source_type'] not in SOURCE_TYPES:raise ValueError('Unknown source type')
 if r['status'] not in STATUSES:raise ValueError('Unknown source status')
 if type(r['representative']) is not bool:raise ValueError('representative must be boolean')
 if r.get('speech_date'):date.fromisoformat(r['speech_date'])
 if r['status']=='accepted' and (r['speech_kind']!='main_general_debate' or r['entity_type']!='member_state'):
  raise ValueError('Accepted statistical inputs must be Member State main General Debate addresses')
 if not isinstance(r.get('selector',{}),dict):raise ValueError('selector must be an object')
 return r

def validate_manifest(records):
 records=list(records)
 ids=set();reps=set()
 for r in records:
  validate_source(r)
  if r['source_id'] in ids:raise ValueError(f"Duplicate source_id: {r['source_id']}")
  ids.add(r['source_id'])
  if r['status']=='accepted' and r['representative']:
   if r['speech_id'] in reps:raise ValueError(f"Multiple accepted representative versions: {r['speech_id']}")
   reps.add(r['speech_id'])
 english={r['speech_id'] for r in records if language_code(r.get('language'))=='en'
          and r['entity_type']=='member_state' and r['speech_kind']=='main_general_debate'}
 for r in records:
  if r['status']=='accepted' and r['representative'] and r['speech_id'] in english and language_code(r.get('language'))!='en':
   raise ValueError(f"English version exists; exclude other language representatives: {r['speech_id']}")
 return records
