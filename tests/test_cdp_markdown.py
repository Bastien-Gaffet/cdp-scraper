import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_markdown


class TestInline(unittest.TestCase):
    def r(self, texte, prefixe=""):
        return cdp_markdown.rendre_inline(texte, prefixe)

    def test_echappement_du_texte(self):
        self.assertEqual(self.r("a < b & c"), "a &lt; b &amp; c")

    def test_gras_et_italique(self):
        self.assertIn("<strong>gras</strong>", self.r("**gras**"))
        self.assertIn("<em>ital</em>", self.r("*ital*"))

    def test_code_inline_echappe_et_non_interprete(self):
        out = self.r("voir `a < **b**`")
        self.assertIn("<code>a &lt; **b**</code>", out)
        self.assertNotIn("<strong>", out)  # pas d'emphase dans le code

    def test_lien_http_externe(self):
        out = self.r("[site](https://exemple.fr)")
        self.assertIn('href="https://exemple.fr"', out)
        self.assertIn('rel="noopener noreferrer"', out)
        self.assertIn(">site</a>", out)

    def test_lien_javascript_neutralise(self):
        out = self.r("[clic](javascript:alert(1))")
        self.assertNotIn("href", out)
        self.assertNotIn("javascript", out)
        self.assertIn("clic", out)

    def test_image_locale_resolue_sous_le_prefixe(self):
        out = self.r("![schéma](figures/x.png)", "/file/PCSI/Maths")
        self.assertIn('<img src="/file/PCSI/Maths/figures/x.png"', out)
        self.assertIn('alt="sch', out)

    def test_image_traversal_neutralisee(self):
        out = self.r("![x](../../secret.png)", "/file/PCSI/Maths")
        self.assertNotIn("<img", out)
        self.assertNotIn("secret", out.replace("x", ""))  # pas de src vers secret

    def test_html_inline_de_la_source_non_propage(self):
        out = self.r("<script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)


if __name__ == "__main__":
    unittest.main()
