import unittest
from pathlib import Path
import tempfile
import json
import threading
import urllib.request
import urllib.error

import cdp_viewer


class TestResoudreDansRacine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        (self.racine / "PCSI").mkdir()
        (self.racine / "PCSI" / "cours.pdf").write_bytes(b"%PDF-1.4 test")

    def tearDown(self):
        self.tmp.cleanup()

    def test_chemin_interne_resolu(self):
        cible = cdp_viewer.resoudre_dans_racine(self.racine, "PCSI/cours.pdf")
        self.assertEqual(cible, (self.racine / "PCSI" / "cours.pdf").resolve())

    def test_racine_elle_meme_autorisee(self):
        self.assertEqual(cdp_viewer.resoudre_dans_racine(self.racine, ""), self.racine.resolve())

    def test_traversal_rejete(self):
        self.assertIsNone(cdp_viewer.resoudre_dans_racine(self.racine, "../secret.txt"))
        self.assertIsNone(cdp_viewer.resoudre_dans_racine(self.racine, "PCSI/../../secret.txt"))


class TestListerClasses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        (self.racine / "PCSI").mkdir()
        (self.racine / "MPSI").mkdir()
        (self.racine / "note.txt").write_text("ignore-moi")

    def tearDown(self):
        self.tmp.cleanup()

    def test_liste_les_sous_dossiers_tries(self):
        self.assertEqual(cdp_viewer.lister_classes(self.racine), ["MPSI", "PCSI"])

    def test_racine_absente_renvoie_vide(self):
        self.assertEqual(cdp_viewer.lister_classes(self.racine / "nexistepas"), [])


class TestConstruireArbre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        maths = self.racine / "PCSI" / "Maths"
        maths.mkdir(parents=True)
        (maths / "cours.pdf").write_bytes(b"%PDF data")
        (self.racine / "PCSI" / "info.txt").write_text("hello")

    def tearDown(self):
        self.tmp.cleanup()

    def test_structure_de_l_arbre(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        self.assertEqual(arbre["type"], "dossier")
        self.assertEqual(arbre["chemin"], "PCSI")
        noms = sorted(e["nom"] for e in arbre["enfants"])
        self.assertEqual(noms, ["Maths", "info.txt"])

    def test_dossiers_avant_fichiers(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        self.assertEqual(arbre["enfants"][0]["type"], "dossier")

    def test_noeud_fichier(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        dossier = next(e for e in arbre["enfants"] if e["nom"] == "Maths")
        fichier = dossier["enfants"][0]
        self.assertEqual(fichier["type"], "fichier")
        self.assertEqual(fichier["nom"], "cours.pdf")
        self.assertEqual(fichier["chemin"], "PCSI/Maths/cours.pdf")
        self.assertEqual(fichier["ext"], "pdf")
        self.assertEqual(fichier["taille"], len(b"%PDF data"))

    def test_classe_inconnue_renvoie_none(self):
        self.assertIsNone(cdp_viewer.construire_arbre(self.racine, "TERM"))


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.racine = Path(cls.tmp.name)
        maths = cls.racine / "PCSI" / "Maths"
        maths.mkdir(parents=True)
        (maths / "cours.pdf").write_bytes(b"%PDF-1.4 contenu")
        (cls.racine / "secret.txt").write_text("hors classe")

        cls.serveur = cdp_viewer.creer_serveur(cls.racine, port=0)
        cls.port = cls.serveur.server_address[1]
        cls.thread = threading.Thread(target=cls.serveur.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()
        cls.tmp.cleanup()

    def _get(self, chemin):
        url = f"http://127.0.0.1:{self.port}{chemin}"
        return urllib.request.urlopen(url, timeout=5)

    def test_api_classes(self):
        with self._get("/api/classes") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(json.load(r), ["PCSI"])

    def test_api_tree(self):
        with self._get("/api/tree?classe=PCSI") as r:
            arbre = json.load(r)
        self.assertEqual(arbre["chemin"], "PCSI")
        self.assertEqual(arbre["enfants"][0]["nom"], "Maths")

    def test_api_tree_classe_inconnue_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/tree?classe=TERM")
        self.assertEqual(ctx.exception.code, 404)

    def test_file_sert_le_contenu(self):
        with self._get("/file/PCSI/Maths/cours.pdf") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.read(), b"%PDF-1.4 contenu")
            self.assertEqual(r.headers["Content-Type"], "application/pdf")

    def test_file_inexistant_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/file/PCSI/Maths/absent.pdf")
        self.assertEqual(ctx.exception.code, 404)

    def test_file_traversal_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/file/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)

    def test_page_racine_contient_le_squelette(self):
        with self._get("/") as r:
            html = r.read().decode("utf-8")
        self.assertIn("cdp-viewer", html)
        self.assertIn("id=\"arbre\"", html)
        self.assertIn("id=\"apercu\"", html)
        self.assertIn("/api/classes", html)


if __name__ == "__main__":
    unittest.main()
