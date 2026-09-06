import unittest
from unittest import mock
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_coffre


class TestChargerEnregistrer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / "coffre.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_renvoie_coffre_vide(self):
        c = cdp_coffre.charger(self.chemin)
        self.assertEqual(c["version"], cdp_coffre.VERSION)
        self.assertEqual(c["entrees"], {})

    def test_json_corrompu_repart_a_vide(self):
        self.chemin.write_text("{pas du json", encoding="utf-8")
        c = cdp_coffre.charger(self.chemin)
        self.assertEqual(c["entrees"], {})

    def test_version_future_leve(self):
        self.chemin.write_text(
            json.dumps({"version": cdp_coffre.VERSION + 1, "entrees": {}}),
            encoding="utf-8")
        with self.assertRaises(cdp_coffre.CoffreVersionFuture):
            cdp_coffre.charger(self.chemin)

    def test_round_trip(self):
        c = cdp_coffre._vide()
        c["entrees"]["mpsi"] = {"nonce": "aa", "chiffre": "bb"}
        cdp_coffre.enregistrer(self.chemin, c)
        relu = cdp_coffre.charger(self.chemin)
        self.assertEqual(relu["entrees"]["mpsi"]["nonce"], "aa")

    def test_enregistrer_atomique_pas_de_part_residuel(self):
        cdp_coffre.enregistrer(self.chemin, cdp_coffre._vide())
        residus = list(self.chemin.parent.glob("*.part"))
        self.assertEqual(residus, [])

    def test_enregistrer_cree_le_dossier_parent(self):
        cible = Path(self.tmp.name) / "sous" / "dossier" / "coffre.json"
        cdp_coffre.enregistrer(cible, cdp_coffre._vide())
        self.assertTrue(cible.is_file())


class TestCheminCoffre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_override_prioritaire(self):
        p = cdp_coffre.chemin_coffre("ailleurs/x.json")
        self.assertEqual(p, Path("ailleurs/x.json"))

    def test_local_existant_prioritaire_sur_home(self):
        cwd = self.base / "projet"
        (cwd / cdp_coffre.DOSSIER).mkdir(parents=True)
        (cwd / cdp_coffre.DOSSIER / cdp_coffre.NOM_FICHIER).write_text("{}", encoding="utf-8")
        with mock.patch.object(cdp_coffre.Path, "cwd", return_value=cwd), \
             mock.patch.object(cdp_coffre.Path, "home", return_value=self.base / "home"):
            p = cdp_coffre.chemin_coffre()
        self.assertEqual(p, cwd / cdp_coffre.DOSSIER / cdp_coffre.NOM_FICHIER)

    def test_sans_local_retombe_sur_home(self):
        cwd = self.base / "projet"
        cwd.mkdir(parents=True)
        home = self.base / "home"
        with mock.patch.object(cdp_coffre.Path, "cwd", return_value=cwd), \
             mock.patch.object(cdp_coffre.Path, "home", return_value=home):
            p = cdp_coffre.chemin_coffre()
        self.assertEqual(p, home / cdp_coffre.DOSSIER / cdp_coffre.NOM_FICHIER)


class TestEstInitialise(unittest.TestCase):
    def test_coffre_vide_non_initialise(self):
        self.assertFalse(cdp_coffre.est_initialise(cdp_coffre._vide()))

    def test_coffre_avec_kdf_et_temoin_initialise(self):
        c = cdp_coffre._vide()
        c["kdf"] = {}
        c["temoin"] = {}
        self.assertTrue(cdp_coffre.est_initialise(c))


if __name__ == "__main__":
    unittest.main()
