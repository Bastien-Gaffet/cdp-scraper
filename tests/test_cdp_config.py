import unittest
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_config


class TestChargerEnregistrer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_renvoie_config_vide(self):
        c = cdp_config.charger(self.chemin)
        self.assertEqual(c["version"], cdp_config.VERSION)
        self.assertEqual(c["classes"], [])

    def test_round_trip(self):
        c = cdp_config._vide()
        c["classes"].append({"nom": "mpsi", "url": "u", "login": "l", "dossier": "d"})
        cdp_config.enregistrer(self.chemin, c)
        relu = cdp_config.charger(self.chemin)
        self.assertEqual(relu["classes"][0]["nom"], "mpsi")

    def test_json_corrompu_repart_a_vide(self):
        self.chemin.write_text("{pas du json", encoding="utf-8")
        c = cdp_config.charger(self.chemin)
        self.assertEqual(c["classes"], [])

    def test_version_future_leve(self):
        self.chemin.write_text(
            json.dumps({"version": cdp_config.VERSION + 1, "classes": []}),
            encoding="utf-8")
        with self.assertRaises(cdp_config.ConfigVersionFuture):
            cdp_config.charger(self.chemin)

    def test_enregistrer_atomique_pas_de_part_residuel(self):
        cdp_config.enregistrer(self.chemin, cdp_config._vide())
        residus = list(self.chemin.parent.glob("*.part"))
        self.assertEqual(residus, [])

    def test_enregistrer_cree_le_dossier_parent(self):
        cible = Path(self.tmp.name) / "sous" / "dossier" / "config.json"
        cdp_config.enregistrer(cible, cdp_config._vide())
        self.assertTrue(cible.is_file())


class TestMutations(unittest.TestCase):
    def _config(self):
        c = cdp_config._vide()
        c["classes"].append({"nom": "mpsi", "url": "u1", "login": "l1", "dossier": "d"})
        return c

    def test_ajouter_nouvelle(self):
        c = cdp_config._vide()
        cdp_config.ajouter_ou_maj(c, {"nom": "pcsi", "url": "u", "login": "l", "dossier": "d"})
        self.assertEqual([x["nom"] for x in c["classes"]], ["pcsi"])

    def test_maj_existante_remplace_sans_doublon(self):
        c = self._config()
        cdp_config.ajouter_ou_maj(c, {"nom": "mpsi", "url": "u2", "login": "l2", "dossier": "d2"})
        self.assertEqual(len(c["classes"]), 1)
        self.assertEqual(c["classes"][0]["url"], "u2")

    def test_lister(self):
        c = self._config()
        self.assertEqual(len(cdp_config.lister(c)), 1)

    def test_retirer(self):
        c = self._config()
        cdp_config.retirer(c, "mpsi")
        self.assertEqual(c["classes"], [])

    def test_retirer_absent_ne_casse_pas(self):
        c = self._config()
        cdp_config.retirer(c, "inconnue")
        self.assertEqual(len(c["classes"]), 1)

    def test_contient(self):
        c = self._config()
        self.assertTrue(cdp_config.contient(c, "mpsi"))
        self.assertFalse(cdp_config.contient(c, "pcsi"))


class TestSelectionner(unittest.TestCase):
    def _config(self):
        c = cdp_config._vide()
        for n in ("mpsi", "pcsi"):
            c["classes"].append({"nom": n, "url": "u", "login": "l", "dossier": "d"})
        return c

    def test_selection_ordre_des_noms(self):
        c = self._config()
        choisies = cdp_config.selectionner(c, ["pcsi", "mpsi"])
        self.assertEqual([x["nom"] for x in choisies], ["pcsi", "mpsi"])

    def test_nom_inconnu_leve(self):
        c = self._config()
        with self.assertRaises(cdp_config.ClasseInconnue):
            cdp_config.selectionner(c, ["mpsi", "terminale"])


if __name__ == "__main__":
    unittest.main()
