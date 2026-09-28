"""Local candidate search; never assigns AI/theme labels or calls a model."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import unicodedata

from .contracts import validate_manifest
from .io import digest, read_jsonl, write_jsonl


def normalized_with_offsets(text):
    """Normalize search text while retaining exact original character positions."""
    chars, offsets = [], []
    for i, char in enumerate(text):
        if char == '\u00ad':
            continue
        for value in unicodedata.normalize('NFKC', char).casefold():
            chars.append('-' if value in '\u2010\u2011\u2012\u2013\u2014\u2212' else value)
            offsets.append(i)
    value = ''.join(chars)
    # Join a word split by a PDF line-end hyphen, preserving source locators.
    removed = set()
    for match in re.finditer(r'(?<=\w)-[ \t]*\n[ \t]*(?=\w)', value):
        removed.update(range(match.start(), match.end()))
    if removed:
        kept = [i for i in range(len(chars)) if i not in removed]
        value = ''.join(chars[i] for i in kept)
        offsets = [offsets[i] for i in kept]
    return value, offsets


def find_terms(text, rules):
    normalized, offsets = normalized_with_offsets(text)
    hits = []
    for rule in rules:
        for match in re.finditer(rule['pattern'], normalized):
            start, end = offsets[match.start()], offsets[match.end() - 1] + 1
            original = text[start:end]
            if rule.get('spaced_acronym_requires_uppercase') and any(c.isspace() for c in original) and '.' not in original:
                # "as I" is ordinary prose, not the acronym ASI.
                if not ''.join(c for c in original if c.isalpha()).isupper():
                    continue
            hits.append(dict(rule=rule['id'], tier=rule['tier'], start=start,
                             end=end, matched_text=text[start:end]))
    return sorted(hits, key=lambda hit: (hit['start'], hit['end'], hit['rule']))


def screen(root):
    root = Path(root).resolve()
    input_path = root/'output/pipeline/speeches.jsonl'
    lexicon_path = root/'config/ai_search_terms.json'
    manifest_path = root/'config/source_manifest.jsonl'
    lexicon = json.loads(lexicon_path.read_text(encoding='utf-8'))
    manifest = validate_manifest(list(read_jsonl(manifest_path)))
    selected = {r['source_id']: r for r in manifest if r['status']=='accepted' and r['representative']}
    rows = list(read_jsonl(input_path))
    counts = Counter(r['source_id'] for r in rows)
    if any(n != 1 for n in counts.values()) or set(counts) != set(selected):
        raise ValueError('Normalized input must contain each selected source exactly once')
    if len({r['speech_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate country-year in screening input')
    hits, coverage = [], []
    tiers = defaultdict(set)
    for row in rows:
        source = selected[row['source_id']]
        if row['sha256'] != source['sha256'] or row['source_type'] != source['source_type']:
            raise ValueError('Stale normalized source metadata')
        if row['source_type'] not in ('official_transcript', 'automatic_transcript'):
            raise ValueError('Transcript-only canonical input required; PDFs are comparison evidence')
        chunks, spans, position = [], [], 0
        for passage in row['passages']:
            if chunks:
                chunks.append('\n')
                position += 1
            chunks.append(passage['text'])
            spans.append((position, position + len(passage['text']), passage))
            position += len(passage['text'])
        text = ''.join(chunks)
        matches = find_terms(text, lexicon['rules'])
        for hit in matches:
            evidence = []
            for start, end, passage in spans:
                if start < hit['end'] and end > hit['start']:
                    evidence.append(dict(passage_id=passage['passage_id'], locator=passage['locator'],
                                         match_start_in_passage=max(hit['start']-start, 0),
                                         match_end_in_passage=min(hit['end']-start, end-start)))
            hits.append(dict(speech_id=row['speech_id'], year=row['year'], country_iso3=row['country_iso3'],
                             source_id=row['source_id'], source_sha256=row['sha256'], **hit,
                             context=text[max(0, hit['start']-250):hit['end']+350], evidence=evidence,
                             review_status='Pending', ai_status='Pending',
                             source_review_notes=row.get('source_review_notes')))
            tiers[hit['tier']].add(row['speech_id'])
        coverage.append(dict(speech_id=row['speech_id'], year=row['year'],
                             candidate_matches=len(matches), tiers=sorted({m['tier'] for m in matches}),
                             ai_status='Pending', negative_review_required=not bool(matches)))
    destination = root/'output/screening'
    write_jsonl(destination/'ai_candidates.jsonl', hits)
    write_jsonl(destination/'speech_screening.jsonl', coverage)
    summary = dict(screened_at_utc=datetime.now(timezone.utc).isoformat(),
                   input_sha256=digest(input_path), manifest_sha256=digest(manifest_path),
                   lexicon_sha256=digest(lexicon_path), code_sha256=digest(Path(__file__)),
                   lexicon_version=lexicon['version'], speeches=len(rows),
                   passages=sum(len(r['passages']) for r in rows), candidate_matches=len(hits),
                   candidate_speeches=len({h['speech_id'] for h in hits}),
                   candidate_speeches_by_tier={k: len(v) for k, v in tiers.items()},
                   matches_by_rule=dict(Counter(h['rule'] for h in hits)),
                   counts_by_year=dict(Counter(str(r['year']) for r in rows)),
                   no_match_is_not_negative=True, labels_changed=False, paid_api_calls=0,
                   limitations=['Finite lexicon cannot guarantee recall of every paraphrase or ASR error.',
                                'Overlapping rules may match one phrase; match counts are not country counts.',
                                'Review contextual matches and screened negatives before final statistics.'])
    (destination/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary
