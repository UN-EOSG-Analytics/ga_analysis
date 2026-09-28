"""Read-only source review; write audit tables without rebuilding the corpus.

Language screening is a transparent heuristic, not certified language detection
or verification of automated transcription against audio.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
import csv, hashlib, json, re, unicodedata
import pymupdf

from .segment import ROOT, OUT, MEMBERS, ALIASES, clean, norm, country, table, dump
from ..io import read_jsonl, digest, stable_hash

WORDS={
 'en':set('the and of to in that we our is are for with this it on be as by have has will not from which their they these must all can its an at but us would should been was were a'.split()),
 'fr':set('le la les des du une un et est sont dans pour nous notre nos avec au aux ce cette ces qui que sur pas par leur leurs vous ont il elle mais comme aussi plus'.split()),
 'es':set('el la los las del una un y es son en para por con que se nuestro nuestra nuestros nuestras sus su como pero este esta estos estas han ha al nos lo las todos entre'.split()),
 'pt':set('o os a as do dos da das uma um e em para por com que se nosso nossa nossos nossas seu sua seus suas como mas este esta estes estas ao pelo pela mais'.split()),
}

def language_screen(text):
    tokens=re.findall(r"[a-z]+",text.lower())
    scores={lang:sum(w in words for w in tokens)/max(1,len(tokens)) for lang,words in WORDS.items()}
    letters=[c for c in text if c.isalpha()]
    nonlatin=sum('LATIN' not in unicodedata.name(c,'') for c in letters)/max(1,len(letters))
    flag=(scores['en']<.12 or max(scores[k] for k in ('fr','es','pt'))>scores['en'] or nonlatin>.05)
    return dict(english_function_word_share=round(scores['en'],4),
        other_language_max_share=round(max(scores[k] for k in ('fr','es','pt')),4),
        non_latin_letter_share=round(nonlatin,4),language_review_flag=flag)

def legacy_gap_rows(active):
    # Historical audit is retained in an archive. No raw files are restored.
    archive=ROOT/'archive/retired_materials.zip'
    name='output/language_coverage_audit.md'
    if not archive.exists():return [],'archive_not_supplied'
    with ZipFile(archive) as z:
        text=z.read(name).decode('utf-8-sig')
    ALIASES[norm('Cote Divoire')]='CIV'
    ALIASES[norm('Cote D Ivoire')]='CIV'
    ALIASES[norm('Democratic Republic Congo')]='COD'
    rows=[]
    for line in text.splitlines():
        if not re.match(r'^\| 20\d{2} \|',line):continue
        columns=[x.strip() for x in line.split('|')]
        year=int(columns[1])
        for label in columns[3].split(', '):
            iso=country(label);r=active.get(f'{year}_{iso}')
            state='unmapped_legacy_label' if not iso else ('excluded_non_member_state' if iso not in MEMBERS else ('English_transcript_prepared' if r else 'not_in_active_corpus'))
            rows.append(dict(year=year,legacy_label=label,country_iso3=iso or '',resolution=state,
                source_type=r['source_type'] if r else '',derived_path=r['path'] if r else '',origin_file=r['origin_file'] if r else ''))
    return rows,'historical_filename_language_audit; not a claim that non-English and English wordings were independently translated and compared'

def main():
    rows=list(read_jsonl(ROOT/'config/source_manifest.jsonl'))
    prepared=list(read_jsonl(ROOT/'data/analysis_ready_en/source_manifest.jsonl'))
    active={r['speech_id']:r for r in rows};issues=[];coverage=[];language_flags=[]
    if rows!=prepared:issues.append(dict(issue='manifest_copies_differ'))
    expected_paths={r['path'] for r in rows}
    actual_paths={p.relative_to(ROOT).as_posix() for p in (ROOT/'data/analysis_ready_en').glob('*/*.json')}
    if expected_paths!=actual_paths:issues.append(dict(issue='derived_file_set_mismatch',missing=sorted(expected_paths-actual_paths),extra=sorted(actual_paths-expected_paths)))
    groups=defaultdict(list);bodies={};pdf_checks=0
    for r in rows:groups[r['origin_file']].append(r)
    for origin,records in sorted(groups.items()):
        document=pymupdf.open(ROOT/origin) if origin.endswith('.pdf') else None
        pages={}
        try:
            for r in records:
                s=json.loads((ROOT/r['path']).read_text(encoding='utf8'))
                if r.get('language')!='en':issues.append(dict(speech_id=r['speech_id'],issue='non_English_manifest_language'))
                if 'speaker_rank' in r or 'speaker_rank' in s:issues.append(dict(speech_id=r['speech_id'],issue='deprecated_speaker_rank'))
                for key in ('speech_id','country_iso3','year','source_type','origin_file','origin_sha256'):
                    if r[key]!=s[key]:issues.append(dict(speech_id=r['speech_id'],issue='manifest_derived_metadata_mismatch',field=key))
                text=' '.join(p['text'] for p in s['paragraphs']);screen=language_screen(text)
                if screen['language_review_flag']:language_flags.append(dict(speech_id=r['speech_id'],paragraph='',text=text[:1200],**screen))
                h=hashlib.sha256(norm(text).encode()).hexdigest()
                if h in bodies:issues.append(dict(speech_id=r['speech_id'],issue='normalized_duplicate_body',other=bodies[h]))
                bodies[h]=r['speech_id']
                for i,p in enumerate(s['paragraphs'],1):
                    if len(p['text'].split())>=40:
                        ps=language_screen(p['text'])
                        if ps['language_review_flag']:language_flags.append(dict(speech_id=r['speech_id'],paragraph=i,text=p['text'][:1600],**ps))
                    if document:
                        pn=p['pdf_page']
                        if pn not in pages:pages[pn]=document[pn-1].get_text('dict')['blocks']
                        block=pages[pn][p['pdf_block']]
                        original=clean('\n'.join(''.join(span['text'] for span in line['spans']) for line in block.get('lines',[])))
                        pdf_checks+=1
                        if p['text'] not in original:issues.append(dict(speech_id=r['speech_id'],paragraph=i,issue='PDF_block_text_mismatch',pdf_page=pn,pdf_block=p['pdf_block']))
                        if any(abs(a-b)>.02 for a,b in zip(p['bbox'],block['bbox'])):issues.append(dict(speech_id=r['speech_id'],paragraph=i,issue='PDF_bbox_mismatch'))
                coverage.append(dict(year=r['year'],country_iso3=r['country_iso3'],country=MEMBERS[r['country_iso3']]['country'],
                    language=r['language'],source_type=r['source_type'],origin_format=r['origin_format'],origin_file=origin,
                    derived_path=r['path'],word_count=s['word_count'],paragraph_count=len(s['paragraphs']),**screen))
        finally:
            if document:document.close()
        print('Reviewed',origin,flush=True)
    normalized=list(read_jsonl(ROOT/'output/pipeline/speeches.jsonl'))
    by_id={r['source_id']:r for r in rows};cache_keys=set();passage_ids=set()
    for r in normalized:
        src=by_id[r['source_id']];key=r['extraction_cache_key'];cache_keys.add(key)
        if 'speaker_rank' in r:issues.append(dict(speech_id=r['speech_id'],issue='normalized_speaker_rank'))
        cache=json.loads((ROOT/'output/pipeline/cache/text'/f'{key}.json').read_text(encoding='utf8'))
        if cache['input']['source_sha256']!=src['sha256'] or stable_hash(cache['input'])!=key or cache['key']!=key:issues.append(dict(speech_id=r['speech_id'],issue='extraction_cache_key_mismatch'))
        for p in r['passages']:
            if p['passage_id'] in passage_ids:issues.append(dict(passage_id=p['passage_id'],issue='duplicate_passage_id'))
            passage_ids.add(p['passage_id'])
            if p['source_sha256']!=src['sha256']:issues.append(dict(passage_id=p['passage_id'],issue='stale_passage_source_hash'))
            loc=p['locator'];text,original_loc=cache['blocks'][loc['extracted_block']-1]
            if text[loc['char_start']:loc['char_end']]!=p['text'] or any(loc.get(k)!=v for k,v in original_loc.items()):issues.append(dict(passage_id=p['passage_id'],issue='cache_passage_mismatch'))
    missing=[dict(year=y,country_iso3=iso,country=m['country'],status='not_obtained_or_no_main_address')
        for y in range(2017,2027) for iso,m in MEMBERS.items() if f'{y}_{iso}' not in active]
    gap_rows,gap_scope=legacy_gap_rows(active)
    gap_counts=Counter(r['resolution'] for r in gap_rows)
    for r in gap_rows:
        if r['resolution'] in ('unmapped_legacy_label','not_in_active_corpus'):issues.append(dict(issue='unresolved_legacy_language_gap',**r))
    table(OUT/'english_source_coverage.csv',sorted(coverage,key=lambda r:(r['year'],r['country_iso3'])))
    table(OUT/'missing_country_years.csv',missing)
    if gap_scope!='archive_not_supplied':
        table(OUT/'legacy_language_gap_resolution.csv',gap_rows,fields=['year','legacy_label','country_iso3','resolution','source_type','derived_path','origin_file'])
    dump(OUT/'language_screen_flags.json',language_flags)
    summary=dict(reviewed_at_utc=datetime.now(timezone.utc).isoformat(),speeches=len(rows),passages=len(passage_ids),
        counts_by_year=dict(Counter(str(r['year']) for r in rows)),source_types=dict(Counter(r['source_type'] for r in rows)),
        origin_formats=dict(Counter(r['origin_format'] for r in rows)),unique_origin_files=len(groups),
        pdf_paragraphs_compared_to_original=pdf_checks,issues=issues,language_screen_flags=len(language_flags),
        missing_country_years=len(missing),legacy_language_gap_counts=dict(gap_counts),legacy_gap_scope=gap_scope,
        language_screen_scope='English source designation plus English/French/Spanish/Portuguese function-word and script heuristic on whole speeches and paragraphs of at least 40 words; not certified language identification',
        limitations=['No ASR audio verification','No independent complete participation roster audit for every year','No translation-equivalence validation of historical non-English submissions','No exhaustive semantic or speaker-attribution review'])
    dump(OUT/'db_review.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary

if __name__=='__main__':main()
