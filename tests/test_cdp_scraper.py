import unittest
import sys
from pathlib import Path

# Les tests vivent dans tests/ ; on ajoute la racine du projet au sys.path pour
# pouvoir importer cdp_scraper quel que soit le dossier depuis lequel on lance
# la suite.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_scraper
import cdp_viewer  # pour le test garde-fou de version (scraper == viewer)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lire_fixture(nom: str) -> str:
    return (FIXTURES / nom).read_text(encoding="utf-8")


class _FakeResp:
    """Réponse minimale : `.text` pour crawler_progcolles ; `.headers` est ajouté ponctuellement pour nom_fichier."""

    def __init__(self, text: str):
        self.text = text


class _FakeSession:
    """Session hors-ligne : renvoie une page figée selon l'URL demandée."""

    def __init__(self, pages: dict):
        self.pages = pages

    def get(self, url, timeout=None):
        if url not in self.pages:
            raise KeyError(f"URL inattendue dans _FakeSession : {url!r}")
        return _FakeResp(self.pages[url])


class TestVersion(unittest.TestCase):
    """Le versioning est unifié : scraper et viewer partagent la même version."""

    def test_versions_egales(self):
        self.assertEqual(cdp_scraper.__version__, cdp_viewer.__version__)

    def test_version_attendue(self):
        self.assertEqual(cdp_scraper.__version__, "1.2.0")


