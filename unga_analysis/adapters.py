"""Format adapters return source-located passages; no AI or policy labels here."""
import json,re,zipfile
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from .io import read_jsonl,workspace_path
ADAPTER_VERSION='1.2-canonical-transcript-locators'

@lru_cache(maxsize=2)
def _cached_pages(path,mtime_ns):
 groups={}
 for p in read_jsonl(path):groups.setdefault(p['file'],[]).append(p)
 return groups

def _pointer(obj,pointer):
 if pointer=='':return obj
 if not pointer.startswith('/'):raise ValueError('json_pointer must begin with /')
 for part in pointer[1:].split('/'):
  part=part.replace('~1','/').replace('~0','~')
  obj=obj[int(part)] if isinstance(obj,list) else obj[part]
 return obj

def _blocks(text):
 # Split actual blank lines only; U+0085 inside OCR text must not become a JSONL boundary.
 lines=text.replace('\r\n','\n').replace('\r','\n').split('\n');start=None;buf=[]
 for i,line in enumerate(lines,1):
  if line.strip():
   if start is None:start=i
   buf.append(line)
  elif buf:
   yield '\n'.join(buf),{'line_start':start,'line_end':i-1};buf=[];start=None
 if buf:yield '\n'.join(buf),{'line_start':start,'line_end':len(lines)}

def _segments(obj,source):
 statement_start=obj.get('start') if isinstance(obj,dict) else None
 if isinstance(obj,dict):
  if obj.get('country_iso3') and obj['country_iso3']!=source['country_iso3']:raise ValueError('Transcript country conflicts with manifest')
  if obj.get('year') and int(obj['year'])!=source['year']:raise ValueError('Transcript year conflicts with manifest')
  attribution=obj.get('speaker',{})
  if isinstance(attribution,dict) and attribution.get('affiliation') and attribution['affiliation']!=source['country_iso3']:raise ValueError('Transcript speaker conflicts with manifest')
  if 'paragraphs' in obj:items=obj['paragraphs']
  elif 'segments' in obj:items=obj['segments']
  elif 'text' in obj:items=[obj]
  else:raise ValueError('Unknown transcript layout; specify json_pointer or implement an adapter')
 elif isinstance(obj,list):items=obj
 else:raise ValueError('Transcript must contain a list or object, not an inferred meeting roster')
 for n,part in enumerate(items,1):
  if isinstance(part,str):part={'text':part}
  if not isinstance(part,dict):raise ValueError('Invalid transcript segment')
  speaker=part.get('country_iso3') or part.get('speaker_country')
  if speaker and speaker!=source['country_iso3']:raise ValueError('Mixed speakers: register an explicit selection for each country')
  if part.get('kind','main_general_debate')!='main_general_debate':raise ValueError('Chair/right-of-reply segment mixed into main address')
  text=part.get('text')
  if text is None and 'sentences' in part:text=' '.join(s['text'] for s in part['sentences'])
  if not isinstance(text,str):raise ValueError('Transcript segment has no text')
  loc={'paragraph':n}
  if statement_start is not None:loc['statement_start']=statement_start
  for key in ['start','end','timestamp','line','line_start','line_end','speaker_line','statement_timestamp','transcript_block','jsonl_record','statement_start','pdf_page','pdf_block','bbox','origin_file','origin_sha256','json_pointer']:
   if key in part:loc[key]=part[key]
  yield text,loc

def extract(root,source):
 path=workspace_path(root,source['path']);fmt=source['format'];selector=source.get('selector',{})
 if fmt=='txt':
  encoding=source.get('encoding','utf-8-sig');text=path.read_text(encoding=encoding)
  if re.search(r'^Transcript: https://transcripts\.un\.org/',text,re.M):raise ValueError('Meeting transcript TXT must first be split into country speeches with prepare')
  return list(_blocks(text))
 if fmt=='json':
  obj=json.loads(path.read_text(encoding='utf-8-sig'));obj=_pointer(obj,selector.get('json_pointer',''))
  if isinstance(obj,dict):
   for key in ('speech_id','country_iso3','year','source_type','origin_file','origin_sha256'):
    if key in obj and key in source and obj[key]!=source[key]:raise ValueError(f'Derived speech/manifest mismatch: {key}')
  return list(_segments(obj,source))
 if fmt=='jsonl':
  items=list(read_jsonl(path))
  items=[dict(r,jsonl_record=i) for i,r in enumerate(items,1)]
  if 'record_start' in selector or 'record_end' in selector:
   start=selector.get('record_start',1);end=selector.get('record_end',len(items))
   if not 1<=start<=end<=len(items):raise ValueError('Invalid one-based record range')
   items=items[start-1:end]
  return list(_segments(items,source))
 if fmt=='docx':
  with zipfile.ZipFile(path) as z:doc=ET.fromstring(z.read('word/document.xml'))
  ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
  return [(''.join(t.text or '' for t in p.findall('.//w:t',ns)),{'paragraph':i}) for i,p in enumerate(doc.findall('.//w:body/w:p',ns),1)]
 if fmt=='pdf':
  if source.get('cached_pages'):
   cache=workspace_path(root,source['cached_pages']);source_file=source.get('cache_file_key',source['path'])
   pp=_cached_pages(str(cache),cache.stat().st_mtime_ns).get(source_file,[])
   if not pp:raise ValueError('Declared PDF text cache contains no matching source pages')
   return [(p['text'],{'pdf_page':p['pdf_page'],'text_method':p.get('method','native_pdf_extraction')}) for p in sorted(pp,key=lambda p:p['pdf_page'])]
  try:import pymupdf
  except ImportError as e:raise RuntimeError('Install the pdf extra or supply verified cached_pages; no remote OCR fallback') from e
  with pymupdf.open(path) as doc:return [(p.get_text(sort=False),{'pdf_page':i+1,'text_method':'native_pdf_extraction'}) for i,p in enumerate(doc)]
 raise ValueError(fmt)
