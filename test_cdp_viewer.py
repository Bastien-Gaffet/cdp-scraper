import unittest
from pathlib import Path
import tempfile

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


if __name__ == "__main__":
    unittest.main()
