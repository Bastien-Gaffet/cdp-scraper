import unittest
from unittest import mock
import sys
import json
import subprocess
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


class _FausseReponse:
    """Contexte minimal imitant l'objet renvoyé par urllib.request.urlopen."""

    def __init__(self, contenu: bytes):
        self._contenu = contenu

    def read(self):
        return self._contenu

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class TestDerniereVersionGithub(unittest.TestCase):
    def test_succes(self):
        corps = json.dumps({"tag_name": "v1.6.0"}).encode("utf-8")
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               return_value=_FausseReponse(corps)):
            self.assertEqual(cdp_maj.derniere_version_github("owner/repo"), "1.6.0")

    def test_timeout(self):
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               side_effect=TimeoutError()):
            self.assertIsNone(cdp_maj.derniere_version_github("owner/repo"))

    def test_erreur_url(self):
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               side_effect=cdp_maj.urllib.error.URLError("boom")):
            self.assertIsNone(cdp_maj.derniere_version_github("owner/repo"))

    def test_json_invalide(self):
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               return_value=_FausseReponse(b"pas du json")):
            self.assertIsNone(cdp_maj.derniere_version_github("owner/repo"))

    def test_cle_tag_name_absente(self):
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               return_value=_FausseReponse(b"{}")):
            self.assertIsNone(cdp_maj.derniere_version_github("owner/repo"))


class TestVerifierMaj(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / "maj.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_cache_absent_appelle_et_ecrit(self):
        with mock.patch.object(cdp_maj, "derniere_version_github", return_value="1.6.0"):
            resultat = cdp_maj.verifier_maj("1.5.0", self.chemin, "owner/repo")
        self.assertEqual(resultat, "1.6.0")
        cache = cdp_maj.charger(self.chemin)
        self.assertEqual(cache["derniere_version_connue"], "1.6.0")
        self.assertIn("derniere_verif", cache)

    def test_version_egale_renvoie_none(self):
        with mock.patch.object(cdp_maj, "derniere_version_github", return_value="1.5.0"):
            resultat = cdp_maj.verifier_maj("1.5.0", self.chemin, "owner/repo")
        self.assertIsNone(resultat)

    def test_version_distante_inferieure_renvoie_none(self):
        with mock.patch.object(cdp_maj, "derniere_version_github", return_value="1.4.0"):
            resultat = cdp_maj.verifier_maj("1.5.0", self.chemin, "owner/repo")
        self.assertIsNone(resultat)

    def test_cache_recent_pas_de_rappel_reseau(self):
        cdp_maj.enregistrer(self.chemin, {
            "derniere_verif": datetime.now().isoformat(timespec="seconds"),
            "derniere_version_connue": "1.6.0",
        })
        with mock.patch.object(cdp_maj, "derniere_version_github") as mock_gh:
            resultat = cdp_maj.verifier_maj("1.5.0", self.chemin, "owner/repo")
        mock_gh.assert_not_called()
        self.assertEqual(resultat, "1.6.0")

    def test_cache_ancien_rappelle(self):
        ancien = datetime.now() - timedelta(hours=25)
        cdp_maj.enregistrer(self.chemin, {
            "derniere_verif": ancien.isoformat(timespec="seconds"),
            "derniere_version_connue": "1.5.0",
        })
        with mock.patch.object(cdp_maj, "derniere_version_github",
                               return_value="1.6.0") as mock_gh:
            resultat = cdp_maj.verifier_maj("1.5.0", self.chemin, "owner/repo")
        mock_gh.assert_called_once()
        self.assertEqual(resultat, "1.6.0")

    def test_echec_reseau_garde_ancienne_version_et_maj_horodatage(self):
        ancien = datetime.now() - timedelta(hours=25)
        ancien_iso = ancien.isoformat(timespec="seconds")
        cdp_maj.enregistrer(self.chemin, {
            "derniere_verif": ancien_iso,
            "derniere_version_connue": "1.6.0",
        })
        with mock.patch.object(cdp_maj, "derniere_version_github", return_value=None):
            resultat = cdp_maj.verifier_maj("1.5.0", self.chemin, "owner/repo")
        self.assertEqual(resultat, "1.6.0")
        cache = cdp_maj.charger(self.chemin)
        self.assertNotEqual(cache["derniere_verif"], ancien_iso)


class TestEstDepotGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_avec_git(self):
        (self.dossier / ".git").mkdir()
        self.assertTrue(cdp_maj.est_depot_git(self.dossier))

    def test_sans_git(self):
        self.assertFalse(cdp_maj.est_depot_git(self.dossier))


class TestGitPull(unittest.TestCase):
    def test_succes(self):
        resultat = subprocess.CompletedProcess(
            args=["git", "pull"], returncode=0, stdout="Already up to date.\n", stderr="")
        with mock.patch.object(cdp_maj.subprocess, "run", return_value=resultat):
            ok, message = cdp_maj.git_pull(Path("."))
        self.assertTrue(ok)
        self.assertIn("Already up to date", message)

    def test_code_retour_non_nul(self):
        resultat = subprocess.CompletedProcess(
            args=["git", "pull"], returncode=1, stdout="", stderr="conflit local")
        with mock.patch.object(cdp_maj.subprocess, "run", return_value=resultat):
            ok, message = cdp_maj.git_pull(Path("."))
        self.assertFalse(ok)
        self.assertIn("conflit local", message)

    def test_git_absent_du_path(self):
        with mock.patch.object(cdp_maj.subprocess, "run",
                               side_effect=FileNotFoundError("git introuvable")):
            ok, message = cdp_maj.git_pull(Path("."))
        self.assertFalse(ok)

    def test_timeout(self):
        with mock.patch.object(cdp_maj.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="git pull", timeout=30)):
            ok, message = cdp_maj.git_pull(Path("."))
        self.assertFalse(ok)


