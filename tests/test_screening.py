import json
from pathlib import Path
import shutil
from contextlib import contextmanager
from uuid import uuid4
import unittest

from unga_analysis.contracts import validate_manifest
from unga_analysis.io import digest, read_jsonl, write_jsonl
from unga_analysis.screening import find_terms, screen

PROJECT = Path(__file__).resolve().parents[1]
RULES = json.loads((PROJECT/'config/ai_search_terms.json').read_text(encoding='utf-8'))['rules']


@contextmanager
def temporary_project():
    # Inherit workspace ACLs; Python 3.13's private Windows temp ACL can deny
    # access to the restricted process identity used by the local runner.
    path = (PROJECT / ('.screening-test-' + uuid4().hex)).resolve()
    assert path.is_relative_to(PROJECT.resolve())
    path.mkdir()
    try:
        yield path
    finally:
        assert path.is_relative_to(PROJECT.resolve()) and path != PROJECT.resolve()
        shutil.rmtree(path)


class ScreeningTests(unittest.TestCase):
    def test_requested_variants(self):
        for term in ['AI', 'ai', 'A.I.', 'A I', 'Artificial Intelligence',
                     'artificial-intelligence', 'ARTIFICIAL INTELLIGENCE',
                     'superintelligence', 'Super Intelligence', 'super-intelligence',
                     'artificial general intelligence', 'artificial superintelligence',
                     'AGI', 'ASI', 'A G I', 'A S I', 'a.g.i.', 'SI', 'GenAI', 'generative AI',
                     'superhuman intelligence', 'human-level intelligence']:
            with self.subTest(term=term):
                self.assertTrue(find_terms(term, RULES))

    def test_substrings_and_military_intelligence_are_not_ai(self):
        self.assertEqual(find_terms('said aid AIDS AIIB Haiti military intelligence intelligence services. As I said, as I see it.', RULES), [])

    def test_related_terms_and_context_are_distinct(self):
        self.assertEqual(find_terms('machine learning', RULES)[0]['tier'], 'ai_related')
        self.assertEqual(find_terms('algorithms', RULES)[0]['tier'], 'context_only')
        self.assertEqual(find_terms('AGI', RULES)[0]['tier'], 'context_required')

    def test_unicode_and_line_breaks_preserve_offsets(self):
        for term in ['arti\ufb01cial intelligence', 'arti\u00adficial intelligence',
                     '\uff21\uff29', 'artifi-\ncial intelligence',
                     'artificial-\nintelligence', 'artificial\nintelligence',
                     'super\u2011intelligence']:
            text = 'Before ' + term + ' after'
            hits = find_terms(text, RULES)
            self.assertTrue(hits, term)
            self.assertEqual(hits[0]['matched_text'], term)
            self.assertEqual(text[hits[0]['start']:hits[0]['end']], term)

    def sample(self, root):
        (root/'config').mkdir()
        shutil.copy2(PROJECT/'config/ai_search_terms.json', root/'config/ai_search_terms.json')
        source = dict(source_id='s', speech_id='2025_VCT', country_iso3='VCT', year=2025,
                      path='data/x.json', format='json', source_type='automatic_transcript',
                      speech_kind='main_general_debate', entity_type='member_state',
                      status='accepted', representative=True, language='en', sha256='example')
        write_jsonl(root/'config/source_manifest.jsonl', [source])
        row = dict(source, source_review_notes={'status':'pending_delivery_verification'},
                   passages=[dict(passage_id='s:1', text='We discuss artificial', locator={'pdf_page':1}, ai_status='Pending'),
                             dict(passage_id='s:2', text='intelligence and peace.', locator={'pdf_page':2}, ai_status='Pending')])
        write_jsonl(root/'output/pipeline/speeches.jsonl', [row])
        return row

    def test_boundary_search_preserves_input_and_review_note(self):
        with temporary_project() as temp:
            root = Path(temp)
            self.sample(root)
            path = root/'output/pipeline/speeches.jsonl'
            before = digest(path)
            result = screen(root)
            self.assertEqual(before, digest(path))
            self.assertEqual(result['candidate_speeches'], 1)
            match = list(read_jsonl(root/'output/screening/ai_candidates.jsonl'))[0]
            self.assertEqual(len(match['evidence']), 2)
            self.assertEqual(match['ai_status'], 'Pending')
            self.assertEqual(match['source_review_notes']['status'], 'pending_delivery_verification')

    def test_duplicate_normalized_rows_rejected(self):
        with temporary_project() as temp:
            root = Path(temp)
            row = self.sample(root)
            write_jsonl(root/'output/pipeline/speeches.jsonl', [row, row])
            with self.assertRaisesRegex(ValueError, 'exactly once'):
                screen(root)

    def test_pdf_and_transcript_representative_conflict_rejected(self):
        with temporary_project() as temp:
            root = Path(temp)
            row = self.sample(root)
            duplicate = dict(row, source_id='prepared_pdf', source_type='submitted_statement')
            with self.assertRaisesRegex(ValueError, 'Multiple accepted representative'):
                validate_manifest([row, duplicate])

    def test_no_match_remains_pending(self):
        with temporary_project() as temp:
            root = Path(temp)
            row = self.sample(root)
            row['passages'][0]['text'] = 'Peace and security.'
            row['passages'][1]['text'] = 'Public health.'
            write_jsonl(root/'output/pipeline/speeches.jsonl', [row])
            screen(root)
            coverage = list(read_jsonl(root/'output/screening/speech_screening.jsonl'))[0]
            self.assertTrue(coverage['negative_review_required'])
            self.assertEqual(coverage['ai_status'], 'Pending')
