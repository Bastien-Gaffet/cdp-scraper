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
        self.assertNotIn("/file/secret", out)   # aucune src vers l'extérieur

    def test_html_inline_de_la_source_non_propage(self):
        out = self.r("<script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_nul_dans_la_source_ne_plante_pas(self):
        self.assertEqual(self.r("\x00"), "")
        self.assertNotIn("\x00", self.r("texte \x005\x00 suite"))

    def test_nul_ne_duplique_pas_un_jeton(self):
        out = self.r("`code`\x000\x00")
        self.assertEqual(out.count("<code>"), 1)


class TestBlocs(unittest.TestCase):
    def c(self, src, prefixe="", colorier_python=None):
        return cdp_markdown.convertir(src, prefixe, colorier_python)

    def test_titres(self):
        out = self.c("# Titre\n\n## Sous-titre")
        self.assertIn("<h1>Titre</h1>", out)
        self.assertIn("<h2>Sous-titre</h2>", out)

    def test_paragraphe(self):
        out = self.c("Ligne un\nligne deux\n\nAutre para")
        self.assertIn("<p>Ligne un ligne deux</p>", out)
        self.assertIn("<p>Autre para</p>", out)

    def test_regle_horizontale(self):
        self.assertIn("<hr>", self.c("a\n\n---\n\nb"))

    def test_citation(self):
        out = self.c("> citée\n> suite")
        self.assertIn("<blockquote>", out)
        self.assertIn("citée suite", out)

    def test_liste_a_puces(self):
        out = self.c("- un\n- deux")
        self.assertIn("<ul>", out)
        self.assertEqual(out.count("<li>"), 2)

    def test_liste_numerotee(self):
        self.assertIn("<ol>", self.c("1. un\n2. deux"))

    def test_liste_imbriquee(self):
        out = self.c("- un\n  - sous\n- deux")
        self.assertIn("<ul><li>un<ul><li>sous</li></ul></li>", out)

    def test_table_gfm(self):
        out = self.c("| a | b |\n| - | - |\n| 1 | 2 |")
        self.assertIn("<table>", out)
        self.assertIn("<th>a</th>", out)
        self.assertIn("<td>1</td>", out)

    def test_bloc_code_sans_langage_echappe(self):
        out = self.c("```\na < b\n```")
        self.assertIn("<pre><code>", out)
        self.assertIn("a &lt; b", out)
        self.assertNotIn('class="kw"', out)

    def test_bloc_code_langage_colore(self):
        out = self.c("```c\nint x = 1;\n```")
        self.assertIn('<span class="kw">int</span>', out)

    def test_bloc_code_python_via_callback(self):
        appels = []

        def faux_python(code):
            appels.append(code)
            return '<span class="kw">import</span> os'

        out = self.c("```python\nimport os\n```", colorier_python=faux_python)
        self.assertEqual(appels, ["import os"])
        self.assertIn('<span class="kw">import</span>', out)

    def test_inline_dans_les_blocs(self):
        self.assertIn("<strong>x</strong>", self.c("# **x**"))

    def test_entree_vide(self):
        self.assertEqual(self.c(""), "")

    def test_bloc_code_non_termine_a_la_fin(self):
        out = self.c("```\na < b")          # pas de clôture
        self.assertIn("a &lt; b", out)       # pas de crash, contenu échappé

    def test_blockquotes_tres_profonds_ne_plantent_pas(self):
        out = self.c("> " * 996 + "x")       # ne doit pas lever RecursionError
        self.assertIn("x", out)

    def test_table_sans_lignes_de_corps(self):
        out = self.c("| a | b |\n| - | - |")
        self.assertIn("<th>a</th>", out)     # en-tête seul, pas de crash

    def test_table_apres_paragraphe_sans_ligne_vide(self):
        out = self.c("texte\n| a | b |\n| - | - |\n| 1 | 2 |")
        self.assertIn("<table>", out)
        self.assertIn("<td>1</td>", out)

    def test_echappement_dans_cellule_et_titre(self):
        self.assertIn("&lt;script&gt;", self.c("# <script>"))
        self.assertIn("&lt;script&gt;", self.c("| <script> |\n| - |\n| x |"))


if __name__ == "__main__":
    unittest.main()
