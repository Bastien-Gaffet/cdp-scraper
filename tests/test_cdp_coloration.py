import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_coloration
import re


def _detag(html_str):
    """Retire les <span ...> et </span> pour reconstituer le texte source."""
    return re.sub(r"</?span[^>]*>", "", html_str)


class TestColoration(unittest.TestCase):
    def test_langage_inconnu_renvoie_none(self):
        self.assertIsNone(cdp_coloration.colorier("x = 1", "brainfuck"))

    def test_python_non_gere_ici(self):
        # Python reste sur tokenize dans le viewer : pas dans cdp_coloration.
        self.assertNotIn("py", cdp_coloration.LANGAGES)
        self.assertNotIn("python", cdp_coloration.LANGAGES)

    def test_c_colore_mot_cle_chaine_commentaire_nombre(self):
        src = 'int x = 42; // commentaire\nchar *s = "abc";'
        out = cdp_coloration.colorier(src, "c")
        self.assertIsNotNone(out)
        self.assertIn('<span class="kw">int</span>', out)
        self.assertIn('<span class="num">42</span>', out)
        self.assertIn('<span class="com">// commentaire</span>', out)
        self.assertIn('<span class="str">"abc"</span>', out)

    def test_commentaire_bloc_c(self):
        out = cdp_coloration.colorier("a /* bloc\nsuite */ b", "c")
        self.assertIn('<span class="com">/* bloc\nsuite */</span>', out)

    def test_preservation_exacte_du_source(self):
        src = 'int main(void) {\n    return 0;  // ok\n}\n'
        out = cdp_coloration.colorier(src, "c")
        self.assertEqual(_detag(out), src)

    def test_echappement_html(self):
        out = cdp_coloration.colorier("a < b && c > d", "c")
        self.assertIn("&lt;", out)
        self.assertIn("&amp;&amp;", out)
        self.assertIn("&gt;", out)
        self.assertNotIn("<b", out)  # aucun < littéral injecté

    def test_sql_mots_cles_insensibles_a_la_casse(self):
        out = cdp_coloration.colorier("select * from t WHERE x = 1", "sql")
        self.assertIn('<span class="kw">select</span>', out)
        self.assertIn('<span class="kw">WHERE</span>', out)

    def test_json_true_false_null(self):
        out = cdp_coloration.colorier('{"a": true, "b": null}', "json")
        self.assertIn('<span class="kw">true</span>', out)
        self.assertIn('<span class="kw">null</span>', out)
        self.assertIn('<span class="str">"a"</span>', out)

    def test_langages_couverts_presents(self):
        for lang in ("c", "cpp", "java", "sql", "r", "ml", "json"):
            self.assertIn(lang, cdp_coloration.LANGAGES, lang)
            self.assertIsNotNone(cdp_coloration.colorier("x", lang), lang)


if __name__ == "__main__":
    unittest.main()
