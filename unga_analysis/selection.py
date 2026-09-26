"""One analytical language version per country-year; English takes precedence."""
import re
from pathlib import Path

LANGUAGE_PRIORITY = {'en': 0, 'fr': 1, 'es': 2, 'pt': 3, 'ru': 4, 'ar': 5, 'zh': 6, 'fl': 7}


def language_code(value):
    return str(value or '').strip().lower().replace('_', '-').split('-')[0]


def select_pdf_version(versions):
    """An unreadable EN stays selected/unresolved; never silently fall back to FR."""
    if not versions:
        raise ValueError('No source versions')
    english = [v for v in versions if language_code(v['lang']) == 'en']
    pool = english or versions
    return min(pool, key=lambda v: (
        not v['source_eligible'], v['extracted_chars'] < 500,
        LANGUAGE_PRIORITY.get(language_code(v['lang']), 8),
        -v['extracted_chars'], v['file']))


def quarantine_non_english_alternatives(root, records):
    """Do not accept a non-EN PDF representative when its data folder has EN."""
    for row in records:
        if Path(row['path']).suffix.lower() != '.pdf' or language_code(row.get('language')) == 'en':
            continue
        path = Path(root) / row['path']
        if '__' not in path.name:
            continue
        country = path.name.split('__')[0]
        english = sorted(p for p in path.parent.glob('*.pdf')
                         if p.name.split('__')[0] == country
                         and re.search(r'_en(?:\d+|_\d+)?\.pdf$', p.name, re.I))
        if english:
            row.update(status='quarantined', representative=False,
                       exclusion_reason='EN exists; non-EN excluded. Verify English year/content/readability before selecting it. No automatic language fallback.',
                       english_version_paths=[p.relative_to(root).as_posix() for p in english])
    return records
