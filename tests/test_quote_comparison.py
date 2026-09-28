import unittest
from unga_analysis.analysis.common import quote_in


class QuoteComparisonTests(unittest.TestCase):
    def test_typographic_variants_match_without_changing_inputs(self):
        source='the Secretary\u2011General\u2019s \u201creport\u201d'
        quote='Secretary-General\'s "report"';original=source
        self.assertTrue(quote_in(quote,source));self.assertEqual(source,original)
        self.assertEqual(quote,'Secretary-General\'s "report"')

    def test_nfkc_dashes_and_whitespace_are_comparison_only(self):
        self.assertTrue(quote_in('AI systems - public safety','\uff21\uff29\u00a0systems\n\u2014 public safety'))
        for dash in '\u2010\u2011\u2012\u2013\u2014\u2015\u2212':self.assertTrue(quote_in('AI-led','AI'+dash+'led'))

    def test_normalization_does_not_allow_paraphrases_or_discontinuous_quotes(self):
        for quote in ('AI safety','AI ... safety','ai and safety','AI or safety',''):
            self.assertFalse(quote_in(quote,'AI and safety'))
        self.assertFalse(quote_in('SecretaryGeneral','Secretary-General'))