class TestAnalyserPage(unittest.TestCase):
    """Vérifie l'extraction des documents depuis une page docs cahier-de-prepa."""

    URL = "https://cahier-de-prepa.fr/maclasse/docs"

    def test_doc_pdf_simple(self):
        # Un PDF n'a pas de lien « icon-play » : un seul href.
        page = (
            '<section>'
            '<p class="doc"><span class="docdonnees">(pdf, 1 jan, 100 ko)</span> '
            '<a href="download?id=42&amp;v=abcde">'
            '<span class="icone"></span><span class="nom">Cours 1</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "42")
        self.assertEqual(docs[0]["nom"], "Cours 1")
        self.assertEqual(docs[0]["type"], "pdf")
        self.assertEqual(
            docs[0]["url"],
            "https://cahier-de-prepa.fr/maclasse/download?id=42&dl",
        )

    def test_doc_audio_ignore_le_lien_voir(self):
        # Audio : le bloc contient D'ABORD un lien icon-play en &voir (page
        # lecteur HTML), puis le vrai lien. L'URL de téléchargement ne doit PAS
        # être le lien &voir, sinon on récupère du HTML au lieu du binaire.
        page = (
            '<section>'
            '<p class="doc"><span class="docdonnees">(mp3, 1 jan, 2 Mo)</span> '
            '<a class="icon-play" href="download?id=3013&amp;v=fae0d&amp;voir" '
            'title="Écouter directement ici l\'audio"></a>&nbsp;'
            '<a href="download?id=3013&amp;v=fae0d">'
            '<span class="icone"></span><span class="nom">10</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "3013")
        self.assertEqual(docs[0]["type"], "mp3")
        self.assertNotIn("voir", docs[0]["url"])
        self.assertEqual(
            docs[0]["url"],
            "https://cahier-de-prepa.fr/maclasse/download?id=3013&dl",
        )

    def test_sous_dossier(self):
        page = (
            '<section>'
            '<p class="rep"><a href="?rep=7">'
            '<span class="nom">Chapitre 2</span></a></p>'
            '</section>'
        )
        reps, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(docs, [])
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["nom"], "Chapitre 2")
        self.assertTrue(reps[0]["url"].endswith("/maclasse/docs?rep=7"))

    def test_documents_recents_ignore(self):
        # Le bloc « Documents récents » liste des docs dont le nom contient le
        # chemin (« Matière/… ») : ils doivent être ignorés (récupérés ailleurs).
        page = (
            '<section>'
            '<p class="doc"><span class="docdonnees">(pdf, 1 jan, 100 ko)</span> '
            '<a href="download?id=99&amp;v=zzz">'
            '<span class="icone"></span><span class="nom">Physique/TD/TD1</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(docs, [])

    def test_melange_dossiers_et_documents(self):
        page = (
            '<section>'
            '<p class="rep"><a href="?rep=5">'
            '<span class="nom">Cours</span></a></p>'
            '<p class="doc"><span class="docdonnees">(pdf, 1 jan, 100 ko)</span> '
            '<a href="download?id=7&amp;v=aaa">'
            '<span class="icone"></span><span class="nom">Intro</span></a></p>'
            '</section>'
        )
        reps, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["nom"], "Cours")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["nom"], "Intro")

    def test_doc_sans_docdonnees(self):
        # Sans bloc docdonnees : type vide, mais URL toujours en &dl.
        page = (
            '<section>'
            '<p class="doc">'
            '<a href="download?id=8&amp;v=bbb">'
            '<span class="icone"></span><span class="nom">Sans type</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["type"], "")
        self.assertEqual(
            docs[0]["url"],
            "https://cahier-de-prepa.fr/maclasse/download?id=8&dl",
        )

    def test_entites_html_dans_nom(self):
        # &amp; et accents encodés doivent être déséchappés dans le nom.
        page = (
            '<section>'
            '<p class="doc"><span class="docdonnees">(pdf, 1 jan, 100 ko)</span> '
            '<a href="download?id=9&amp;v=ccc">'
            '<span class="icone"></span>'
            '<span class="nom">Alg&egrave;bre &amp; G&eacute;om&eacute;trie</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(docs[0]["nom"], "Algèbre & Géométrie")


class TestProgcolles(unittest.TestCase):
    BASE = "https://cahier-de-prepa.fr/maclasse"

    def test_mode_pdf_par_semaine(self):
        menu = '<a href="progcolles?maths">Colles de maths</a>'
        session = _FakeSession({
            self.BASE + "/docs": menu,
            self.BASE + "/progcolles?maths&tout": _lire_fixture("progcolles_pdf.html"),
        })
        res = cdp_scraper.crawler_progcolles(session, self.BASE)
        self.assertEqual(len(res), 2)
        for d in res:
            self.assertEqual(d["type"], "pdf")
            self.assertEqual(d["chemin"], "Maths/Programme de colles")
            self.assertTrue(d["url"].endswith("&dl"))
        noms = {d["nom"] for d in res}
        self.assertEqual(noms, {"Semaine 1", "Semaine 2"})  # suffixe « (pdf) » retiré

    def test_mode_texte(self):
        menu = '<a href="progcolles?phys">Colles de physique</a>'
        session = _FakeSession({
            self.BASE + "/docs": menu,
            self.BASE + "/progcolles?phys&tout": _lire_fixture("progcolles_texte.html"),
        })
        res = cdp_scraper.crawler_progcolles(session, self.BASE)
        self.assertEqual(len(res), 1)
        doc = res[0]
        self.assertIn("contenu_html", doc)
        self.assertEqual(doc["chemin"], "Physique")
        self.assertIn("Mecanique du point", doc["contenu_html"])
        # Le <script>var x... de la source doit être supprimé ; le <script> MathJax
        # injecté par _html_progcolles dans le <head> est attendu et non compté ici.
        self.assertNotIn("var x = 1", doc["contenu_html"])
        self.assertNotIn("recherchecolle", doc["contenu_html"])
        self.assertNotIn('id="icones"', doc["contenu_html"])

    def test_contenu_protege_ignore(self):
        menu = '<a href="progcolles?secret">Colles</a>'
        session = _FakeSession({
            self.BASE + "/docs": menu,
            self.BASE + "/progcolles?secret&tout":
                "<html><body>Ce contenu est protégé</body></html>",
        })
        res = cdp_scraper.crawler_progcolles(session, self.BASE)
        self.assertEqual(res, [])

    def test_aucun_programme(self):
        session = _FakeSession({self.BASE + "/docs": "<html><body>rien</body></html>"})
        self.assertEqual(cdp_scraper.crawler_progcolles(session, self.BASE), [])


class TestHtmlProgcolles(unittest.TestCase):
    def test_nettoyage_et_autonomie(self):
        page = _lire_fixture("progcolles_texte.html")
        out = cdp_scraper._html_progcolles(page, "Physique")
        self.assertIsNotNone(out)
        self.assertTrue(out.lstrip().startswith("<!doctype html>"))
        self.assertIn("Programme de colles - Physique", out)
        self.assertNotIn("<script>var", out)
        self.assertNotIn("recherchecolle", out)

    def test_section_vide_renvoie_none(self):
        page = "<html><body><section></section></body></html>"
        self.assertIsNone(cdp_scraper._html_progcolles(page, "Physique"))


class TestUtilitaires(unittest.TestCase):
    def test_nom_sur_caracteres_interdits(self):
        # ? et " sont deux caractères distincts → deux underscores consécutifs d__e
        self.assertEqual(cdp_scraper.nom_sur('a/b:c*d?"e<f>g|h'), "a_b_c_d__e_f_g_h")

    def test_nom_sur_troncature_200(self):
        self.assertEqual(len(cdp_scraper.nom_sur("x" * 300)), 200)

    def test_nom_sur_fallback(self):
        self.assertEqual(cdp_scraper.nom_sur("..."), "document")

    def test_nom_fichier_content_disposition_prioritaire(self):
        resp = _FakeResp("")
        resp.headers = {"Content-Disposition": 'attachment; filename="vrai_nom.pdf"'}
        nom = cdp_scraper.nom_fichier(resp, {"nom": "affiche", "type": "pdf"})
        self.assertEqual(nom, "vrai_nom.pdf")

    def test_nom_fichier_repli_nom_plus_extension(self):
        resp = _FakeResp("")
        resp.headers = {}
        nom = cdp_scraper.nom_fichier(resp, {"nom": "Cours", "type": "pdf"})
        self.assertEqual(nom, "Cours.pdf")

    def test_cle_rep_retire_parametres_affichage(self):
        a = cdp_scraper._cle_rep("https://x/docs?rep=7&ordre=nom&v=abc")
        b = cdp_scraper._cle_rep("https://x/docs?rep=7")
        self.assertEqual(a, b)
        self.assertEqual(a, "rep=7")

    def test_cle_rep_racine(self):
        self.assertEqual(cdp_scraper._cle_rep("https://x/docs"), "")


if __name__ == "__main__":
    unittest.main()
