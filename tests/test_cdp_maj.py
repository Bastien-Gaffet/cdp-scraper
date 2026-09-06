import unittest
from unittest import mock
import sys
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_maj


class TestChargerEnregistrer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / "maj.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_renvoie_dict_vide(self):
        self.assertEqual(cdp_maj.charger(self.chemin), {})

    def test_json_corrompu_repart_a_vide(self):
        self.chemin.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(cdp_maj.charger(self.chemin), {})

    def test_round_trip(self):
        cdp_maj.enregistrer(self.chemin, {"derniere_version_connue": "1.6.0"})
        relu = cdp_maj.charger(self.chemin)
        self.assertEqual(relu["derniere_version_connue"], "1.6.0")

    def test_enregistrer_atomique_pas_de_part_residuel(self):
        cdp_maj.enregistrer(self.chemin, {})
        self.assertEqual(list(self.chemin.parent.glob("*.part")), [])

    def test_enregistrer_cree_le_dossier_parent(self):
        cible = Path(self.tmp.name) / "sous" / "dossier" / "maj.json"
        cdp_maj.enregistrer(cible, {})
        self.assertTrue(cible.is_file())


class TestCheminMaj(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_override_prioritaire(self):
        self.assertEqual(cdp_maj.chemin_maj("ailleurs/x.json"), Path("ailleurs/x.json"))

    def test_local_existant_prioritaire_sur_home(self):
        cwd = self.base / "projet"
        (cwd / cdp_maj.DOSSIER).mkdir(parents=True)
        (cwd / cdp_maj.DOSSIER / cdp_maj.NOM_FICHIER).write_text("{}", encoding="utf-8")
        with mock.patch.object(cdp_maj.Path, "cwd", return_value=cwd), \
             mock.patch.object(cdp_maj.Path, "home", return_value=self.base / "home"):
            p = cdp_maj.chemin_maj()
        self.assertEqual(p, cwd / cdp_maj.DOSSIER / cdp_maj.NOM_FICHIER)

    def test_sans_local_retombe_sur_home(self):
        cwd = self.base / "projet"
        cwd.mkdir(parents=True)
        home = self.base / "home"
        with mock.patch.object(cdp_maj.Path, "cwd", return_value=cwd), \
             mock.patch.object(cdp_maj.Path, "home", return_value=home):
            p = cdp_maj.chemin_maj()
        self.assertEqual(p, home / cdp_maj.DOSSIER / cdp_maj.NOM_FICHIER)


class TestVersionTuple(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(cdp_maj._version_tuple("1.5.0"), (1, 5, 0))

    def test_prefixe_v(self):
        self.assertEqual(cdp_maj._version_tuple("v1.5.0"), (1, 5, 0))

    def test_format_inattendu_renvoie_tuple_vide(self):
        self.assertEqual(cdp_maj._version_tuple("pas-une-version"), ())

    def test_comparaison(self):
        self.assertGreater(cdp_maj._version_tuple("1.6.0"), cdp_maj._version_tuple("1.5.0"))


if __name__ == "__main__":
    unittest.main()
