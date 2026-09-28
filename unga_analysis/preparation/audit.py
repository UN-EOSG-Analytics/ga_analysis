"""Audit actual prepared corpus hashes and locations; does not assess speech meaning."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from unga_analysis.io import read_jsonl,digest
from unga_analysis.contracts import validate_manifest
from .segment import dump,clean
from ..adapters import _pointer

def main():
    rows=list(read_jsonl(ROOT/'config/source_manifest.jsonl'));validate_manifest(rows)
    issues=[];bodies={};origins={};counts=Counter();original_text={};derived={}
    for r in rows:
        p=ROOT/r['path'];s=json.loads(p.read_text(encoding='utf8'));counts[r['status']]+=1;derived[r['source_id']]=s
        if digest(p)!=r['sha256']:issues.append(dict(source_id=r['source_id'],issue='derived_hash'))
        origin=r['origin_file']
        if origin not in origins:origins[origin]=digest(ROOT/origin)
        if origins[origin]!=r['origin_sha256']:issues.append(dict(source_id=r['source_id'],issue='origin_hash'))
        if not s.get('speech_date'):issues.append(dict(source_id=r['source_id'],issue='no_date'))
        if not s['paragraphs']:issues.append(dict(source_id=r['source_id'],issue='empty'))
        for n,x in enumerate(s['paragraphs']):
            if x.get('origin_file')!=origin or x.get('origin_sha256')!=origins[origin]:issues.append(dict(source_id=r['source_id'],issue='paragraph_origin',paragraph=n+1))
            if r['source_type']=='official_transcript' and 'pdf_page' not in x:issues.append(dict(source_id=r['source_id'],issue='no_pdf_locator',paragraph=n+1))
            if r['source_type']=='automatic_transcript':
                fmt=Path(origin).suffix
                if origin not in original_text:
                    content=(ROOT/origin).read_text(encoding='utf-8-sig')
                    original_text[origin]=json.loads(content) if fmt=='.json' else content.splitlines()
                if fmt=='.json':
                    if not x.get('json_pointer'):issues.append(dict(source_id=r['source_id'],issue='no_JSON_locator',paragraph=n+1))
                    else:
                        obj=_pointer(original_text[origin],x['json_pointer'])
                        if clean(' '.join(t['text'] for t in obj['sentences']))!=x['text']:issues.append(dict(source_id=r['source_id'],issue='JSON_text_locator_mismatch',paragraph=n+1))
                elif fmt=='.txt':
                    if not (x.get('line_start') and x.get('line_end') and x.get('statement_timestamp')):issues.append(dict(source_id=r['source_id'],issue='no_TXT_locator',paragraph=n+1))
                    elif clean('\n'.join(original_text[origin][x['line_start']-1:x['line_end']]))!=x['text']:issues.append(dict(source_id=r['source_id'],issue='TXT_text_locator_mismatch',paragraph=n+1))
                else:issues.append(dict(source_id=r['source_id'],issue='unsupported_ASR_origin'))
            if re.match(r'^The (?:Acting )?President\s*[:(]',x['text']):issues.append(dict(source_id=r['source_id'],issue='chair_text',paragraph=n+1))
            if r['source_type']=='official_transcript' and any(ord(c)<32 and c not in '\r\n\t' for c in x['text']):issues.append(dict(source_id=r['source_id'],issue='control_character',paragraph=n+1))
        h=hashlib.sha256('\n'.join(x['text'] for x in s['paragraphs']).encode()).hexdigest()
        if h in bodies:issues.append(dict(source_id=r['source_id'],issue='duplicate_body',other=bodies[h]))
        bodies[h]=r['source_id']
    expected={r['source_id'] for r in rows if r['status']=='accepted' and r['representative']}
    normalized=list(read_jsonl(ROOT/'output/pipeline/speeches.jsonl'))
    for field in ('source_id','speech_id'):
        for value,count in Counter(r[field] for r in normalized).items():
            if count>1:issues.append(dict(issue='duplicate_normalized_'+field,value=value,count=count))
    for value,count in Counter(p['passage_id'] for r in normalized for p in r['passages']).items():
        if count>1:issues.append(dict(issue='duplicate_passage_id',value=value,count=count))
    if {r['source_id'] for r in normalized}!=expected:issues.append(dict(issue='normalized_manifest_set_mismatch'))
    manifest={r['source_id']:r for r in rows}
    for r in normalized:
        if r['sha256']!=manifest[r['source_id']]['sha256']:issues.append(dict(source_id=r['source_id'],issue='stale_normalized_source'))
        if any(p['ai_status']!='Pending' for p in r['passages']):issues.append(dict(source_id=r['source_id'],issue='unexpected_AI_label'))
        source=derived[r['source_id']]
        expected_text=' '.join(' '.join(p['text'].split()) for p in source['paragraphs'])
        actual_text=' '.join(' '.join(p['text'].split()) for p in r['passages'])
        if expected_text!=actual_text:issues.append(dict(source_id=r['source_id'],issue='passage_text_lost_reordered_or_duplicated'))
        for p in r['passages']:
            loc=p['locator'];block=source['paragraphs'][loc['extracted_block']-1]['text']
            if block[loc['char_start']:loc['char_end']]!=p['text']:issues.append(dict(passage_id=p['passage_id'],issue='passage_character_offsets'))
            limits=r['passage_settings']
            if len(p['text'].split())>limits['passage_max_words'] or len(p['text'])>limits['passage_max_chars']:issues.append(dict(passage_id=p['passage_id'],issue='passage_size'))
    raw=defaultdict(list)
    for p in (ROOT/'data').rglob('*.pdf'):raw[digest(p)].append(p.relative_to(ROOT).as_posix())
    remaining=[v for v in raw.values() if len(v)>1]
    result=dict(manifest_rows=len(rows),counts=dict(counts),issues=issues,remaining_byte_duplicate_PDF_groups=remaining,
        scope='Actual source hashes, unique representatives, dates, paragraph locations, chair labels, exact speech bodies and normalized input consistency; no audio or semantic validation')
    dump(ROOT/'output/corpus_preparation/input_integrity.json',result)
    print(json.dumps(dict(rows=len(rows),issues=len(issues),remaining_pdf_duplicate_groups=len(remaining))),flush=True)
    if issues or remaining:raise SystemExit(1)
    return result

if __name__=='__main__':main()
