import unittest
import sys
from pathlib import Path

# Les tests vivent dans tests/ ; on ajoute la racine du projet au sys.path pour
# pouvoir importer cdp_scraper quel que soit le dossier depuis lequel on lance
# la suite.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_scraper


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


if __name__ == "__main__":
    unittest.main()