class TestListerFichiersMaj(unittest.TestCase):
    CONTENU_API = [
        {"name": "cdp_scraper.py", "type": "file", "download_url": "https://raw/cdp_scraper.py"},
        {"name": "tests", "type": "dir", "download_url": None},
        {"name": ".github", "type": "dir", "download_url": None},
        {"name": "image.png", "type": "file", "download_url": "https://raw/image.png"},
        {"name": "README.md", "type": "file", "download_url": "https://raw/README.md"},
        {"name": "requirements.txt", "type": "file", "download_url": "https://raw/requirements.txt"},
    ]

    def test_filtre_les_fichiers_pertinents(self):
        corps = json.dumps(self.CONTENU_API).encode("utf-8")
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               return_value=_FausseReponse(corps)):
            fichiers = cdp_maj.lister_fichiers_maj("owner/repo", "v1.6.0")
        noms = {f["nom"] for f in fichiers}
        self.assertEqual(noms, {"cdp_scraper.py", "README.md", "requirements.txt"})

    def test_erreur_reseau_renvoie_none(self):
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               side_effect=TimeoutError()):
            self.assertIsNone(cdp_maj.lister_fichiers_maj("owner/repo", "v1.6.0"))

    def test_json_invalide_renvoie_none(self):
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               return_value=_FausseReponse(b"pas du json")):
            self.assertIsNone(cdp_maj.lister_fichiers_maj("owner/repo", "v1.6.0"))


class TestTelechargerFichiers(unittest.TestCase):
    def test_tous_reussissent(self):
        fichiers = [{"nom": "a.py", "download_url": "https://raw.example/a.py"},
                   {"nom": "b.py", "download_url": "https://raw.example/b.py"}]
        reponses = [_FausseReponse(b"contenu-a"), _FausseReponse(b"contenu-b")]
        with mock.patch.object(cdp_maj.urllib.request, "urlopen", side_effect=reponses):
            resultat = cdp_maj.telecharger_fichiers(fichiers)
        self.assertEqual(resultat, {"a.py": b"contenu-a", "b.py": b"contenu-b"})

    def test_un_seul_echec_annule_tout(self):
        fichiers = [{"nom": "a.py", "download_url": "https://raw.example/a.py"},
                   {"nom": "b.py", "download_url": "https://raw.example/b.py"}]
        with mock.patch.object(cdp_maj.urllib.request, "urlopen",
                               side_effect=[_FausseReponse(b"contenu-a"), TimeoutError()]):
            resultat = cdp_maj.telecharger_fichiers(fichiers)
        self.assertIsNone(resultat)


