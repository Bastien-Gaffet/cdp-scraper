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


class TestCreerDeverrouiller(unittest.TestCase):
    def test_creer_est_initialise(self):
        c = cdp_coffre.creer("motmaitre")
        self.assertTrue(cdp_coffre.est_initialise(c))
        self.assertEqual(c["kdf"]["algorithme"], "scrypt")

    def test_deverrouiller_bon_mot_de_passe(self):
        c = cdp_coffre.creer("motmaitre")
        cle = cdp_coffre.deverrouiller(c, "motmaitre")
        self.assertEqual(len(cle), 32)

    def test_deverrouiller_mauvais_mot_de_passe_leve(self):
        c = cdp_coffre.creer("motmaitre")
        with self.assertRaises(cdp_coffre.MotDePasseMaitreIncorrect):
            cdp_coffre.deverrouiller(c, "autrechose")

    def test_deux_coffres_ont_des_sels_differents(self):
        c1 = cdp_coffre.creer("motmaitre")
        c2 = cdp_coffre.creer("motmaitre")
        self.assertNotEqual(c1["kdf"]["sel"], c2["kdf"]["sel"])


class TestAjouterRecuperer(unittest.TestCase):
    def test_round_trip_mot_de_passe(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "secretclasse")
        self.assertEqual(cdp_coffre.recuperer(c, "motmaitre", "mpsi"), "secretclasse")

    def test_ajouter_initialise_le_coffre_au_premier_usage(self):
        c = cdp_coffre._vide()
        self.assertFalse(cdp_coffre.est_initialise(c))
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "secretclasse")
        self.assertTrue(cdp_coffre.est_initialise(c))

    def test_ajouter_deuxieme_classe_meme_coffre(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "secret1")
        cdp_coffre.ajouter(c, "motmaitre", "pcsi", "secret2")
        self.assertEqual(cdp_coffre.recuperer(c, "motmaitre", "mpsi"), "secret1")
        self.assertEqual(cdp_coffre.recuperer(c, "motmaitre", "pcsi"), "secret2")

    def test_ajouter_avec_mauvais_mot_de_passe_maitre_leve(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "secret1")
        with self.assertRaises(cdp_coffre.MotDePasseMaitreIncorrect):
            cdp_coffre.ajouter(c, "autrechose", "pcsi", "secret2")

    def test_recuperer_mauvais_mot_de_passe_maitre_leve(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "secret1")
        with self.assertRaises(cdp_coffre.MotDePasseMaitreIncorrect):
            cdp_coffre.recuperer(c, "autrechose", "mpsi")

    def test_recuperer_classe_absente_leve(self):
        c = cdp_coffre.creer("motmaitre")
        with self.assertRaises(cdp_coffre.ClasseAbsenteDuCoffre):
            cdp_coffre.recuperer(c, "motmaitre", "inconnue")

    def test_remplacer_mot_de_passe_existant(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "ancien")
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "nouveau")
        self.assertEqual(cdp_coffre.recuperer(c, "motmaitre", "mpsi"), "nouveau")

    def test_entrees_chiffrees_ne_sont_pas_en_clair(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "secretclasse")
        # Le JSON sérialisé du coffre ne doit jamais contenir le mot de passe en clair.
        self.assertNotIn("secretclasse", json.dumps(c))


class TestRetirerContientLister(unittest.TestCase):
    def _coffre(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "motmaitre", "mpsi", "s1")
        cdp_coffre.ajouter(c, "motmaitre", "pcsi", "s2")
        return c

    def test_contient(self):
        c = self._coffre()
        self.assertTrue(cdp_coffre.contient(c, "mpsi"))
        self.assertFalse(cdp_coffre.contient(c, "inconnue"))

    def test_contient_coffre_vide(self):
        self.assertFalse(cdp_coffre.contient(cdp_coffre._vide(), "mpsi"))

    def test_lister_ordre_alphabetique(self):
        c = self._coffre()
        self.assertEqual(cdp_coffre.lister(c), ["mpsi", "pcsi"])

    def test_lister_coffre_vide(self):
        self.assertEqual(cdp_coffre.lister(cdp_coffre._vide()), [])

    def test_retirer(self):
        c = self._coffre()
        cdp_coffre.retirer(c, "mpsi")
        self.assertFalse(cdp_coffre.contient(c, "mpsi"))
        self.assertTrue(cdp_coffre.contient(c, "pcsi"))

    def test_retirer_absent_ne_casse_pas(self):
        c = self._coffre()
        cdp_coffre.retirer(c, "inconnue")
        self.assertEqual(len(cdp_coffre.lister(c)), 2)


class TestChangerMdpMaitre(unittest.TestCase):
    def test_ancien_mdp_ne_fonctionne_plus(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "ancien", "mpsi", "secret")
        cdp_coffre.changer_mdp_maitre(c, "ancien", "nouveau")
        with self.assertRaises(cdp_coffre.MotDePasseMaitreIncorrect):
            cdp_coffre.recuperer(c, "ancien", "mpsi")

    def test_nouveau_mdp_fonctionne(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "ancien", "mpsi", "secret")
        cdp_coffre.changer_mdp_maitre(c, "ancien", "nouveau")
        self.assertEqual(cdp_coffre.recuperer(c, "nouveau", "mpsi"), "secret")

    def test_toutes_les_entrees_survivent_au_changement(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "ancien", "mpsi", "s1")
        cdp_coffre.ajouter(c, "ancien", "pcsi", "s2")
        cdp_coffre.changer_mdp_maitre(c, "ancien", "nouveau")
        self.assertEqual(cdp_coffre.recuperer(c, "nouveau", "mpsi"), "s1")
        self.assertEqual(cdp_coffre.recuperer(c, "nouveau", "pcsi"), "s2")

    def test_mauvais_ancien_mdp_leve_et_ne_modifie_rien(self):
        c = cdp_coffre._vide()
        cdp_coffre.ajouter(c, "ancien", "mpsi", "secret")
        sel_avant = c["kdf"]["sel"]
        with self.assertRaises(cdp_coffre.MotDePasseMaitreIncorrect):
            cdp_coffre.changer_mdp_maitre(c, "faux", "nouveau")
        self.assertEqual(c["kdf"]["sel"], sel_avant)
        self.assertEqual(cdp_coffre.recuperer(c, "ancien", "mpsi"), "secret")


if __name__ == "__main__":
    unittest.main()
