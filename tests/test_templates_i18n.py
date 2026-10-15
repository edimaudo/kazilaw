import unittest
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader
from translations import TRANSLATIONS, get_translations

ROOT = Path(__file__).resolve().parents[1]
ENV = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)


class TemplateI18nTests(unittest.TestCase):
    def test_template_translation_keys_exist_in_both_locales(self):
        template_files = ["base.html", "index.html", "audit.html", "qa.html", "lawyers.html", "404.html"]
        import re
        for filename in template_files:
            source = (ROOT / "templates" / filename).read_text()
            keys = set(re.findall(r'data-i18n(?:-placeholder|-aria-label)?="([a-z_]+)"', source))
            keys.update(re.findall(r'data-i18n-province="([A-Z]{2})"', source))
            for key in keys:
                if len(key) == 2 and key.isupper():
                    self.assertIn(key, TRANSLATIONS["en"]["provinces"])
                    self.assertIn(key, TRANSLATIONS["fr"]["provinces"])
                else:
                    self.assertIn(key, TRANSLATIONS["en"], f"{filename}: missing EN key {key}")
                    self.assertIn(key, TRANSLATIONS["fr"], f"{filename}: missing FR key {key}")

    def test_all_pages_render_for_english_and_french(self):
        cases = {
            "/": ("index.html", "landing_meta_title"),
            "/audit": ("audit.html", "audit_title"),
            "/qa": ("qa.html", "qa_title"),
            "/lawyers": ("lawyers.html", "lawyers_title"),
            "/missing-page": ("404.html", "not_found_title"),
        }
        for language in ("en", "fr"):
            for path, (filename, title_key) in cases.items():
                with self.subTest(language=language, path=path):
                    rendered = ENV.get_template(filename).render(
                        request=SimpleNamespace(path=path),
                        language=language,
                        html_lang="fr-CA" if language == "fr" else "en-CA",
                        t=get_translations(language),
                        all_translations=TRANSLATIONS,
                        page_title_key=title_key,
                        specialists=[],
                    )
                    expected_lang = 'lang="fr-CA"' if language == "fr" else 'lang="en-CA"'
                    self.assertIn(expected_lang, rendered)
                    self.assertIn('id="language-select"', rendered)
                    self.assertNotIn("{{", rendered)
                    self.assertNotIn("{%", rendered)


if __name__ == "__main__":
    unittest.main()