class TestAppliquerMaj(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ecrit_les_fichiers(self):
        cdp_maj.appliquer_maj(self.dossier, {"a.py": b"contenu-a", "README.md": b"contenu-b"})
        self.assertEqual((self.dossier / "a.py").read_bytes(), b"contenu-a")
        self.assertEqual((self.dossier / "README.md").read_bytes(), b"contenu-b")

    def test_pas_de_part_residuel(self):
        cdp_maj.appliquer_maj(self.dossier, {"a.py": b"x"})
        self.assertEqual(list(self.dossier.glob("*.part")), [])

    def test_rejette_les_noms_avec_separateur_de_chemin(self):
        cdp_maj.appliquer_maj(self.dossier, {"../evil.py": b"x", "sub/evil.py": b"y",
                                             "bon.py": b"z"})
        self.assertFalse((self.dossier.parent / "evil.py").exists())
        self.assertFalse((self.dossier / "sub").exists())
        self.assertTrue((self.dossier / "bon.py").exists())


class TestProposerMaj(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin_cache = Path(self.tmp.name) / "maj.json"
        self.dossier_projet = Path(self.tmp.name) / "projet"
        self.dossier_projet.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _appel(self, **kw):
        defaut = dict(version_locale="1.5.0", chemin_cache=self.chemin_cache,
                     depot="owner/repo", dossier_projet=self.dossier_projet, tty=lambda: True)
        defaut.update(kw)
        cdp_maj.proposer_maj(**defaut)

    def test_a_jour_aucune_question(self):
        with mock.patch.object(cdp_maj, "verifier_maj", return_value=None), \
             mock.patch("builtins.input") as input_mock:
            self._appel()
        input_mock.assert_not_called()

    def test_hors_tty_notice_sans_question(self):
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input") as input_mock:
            self._appel(tty=lambda: False)
        input_mock.assert_not_called()

    def test_refus_utilisateur_ne_fait_rien(self):
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input", return_value="n"), \
             mock.patch.object(cdp_maj, "est_depot_git") as git_mock:
            self._appel()
        git_mock.assert_not_called()

    def test_depot_git_confirme_appelle_git_pull_pas_la_liste_zip(self):
        (self.dossier_projet / ".git").mkdir()
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input", return_value="o"), \
             mock.patch.object(cdp_maj, "git_pull", return_value=(True, "ok")) as pull_mock, \
             mock.patch.object(cdp_maj, "lister_fichiers_maj") as lister_mock:
            self._appel()
        pull_mock.assert_called_once()
        lister_mock.assert_not_called()

    def test_refus_confirmation_git_pull_specifique(self):
        (self.dossier_projet / ".git").mkdir()
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input", side_effect=["o", "n"]), \
             mock.patch.object(cdp_maj, "git_pull") as pull_mock:
            self._appel()
        pull_mock.assert_not_called()

    def test_zip_confirme_va_jusqu_a_appliquer(self):
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input", return_value="o"), \
             mock.patch.object(cdp_maj, "lister_fichiers_maj",
                               return_value=[{"nom": "a.py", "download_url": "u"}]) as lister_mock, \
             mock.patch.object(cdp_maj, "telecharger_fichiers",
                               return_value={"a.py": b"x"}) as dl_mock, \
             mock.patch.object(cdp_maj, "appliquer_maj") as appliquer_mock:
            self._appel()
        lister_mock.assert_called_once()
        dl_mock.assert_called_once()
        appliquer_mock.assert_called_once_with(self.dossier_projet, {"a.py": b"x"})

    def test_echec_liste_fichiers_n_ecrit_rien(self):
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input", return_value="o"), \
             mock.patch.object(cdp_maj, "lister_fichiers_maj", return_value=None), \
             mock.patch.object(cdp_maj, "telecharger_fichiers") as dl_mock, \
             mock.patch.object(cdp_maj, "appliquer_maj") as appliquer_mock:
            self._appel()
        dl_mock.assert_not_called()
        appliquer_mock.assert_not_called()

    def test_echec_telechargement_n_applique_rien(self):
        with mock.patch.object(cdp_maj, "verifier_maj", return_value="1.6.0"), \
             mock.patch("builtins.input", return_value="o"), \
             mock.patch.object(cdp_maj, "lister_fichiers_maj",
                               return_value=[{"nom": "a.py", "download_url": "u"}]), \
             mock.patch.object(cdp_maj, "telecharger_fichiers", return_value=None), \
             mock.patch.object(cdp_maj, "appliquer_maj") as appliquer_mock:
            self._appel()
        appliquer_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
