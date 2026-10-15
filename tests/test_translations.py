import unittest
from translations import get_translations


class TranslationCatalogTests(unittest.TestCase):
    def test_english_is_default(self):
        self.assertEqual(get_translations()["contract_review"], "Contract Review")
        self.assertEqual(get_translations("unsupported")["language"], "Language")

    def test_french_canadian_strings(self):
        fr = get_translations("fr")
        self.assertEqual(fr["contract_review"], "Analyse de contrat")
        self.assertEqual(fr["provinces"]["QC"], "Québec")
        self.assertEqual(fr["provinces"]["BC"], "Colombie-Britannique")

    def test_all_provinces_and_territories_are_localized(self):
        expected = {"AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK", "NT", "NU", "YT"}
        self.assertEqual(set(get_translations("en")["provinces"]), expected)
        self.assertEqual(set(get_translations("fr")["provinces"]), expected)


if __name__ == "__main__":
    unittest.main()
