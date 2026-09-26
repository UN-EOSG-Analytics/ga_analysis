import unittest
import tempfile
from pathlib import Path
from unga_analysis.selection import select_pdf_version, quarantine_non_english_alternatives
from unga_analysis.contracts import validate_manifest


class LanguageSelectionTests(unittest.TestCase):
    def version(self, lang, chars=1000, eligible=True):
        return dict(lang=lang, extracted_chars=chars, source_eligible=eligible, file=lang+'.pdf')

    def test_english_wins_even_when_french_has_more_text(self):
        en, fr = self.version('EN'), self.version('fr', 5000)
        self.assertIs(select_pdf_version([fr, en]), en)

    def test_unreadable_english_does_not_fall_back(self):
        en = self.version('en', 0)
        self.assertIs(select_pdf_version([self.version('fr'), en]), en)

    def test_without_english_exactly_one_version_is_selected(self):
        fr = self.version('fr')
        self.assertIs(select_pdf_version([self.version('es'), fr]), fr)

    def test_manifest_rejects_french_representative_with_pending_english(self):
        fr = dict(source_id='fr', speech_id='2025_FRA', country_iso3='FRA', year=2025,
                  path='fr.pdf', format='pdf', source_type='submitted_statement',
                  speech_kind='main_general_debate', entity_type='member_state',
                  status='accepted', representative=True, language='fr')
        en = dict(fr, source_id='en', path='en.pdf', language='EN', status='pending', representative=False)
        with self.assertRaisesRegex(ValueError, 'English version exists'):
            validate_manifest([fr, en])

    def test_existing_non_english_is_quarantined_without_reprocessing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'france__fr_en.pdf').touch()
            row = dict(source_id='legacy_pdf_2025_FRA', path='france__fr_fr.pdf',
                       language='fr', status='accepted', representative=True)
            quarantine_non_english_alternatives(root, [row])
            self.assertEqual(row['status'], 'quarantined')
            self.assertFalse(row['representative'])
            self.assertEqual(row['english_version_paths'], ['france__fr_en.pdf'])


if __name__ == '__main__':
    unittest.main()
