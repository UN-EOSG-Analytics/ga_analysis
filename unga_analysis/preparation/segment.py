"""Build source-located English country speeches and an explicit exception queue.

No embeddings, model calls or policy labels. Raw inputs remain recoverable.
Run from the project root. Extraction cache is keyed by PDF SHA-256.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import csv, hashlib, json, re, sys, unicodedata, tomllib
from functools import lru_cache
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from unga_analysis.io import digest, read_jsonl, write_jsonl

RAW = ROOT/'data/unga_general_debate_verbatim_en'
DEST = ROOT/'data/analysis_ready_en'
OUT = ROOT/'output/corpus_preparation'
CACHE = ROOT/'cache/verbatim_blocks'
VERSION = 'canonical-transcripts-3'
PDF_CACHE_VERSION = 'verbatim-blocks-2'
digest = lru_cache(maxsize=4096)(digest)

def norm(s):
    s=unicodedata.normalize('NFKD',s).casefold()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def clean(s):
    s=s.replace('\u00ad','').replace('\x08','').replace('\u200b','')
    s=re.sub(r'([a-z])-\s*\n\s*([a-z])',r'\1\2',s)
    return re.sub(r'\s+',' ',s).strip()

def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(obj,ensure_ascii=False,indent=2)
    if path.exists() and path.read_text(encoding='utf8')==content:return
    path.write_text(content,encoding='utf8')

def table(path,rows,fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

MEMBERS={r['iso3']:r for r in csv.DictReader((ROOT/'config/un_regional_groups.csv').open(encoding='utf-8-sig'))}
ALIASES={norm(r['country']):iso for iso,r in MEMBERS.items()}
for iso,names in {
 'NRU':['Nauru'], 'BHS':['Bahamas'], 'LBN':['Lebanese Republic'], 'GAB':['Gabonese Republic'],
 'CHE':['Swiss Confederation'], 'SVK':['Slovak Republic'], 'FRA':['French Republic'],
 'KGZ':['Kyrgyz Republic'], 'MEX':['United Mexican States'], 'ARG':['Argentine Republic'],
 'PRT':['Portuguese Republic'], 'GRC':['Hellenic Republic'], 'TGO':['Togolese Republic'],
 'TUR':['Turkey','Türkiye'], 'MKD':['the former Yugoslav Republic of Macedonia','North Macedonia'],
 'SWZ':['Swaziland','Eswatini'], 'CIV':['Côte d’Ivoire','Ivory Coast'], 'KOR':['Republic of Korea'],
 'PRK':["Democratic People’s Republic of Korea"], 'IRN':['Islamic Republic of Iran','Iran'],
 'BOL':['Plurinational State of Bolivia','Bolivia'], 'VEN':['Bolivarian Republic of Venezuela','Venezuela'],
 'TZA':['United Republic of Tanzania','Tanzania'], 'VNM':['Viet Nam','Vietnam'],
 'MDA':['Republic of Moldova','Moldova'], 'LAO':["Lao People’s Democratic Republic","Lao People's Democratic Republic"],
 'FSM':['Federated States of Micronesia','Micronesia'], 'BRN':['Brunei Darussalam'],
 'GBR':['United Kingdom of Great Britain and Northern Ireland','United Kingdom'],
 'USA':['United States of America','United States'], 'SYR':['Syrian Arab Republic','Syria'],
 'RUS':['Russian Federation','Russia'], 'CZE':['Czech Republic','Czechia'],
 'CPV':['Cabo Verde','Cape Verde'], 'COG':['Republic of the Congo','Congo'],
 'COD':['Democratic Republic of the Congo'], 'STP':['Sao Tome and Principe','São Tomé and Príncipe','Sao Tome et Principe'],
 'TLS':['Timor-Leste','East Timor'], 'PSE':['State of Palestine','Palestine'],
 'VAT':['Holy See','His Holiness Pope Francis'], 'EU':['European Union','European Council']}.items():
    for name in names:ALIASES[norm(name)]=iso

def country(text):
    t=' '+norm(text)+' '
    hits=[(len(name),iso) for name,iso in ALIASES.items() if ' '+name+' ' in t]
    return max(hits)[1] if hits else None

def blocks(path):
    sha=digest(path);cache=CACHE/f'{sha}-{PDF_CACHE_VERSION}.json'
    if cache.exists():return json.loads(cache.read_text(encoding='utf8'))
    result=[]
    with pymupdf.open(path) as doc:
        for pi,page in enumerate(doc):
            bb=[]
            for bi,b in enumerate(page.get_text('dict')['blocks']):
                if 'lines' not in b:continue
                spans=[s for l in b['lines'] for s in l['spans']]
                raw='\n'.join(''.join(s['text'] for s in l['spans']) for l in b['lines'])
                text=clean(raw)
                if not text:continue
                x0,y0,x1,y1=b['bbox']
                # Running header/footer and first-page publication boilerplate.
                if y0<55 or y1>page.rect.height-42:continue
                if pi==0 and ('This record contains' in text or text.startswith(('Corrections should','They should be incorporated','verbatimrecords@'))):continue
                if re.fullmatch(r'(?:\d{2}-\d{4,6}.*|\*\d+\*|\d+/\d+|A/\d+/PV\.\d+|\d{2}/\d{2}/\d{4})',text):continue
                lead=''
                for s in spans:
                    if 'Bold' in s['font']:lead+=s['text']
                    elif s['text'].strip():break
                bb.append(dict(text=text,raw_text=raw,bold=clean(lead),italic=('Italic' in spans[0]['font']),
                    pdf_page=pi+1,pdf_block=bi,bbox=[round(v,2) for v in b['bbox']]))
            # Older records use two columns; annexes and newer records are single column.
            two=sum(b['bbox'][0]<100 and b['bbox'][2]<320 for b in bb)>=2 and sum(b['bbox'][0]>300 for b in bb)>=2
            bb.sort(key=lambda b:((int(b['bbox'][0]>305) if two else 0),b['bbox'][1],b['bbox'][0]))
            result.extend(bb)
    dump(cache,result)
    return result

def make_speech(year,iso,title,label,source,kind,parts,date,extra=None):
    title=title.split(' The President:')[0].split(' The Acting President')[0] if title.startswith(('Address by ','Statement by ')) else title
    sha=digest(source)
    for p in parts:
        p['origin_file']=source.relative_to(ROOT).as_posix();p['origin_sha256']=sha
    return dict(year=year,country_iso3=iso,speech_id=f'{year}_{iso}',speaker_name=label,
        speaker_title=title,speech_date=date,source_type=kind,
        origin_file=source.relative_to(ROOT).as_posix(),origin_sha256=sha,
        paragraphs=parts,word_count=sum(len(p['text'].split()) for p in parts),
        metadata_evidence=title,preprocessing_version=VERSION,**(extra or {}))

def parse_pdf(path):
    year=int(path.parent.name[-4:]);meeting=int(re.search(r'_PV_(\d+)',path.name)[1])
    if year==2021 and meeting in (5,8):return [],[dict(file=path.relative_to(ROOT).as_posix(),reason='excluded_other_agenda_Durban_anniversary')]
    bb=blocks(path);alltext=' '.join(b['text'] for b in bb[:25])
    dm=re.search(r'(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (20\d{2})',alltext)
    date=datetime.strptime(dm[0],'%d %B %Y').date().isoformat() if dm else None
    speeches=[];issues=[];active=None;context='';reply=False;annex=False;chair_mode=False
    def flush():
        nonlocal active
        if active and active['parts']:
            speeches.append(make_speech(year,active['iso'],active['title'],active['label'],path,'official_transcript',active['parts'],date,dict(segmentation_method=active['method'])))
        active=None
    for index,b in enumerate(bb):
        t=b['text'];bold=b['bold']
        if re.fullmatch(r'(?:(?:\d+/\d+|\d{2}-\d{4,6}|A/\d+/PV\.\d+|\d{2}/\d{2}/\d{4})\s*)+',t):continue
        if re.match(r'^Annex (?:[IVXLCDM]+|\d+)\b',t):
            flush();annex=True;context='';continue
        heading=bool(re.match(r'^(?:Address(?: by)?|Statement by) ',t,re.I)) and bool(bold)
        if annex:
            if heading:
                flush();context=t
                iso=country(t)
                if iso:active=dict(iso=iso,title=t,label=t.split(',')[0],parts=[],method='annex_heading')
                else:issues.append(dict(file=path.name,pdf_page=b['pdf_page'],reason='unmapped_annex_heading',text=t))
                continue
            if active and not t.startswith(('[Original:', '[English translation', '[Translation')):
                active['parts'].append({k:v for k,v in b.items() if k not in ('bold','italic')})
            continue
        if heading:
            flush();context=t;chair_mode=True;continue
        chair=bool(re.match(r'^(?:The (?:Acting )?President|The Secretary-General|The Deputy Secretary-General)\s*[:(]',t))
        if chair:
            flush();chair_mode=True
            if 'right of reply' in t.casefold():reply=True
            # Preserve nearby introduction as attribution evidence, not analytical text.
            if 'give the floor' in t or 'call on' in t or 'welcome' in t or 'will now hear' in t:
                new_minister_intro='call on' in t or ('give the floor' in t and 'to introduce' not in t)
                context=t if new_minister_intro else (context+' '+t)[-2200:]
            continue
        if chair_mode and 'right of reply' in t.casefold() and not bold:
            reply=True;flush();continue
        if chair_mode and not bold and not re.match(r'^(?:Mr\.|Mrs\.|Ms\.|Prime Minister |Sir |Dato |Shaikh )',t):
            if 'give the floor' in t or 'call on' in t:context=t
            elif context and not context.endswith(('.',':')):context=clean(context+' '+t)
        if t.startswith(('The meeting rose','The meeting was suspended','The meeting was called','The meeting was resumed')):
            flush();continue
        label_start=bool(re.match(r'^(?:Mr\.|Mrs\.|Ms\.|President |Prime Minister |King |Queen |Emir |Amir |Prince |Sheikh |Shaikh |Dato |Sir |Sultan |Crown Prince |General |Chancellor |His Majesty |Her Majesty )',t))
        label=label_start and (bool(bold) or t.startswith('Prime Minister Schoof (Kingdom of the Netherlands):')) and (bool(re.search(r'[:;]',t[:500])) or bool(re.match(r'^[^()]+\([^()]+\) \(spoke in [^()]+\) ',t)))
        if label:
            flush();chair_mode=False
            delimiter=re.search(r':',t[:500]) or re.search(r';',t[:500])
            if delimiter:prefix,body=t[:delimiter.start()],t[delimiter.end():]
            else:
                end=re.match(r'^[^()]+\([^()]+\) \(spoke in [^()]+\) ',t).end()
                prefix,body=t[:end],t[end:]
            # Direct country label takes precedence over the preceding introduction.
            parens=re.findall(r'\(([^()]*)\)',prefix)
            iso=next((ALIASES[norm(p)] for p in parens if norm(p) in ALIASES),None) or country(context)
            if year==2017 and meeting==7 and iso=='MEX':
                issues.append(dict(file=path.name,pdf_page=b['pdf_page'],reason='excluded_condolence_response_before_general_debate',country_iso3='MEX'))
                continue
            if not reply and iso:
                active=dict(iso=iso,title=context,label=re.sub(r'\s*\(.*','',prefix),parts=[],method='bold_speaker_and_official_introduction')
                if body.strip():active['parts'].append(dict(text=body.strip(),raw_text=b['raw_text'],pdf_page=b['pdf_page'],pdf_block=b['pdf_block'],bbox=b['bbox']))
            elif not reply:
                issues.append(dict(file=path.name,pdf_page=b['pdf_page'],reason='unmapped_speaker',text=t[:500],context=context))
            continue
        if active:
            if b['italic'] and ('was escorted' in t or 'took the' in t or 'assumed the' in t or 'pre-recorded video statement' in t):continue
            if re.match(r'^\(spoke in [^)]*\)$',t):continue
            active['parts'].append({k:v for k,v in b.items() if k not in ('bold','italic')})
    flush()
    # Recorded video annexes replace the floor representative's introduction in 2020/2021.
    annex_isos={s['country_iso3'] for s in speeches if s['segmentation_method']=='annex_heading'}
    speeches=[s for s in speeches if s['segmentation_method']=='annex_heading' or s['country_iso3'] not in annex_isos]
    return speeches,issues

def parse_asr(path):
    obj=json.loads(path.read_text(encoding='utf8'));year=int(re.search(r'UNGA(\d{4})',path.name)[1]);date=obj['video']['date'][:10]
    overrides=json.loads((ROOT/'config/verbatim_attribution_overrides.json').read_text(encoding='utf8')).get(path.name,{})
    results=[];issues=[];reply=False
    for si,s in enumerate(obj['transcript']['data']):
        speaker=overrides.get(str(si),s.get('speaker') or {});iso=speaker.get('affiliation');paras=[]
        raw=' '.join(sentence['text'] for p in s.get('paragraphs',[]) for sentence in p.get('sentences',[]))
        if iso in ('GA','UN'):
            if re.search(r'right (?:of|to) reply|deliver my closing remarks',raw,re.I):reply=True
            continue
        if iso not in MEMBERS:
            if not iso and len(raw.split())>150:issues.append(dict(file=path.name,reason='ASR_unknown_speaker',statement=si,text=raw[:180]))
            continue
        if reply:continue
        for pi,p in enumerate(s.get('paragraphs',[])):
            sent=p.get('sentences',[]);text=clean(' '.join(x['text'] for x in sent))
            if not text:continue
            paras.append(dict(text=text,raw_text=text,start=sent[0].get('start'),end=sent[-1].get('end'),
                json_pointer=f'/transcript/data/{si}/paragraphs/{pi}',statement_start=s.get('start')))
        if paras:
            results.append(make_speech(year,iso,speaker.get('function') or '',speaker.get('name'),path,'automatic_transcript',paras,date,
                dict(segmentation_method='ASR_supplied_speaker_metadata',source_url=obj['url'],audio_url=obj['video']['url'],asr_review_status='unverified')))
            if str(si) in overrides:results[-1]['attribution_evidence']=overrides[str(si)]['evidence']
    return results,issues

def parse_asr_txt(path):
    """Parse UN text exports with speaker headers and original line locators.

    Header timestamps locate speaker turns, not individual paragraphs.
    """
    lines=path.read_text(encoding='utf-8-sig').splitlines()
    year=int(re.search(r'UNGA(\d{4})',path.name)[1])
    dm=next((re.fullmatch(r'Date: (\d{1,2} \w+ \d{4}), .*',x) for x in lines[:10] if x.startswith('Date: ')),None)
    if not dm:raise ValueError(f'{path.name}: missing transcript date')
    date=datetime.strptime(dm[1],'%d %B %Y').date().isoformat()
    if int(date[:4])!=year:raise ValueError(f'{path.name}: filename/date conflict')
    if 'Language: English' not in lines[:10]:raise ValueError(f'{path.name}: English header required')
    url=next((x.removeprefix('Transcript: ') for x in lines[:10] if x.startswith('Transcript: ')),None)
    headers=[]
    for i,line in enumerate(lines):
        m=re.fullmatch(r'(.+?) \[((?:\d+:)?\d+:\d{2})\]:',line)
        if m:headers.append((i,m[1].split(' · '),m[2]))
    if not headers:raise ValueError(f'{path.name}: unsupported speaker header layout')
    results=[];issues=[];reply=False
    for n,(start,fields,timestamp) in enumerate(headers):
        end=headers[n+1][0] if n+1<len(headers) else len(lines)
        body=' '.join(lines[start+1:end]);affiliation=fields[0]
        if affiliation in ('GA','UN'):
            if re.search(r'right (?:of|to) reply|deliver my closing remarks',body,re.I):reply=True
            continue
        iso=ALIASES.get(norm(affiliation))
        if reply:
            issues.append(dict(file=path.name,reason='excluded_right_of_reply',line=start+1,country_iso3=iso))
            continue
        if iso in ('VAT','PSE','EU'):
            issues.append(dict(file=path.name,reason='excluded_non_member_state',line=start+1,country_iso3=iso))
            continue
        if iso not in MEMBERS or len(fields)>3:
            issues.append(dict(file=path.name,reason='unmapped_ASR_text_header',line=start+1,header=lines[start]))
            continue
        paras=[];begin=None
        for j in range(start+1,end+1):
            line=lines[j] if j<end else ''
            if line.strip() and begin is None:begin=j
            if not line.strip() and begin is not None:
                raw='\n'.join(lines[begin:j])
                paras.append(dict(text=clean(raw),raw_text=raw,line_start=begin+1,line_end=j,
                    speaker_line=start+1,statement_timestamp=timestamp,transcript_block=n+1))
                begin=None
        if paras:
            title=fields[1] if len(fields)==3 else ''
            name=fields[-1] if len(fields)>1 else None
            results.append(make_speech(year,iso,title,name,path,'automatic_transcript',paras,date,
                dict(segmentation_method='ASR_text_speaker_headers',source_url=url,asr_review_status='unverified')))
    return results,issues

def main():
    OUT.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
    digest.cache_clear()
    with (ROOT/'config/analysis.toml').open('rb') as f:cfg=tomllib.load(f)
    accepted_asr_years=cfg['sources']['accepted_automatic_transcript_years']
    # Comparison evidence is metadata; never splice prepared PDF text into ASR.
    review_path=ROOT/'config/source_review_notes.json'
    source_reviews=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    candidates=[];issues=[]
    for path in sorted(RAW.glob('UNGA*/*.pdf')):
        ss,ii=parse_pdf(path);candidates+=ss;issues+=ii
        print(path.name,len(ss),len(ii),flush=True)
    for path in sorted((RAW/'automatic_transcripts_unofficial').glob('*_ASR.*')):
        if path.suffix not in ('.json','.txt'):continue
        ss,ii=(parse_asr(path) if path.suffix=='.json' else parse_asr_txt(path))
        candidates+=ss;issues+=ii
        print(path.name,len(ss),len(ii),flush=True)
    groups=defaultdict(list)
    for s in candidates:
        if s['country_iso3'] not in MEMBERS:continue
        groups[s['speech_id']].append(s)
    manifest=[];coverage=[];duplicates=[];candidates_report=[]
    for sid,items in sorted(groups.items()):
        # Separate session/source duplicates from adjacent ASR continuation segments.
        items.sort(key=lambda s:(s['source_type']!='official_transcript',-s['word_count']))
        official=[s for s in items if s['source_type']=='official_transcript' and s['word_count']>=200]
        if official:
            chosen=official[0]
            other=[s for s in official[1:] if s['word_count']>=200]
            status='accepted' if not other else 'pending'
            reason='' if not other else 'multiple_official_speech_segments'
        else:
            chosen=items[0];status='pending';reason='short_or_incomplete_speech'
            if chosen['source_type']=='automatic_transcript':
                variants=defaultdict(list)
                for s in items:variants[(s['origin_file'],s['speaker_name'])].append(s)
                merged=[]
                for same in variants.values():
                    paras=sorted([p for s in same for p in s['paragraphs']],key=lambda p:(p.get('line_start',0),p.get('start') or 0))
                    merged.append(dict(same[0],paragraphs=paras,word_count=sum(len(p['text'].split()) for p in paras)))
                merged.sort(key=lambda s:(not s['origin_file'].endswith('.json'),-s['word_count']))
                chosen=merged[0]
                bodies={norm(' '.join(p['text'] for p in s['paragraphs'])) for s in merged}
                reason='multiple_ASR_speech_versions' if len(bodies)>1 else ''
                if reason:status='pending'
                elif chosen['word_count']<200:reason='short_or_incomplete_speech'
                elif chosen['year'] in accepted_asr_years:status='accepted'
                else:status='external_provisional';reason='source_acceptance_required'
        chosen['source_acceptance']='user_confirmed_primary' if chosen['source_type']=='automatic_transcript' and status=='accepted' else ('official_verbatim_primary' if chosen['source_type']=='official_transcript' else 'pending')
        chosen['text_accuracy']='unverified_automatic_transcription' if chosen['source_type']=='automatic_transcript' else 'official_record'
        chosen['preprocessing_version']=VERSION
        for s in items:
            candidates_report.append({k:s[k] for k in ('speech_id','source_type','origin_file','speaker_name','word_count','segmentation_method')})
        selected_parts={id(p) for p in chosen['paragraphs']}
        for s in items:
            used=all(id(p) in selected_parts for p in s['paragraphs'])
            if used and len(items)==1:continue
            if s is not chosen:duplicates.append(dict(speech_id=sid,origin_file=s['origin_file'],word_count=s['word_count'],action='merged_into_selected_main_address' if used else 'alternate_or_short_segment_not_separately_counted'))
        text='\n\n'.join(p['text'] for p in chosen['paragraphs'])
        chosen['body_sha256']=hashlib.sha256(norm(text).encode()).hexdigest()
        if '\ufffd' in text:
            reason=(reason+'; ' if reason else '')+'replacement_character_in_extraction'
            status='pending' if status=='accepted' else status
        path=DEST/str(chosen['year'])/f'{sid}.json';dump(path,chosen)
        manifest.append(dict(source_id=f'verbatim_en_{sid}',speech_id=sid,country_iso3=chosen['country_iso3'],year=chosen['year'],
            path=path.relative_to(ROOT).as_posix(),format='json',source_type=chosen['source_type'],speech_kind='main_general_debate',
            entity_type='member_state',status=status,representative=status=='accepted',language='en',
            speech_date=chosen['speech_date'],speaker_name=chosen['speaker_name'],
            sha256=digest(path),origin_file=chosen['origin_file'],origin_sha256=chosen['origin_sha256'],
            metadata_evidence=chosen['metadata_evidence'],preprocessing_version=VERSION,readiness_issue=reason))
        manifest[-1].update(source_acceptance=chosen['source_acceptance'],text_accuracy=chosen['text_accuracy'],
            origin_format=Path(chosen['origin_file']).suffix.lstrip('.'))
        if sid in source_reviews:
            manifest[-1]['source_review_notes']=source_reviews[sid]
        coverage.append(dict(year=chosen['year'],country_iso3=chosen['country_iso3'],country=MEMBERS[chosen['country_iso3']]['country'],
            status=status,source_type=chosen['source_type'],words=chosen['word_count'],issue=reason,path=path.relative_to(ROOT).as_posix()))
    covered={(r['year'],r['country_iso3']) for r in coverage}
    for year in range(2017,2027):
        for iso,m in MEMBERS.items():
            if (year,iso) not in covered:coverage.append(dict(year=year,country_iso3=iso,country=m['country'],status='not_obtained_or_no_main_address',source_type='',words=0,issue='not_an_AI_negative; participation_roster_required',path=''))
    write_jsonl(DEST/'source_manifest.jsonl',manifest)
    dump(OUT/'segmentation_issues.json',issues)
    table(OUT/'country_year_coverage.csv',sorted(coverage,key=lambda r:(r['year'],r['country_iso3'])))
    table(OUT/'speech_candidates.csv',candidates_report)
    table(OUT/'alternate_segments.csv',duplicates)
    summary={str(y):dict(Counter(r['status'] for r in coverage if r['year']==y)) for y in range(2017,2027)}
    dump(OUT/'preparation_summary.json',summary);print(json.dumps(summary),flush=True)
    return manifest

if __name__=='__main__':main()
