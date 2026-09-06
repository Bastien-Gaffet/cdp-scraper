import unittest
from pathlib import Path
import sys
import tempfile
import json
import subprocess
import threading
import urllib.request
import urllib.error
from unittest import mock

# Les tests vivent dans tests/ ; on ajoute la racine du projet au sys.path pour
# pouvoir importer les modules (cdp_viewer, cdp_scraper) quel que soit le dossier
# depuis lequel on lance la suite.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_viewer
import cdp_manifeste


class TestDatesArbre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        (self.racine / "PCSI" / "Phys").mkdir(parents=True)
        (self.racine / "PCSI" / "Phys" / "tp.pdf").write_bytes(b"x")
        (self.racine / "PCSI" / "Phys" / "sans_manif.pdf").write_bytes(b"y")
        (self.racine / "PCSI" / "Phys" / "maj.pdf").write_bytes(b"z")
        man = cdp_manifeste._vide()
        man["documents"]["1"] = {
            "url": "u", "nom": "tp.pdf", "chemin": "Phys", "type": "pdf",
            "empreinte": "", "taille": 1, "statut": "ok",
            "premiere_vue": "2026-06-01T08:00:00",
            "derniere_maj": "2026-06-01T08:00:00", "erreur": None}
        # Document ajouté il y a longtemps mais re-téléchargé récemment.
        man["documents"]["2"] = {
            "url": "u", "nom": "maj.pdf", "chemin": "Phys", "type": "pdf",
            "empreinte": "", "taille": 1, "statut": "ok",
            "premiere_vue": "2026-01-01T08:00:00",
            "derniere_maj": "2026-06-15T08:00:00", "erreur": None}
        cdp_manifeste.enregistrer(self.racine / "PCSI", man)

    def tearDown(self):
        self.tmp.cleanup()

    def _fichier(self, arbre, nom):
        for d in arbre["enfants"]:
            if d["type"] == "dossier":
                t = self._fichier(d, nom)
                if t:
                    return t
            elif d["nom"] == nom:
                return d
        return None

    def test_date_vient_du_manifeste(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        self.assertEqual(self._fichier(arbre, "tp.pdf")["date"], "2026-06-01T08:00:00")

    def test_repli_mtime_si_absent_du_manifeste(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        f = self._fichier(arbre, "sans_manif.pdf")
        self.assertTrue(f["date"])          # une date ISO non vide (mtime)
        self.assertIn("T", f["date"])
        self.assertEqual(f["date_maj"], f["date"])  # repli : maj = ajout = mtime

    def test_date_maj_vient_de_derniere_maj(self):
        # La date affichée reste l'ajout ; date_maj porte la dernière modif
        # (pour que la vue « récemment ajoutés » fasse réapparaître un document
        # re-téléchargé).
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        f = self._fichier(arbre, "maj.pdf")
        self.assertEqual(f["date"], "2026-01-01T08:00:00")
        self.assertEqual(f["date_maj"], "2026-06-15T08:00:00")


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


class TestOuvrirOuReveler(unittest.TestCase):
    @unittest.skipUnless(__import__("sys").platform == "win32", "logique Windows")
    def test_lance_l_app_associee(self):
        with mock.patch.object(cdp_viewer, "_a_une_app_associee_windows", return_value=True), \
             mock.patch("cdp_viewer.os.startfile") as start, \
             mock.patch.object(cdp_viewer, "reveler_dans_explorateur") as rev:
            cdp_viewer.ouvrir_ou_reveler(Path("C:/x/y.docx"))
        start.assert_called_once()
        rev.assert_not_called()

    @unittest.skipUnless(__import__("sys").platform == "win32", "logique Windows")
    def test_revele_si_pas_d_app(self):
        with mock.patch.object(cdp_viewer, "_a_une_app_associee_windows", return_value=False), \
             mock.patch("cdp_viewer.os.startfile") as start, \
             mock.patch.object(cdp_viewer, "reveler_dans_explorateur") as rev:
            cdp_viewer.ouvrir_ou_reveler(Path("C:/x/y.ggb"))
        start.assert_not_called()
        rev.assert_called_once()


class TestLancerPython(unittest.TestCase):
    def test_ouvre_dans_ide_si_disponible(self):
        with mock.patch.object(cdp_viewer, "trouver_ide",
                               return_value=("C:/x/code.exe", "Visual Studio Code")), \
             mock.patch.object(cdp_viewer, "_ouvrir_dans_ide") as ide, \
             mock.patch.object(cdp_viewer, "_ouvrir_terminal_python") as term:
            info = cdp_viewer.lancer_python(Path("C:/x/s.py"))
        self.assertEqual(info, {"methode": "ide", "outil": "Visual Studio Code"})
        ide.assert_called_once()
        term.assert_not_called()

    def test_repli_terminal_sans_ide(self):
        with mock.patch.object(cdp_viewer, "trouver_ide", return_value=None), \
             mock.patch.object(cdp_viewer, "_ouvrir_dans_ide") as ide, \
             mock.patch.object(cdp_viewer, "_ouvrir_terminal_python") as term:
            info = cdp_viewer.lancer_python(Path("C:/x/s.py"))
        self.assertEqual(info["methode"], "terminal")
        term.assert_called_once()
        ide.assert_not_called()

    def test_trouver_ide_renvoie_premier_present(self):
        def faux_which(cmd):
            return "C:/x/subl.exe" if cmd == "subl" else None
        with mock.patch.object(cdp_viewer.shutil, "which", side_effect=faux_which):
            self.assertEqual(cdp_viewer.trouver_ide(), ("C:/x/subl.exe", "Sublime Text"))

    def test_trouver_ide_aucun(self):
        with mock.patch.object(cdp_viewer.shutil, "which", return_value=None):
            self.assertIsNone(cdp_viewer.trouver_ide())


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.racine = Path(cls.tmp.name)
        maths = cls.racine / "PCSI" / "Maths"
        maths.mkdir(parents=True)
        (maths / "cours.pdf").write_bytes(b"%PDF-1.4 contenu")
        (maths / "figure.ggb").write_bytes(b"PK\x03\x04 ggb")
        (maths / "script.py").write_text("import os\nprint('hello')\n")
        (maths / "notes.md").write_text(
            "# Cours\n\nUn **point** important.\n\n- a\n- b\n", encoding="utf-8")
        (maths / "prog.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
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

    def test_reveal_ouvre_ou_revele(self):
        with mock.patch.object(cdp_viewer, "ouvrir_ou_reveler") as m:
            with self._get("/reveal/PCSI/Maths/cours.pdf") as r:
                self.assertEqual(r.status, 204)
        self.assertEqual(m.call_count, 1)
        self.assertEqual(Path(m.call_args[0][0]).name, "cours.pdf")

    def test_reveal_traversal_403(self):
        with mock.patch.object(cdp_viewer, "ouvrir_ou_reveler") as m:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get("/reveal/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)
        m.assert_not_called()

    def test_reveal_inexistant_404(self):
        with mock.patch.object(cdp_viewer, "ouvrir_ou_reveler") as m:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get("/reveal/PCSI/Maths/absent.ggb")
        self.assertEqual(ctx.exception.code, 404)
        m.assert_not_called()

    def test_ouvrir_ggb_sert_la_page_geogebra(self):
        with self._get("/ouvrir/PCSI/Maths/figure.ggb") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers["Content-Type"], "text/html; charset=utf-8")
            html = r.read().decode("utf-8")
        self.assertIn("deployggb.js", html)
        self.assertIn("/file/PCSI/Maths/figure.ggb", html)
        self.assertIn("/reveal/PCSI/Maths/figure.ggb", html)

    def test_code_py_colorise(self):
        with self._get("/code/PCSI/Maths/script.py") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers["Content-Type"], "text/html; charset=utf-8")
            html = r.read().decode("utf-8")
        # script.py = "print('hello')\nimport os\n" : 'import' est un mot-clé.
        self.assertIn('class="kw"', html)
        self.assertIn('class="str"', html)
        self.assertIn("script.py", html)
        # Bouton de lancement + URL /lancer/ pointant vers le script.
        self.assertIn('id="lancer"', html)
        self.assertIn("/lancer/PCSI/Maths/script.py", html)

    def test_rendu_md_html(self):
        with self._get("/rendu/PCSI/Maths/notes.md") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers["Content-Type"], "text/html; charset=utf-8")
            page = r.read().decode("utf-8")
        self.assertIn("<h1>Cours</h1>", page)
        self.assertIn("<strong>point</strong>", page)
        self.assertIn("<li>a</li>", page)
        self.assertIn("/file/PCSI/Maths/notes.md", page)  # lien « voir la source »

    def test_rendu_md_traversal_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/rendu/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)

    def test_rendu_md_inexistant_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/rendu/PCSI/Maths/absent.md")
        self.assertEqual(ctx.exception.code, 404)

    def test_code_c_colore(self):
        with self._get("/code/PCSI/Maths/prog.c") as r:
            self.assertEqual(r.status, 200)
            page = r.read().decode("utf-8")
        self.assertIn('class="kw"', page)
        self.assertNotIn('id="lancer"', page.split("</style>")[0])  # bouton masqué côté JS

    def test_lancer_appelle_lancer_python(self):
        with mock.patch.object(cdp_viewer, "lancer_python",
                               return_value={"methode": "ide", "outil": "Test"}) as m:
            with self._get("/lancer/PCSI/Maths/script.py") as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(json.load(r), {"methode": "ide", "outil": "Test"})
        self.assertEqual(m.call_count, 1)
        self.assertEqual(Path(m.call_args[0][0]).name, "script.py")

    def test_lancer_traversal_403(self):
        with mock.patch.object(cdp_viewer, "lancer_python") as m:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get("/lancer/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)
        m.assert_not_called()

    def test_lancer_inexistant_404(self):
        with mock.patch.object(cdp_viewer, "lancer_python") as m:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get("/lancer/PCSI/Maths/absent.py")
        self.assertEqual(ctx.exception.code, 404)
        m.assert_not_called()

    def test_ouvrir_traversal_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/ouvrir/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)

    def test_code_traversal_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/code/../secret.txt")
        self.assertEqual(ctx.exception.code, 403)

    def test_ouvrir_inexistant_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/ouvrir/PCSI/Maths/absent.ggb")
        self.assertEqual(ctx.exception.code, 404)

    def test_page_racine_contient_le_squelette(self):
        with self._get("/") as r:
            html = r.read().decode("utf-8")
        self.assertIn("cdp-viewer", html)
        self.assertIn("id=\"rubriques\"", html)
        self.assertIn("id=\"explorateur\"", html)
        self.assertIn("/api/classes", html)

    def test_erreur_404_html_contextuel(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/file/PCSI/Maths/absent.pdf")
        e = ctx.exception
        self.assertEqual(e.code, 404)
        self.assertIn("text/html", e.headers["Content-Type"])
        self.assertIn("Fichier introuvable", e.read().decode("utf-8"))

    def test_erreur_403_html_contextuel(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/file/../secret.txt")
        e = ctx.exception
        self.assertEqual(e.code, 403)
        self.assertIn("Accès refusé", e.read().decode("utf-8"))


class TestExclusionDotfiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        (self.racine / "PCSI").mkdir()
        (self.racine / "PCSI" / "cours.pdf").write_bytes(b"x")
        (self.racine / "PCSI" / ".cdp-manifest.json").write_text("{}")
        (self.racine / ".cache").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_classes_ignorent_les_dotdirs(self):
        self.assertEqual(cdp_viewer.lister_classes(self.racine), ["PCSI"])

    def test_arbre_ignore_le_manifeste(self):
        arbre = cdp_viewer.construire_arbre(self.racine, "PCSI")
        noms = [e["nom"] for e in arbre["enfants"]]
        self.assertIn("cours.pdf", noms)
        self.assertNotIn(".cdp-manifest.json", noms)


class TestVersionCLI(unittest.TestCase):
    """`cdp_viewer.py --version` affiche la version et quitte proprement."""

    def test_version_cli(self):
        racine_projet = Path(__file__).resolve().parent.parent
        script = racine_projet / "cdp_viewer.py"
        res = subprocess.run(
            [sys.executable, str(script), "--version"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(res.returncode, 0)
        # argparse action="version" écrit sur stdout (3.4+) ; on couvre les deux flux.
        self.assertIn("cdp-viewer 1.6.0", res.stdout + res.stderr)


class TestPageErreur(unittest.TestCase):
    def test_contient_code_titre_message(self):
        page = cdp_viewer.page_erreur(404, "fichier")
        texte = page.decode("utf-8")
        self.assertIn("404", texte)
        self.assertIn("Fichier introuvable", texte)
        self.assertIn("Retour à l'accueil", texte)

    def test_contexte_classe(self):
        self.assertIn("Classe introuvable",
                      cdp_viewer.page_erreur(404, "classe").decode("utf-8"))

    def test_contexte_inconnu_repli(self):
        self.assertIn("Erreur", cdp_viewer.page_erreur(418, "zzz").decode("utf-8"))


class TestRechercheAmelioree(unittest.TestCase):
    def test_helpers_recherche_presents(self):
        self.assertIn('normalize("NFD")', cdp_viewer.PAGE_HTML)
        self.assertIn("function sansAccents", cdp_viewer.PAGE_HTML)
        self.assertIn("function dossierParent", cdp_viewer.PAGE_HTML)
        self.assertIn('className = "chemin"', cdp_viewer.PAGE_HTML)


class TestNavigationClavier(unittest.TestCase):
    def test_handler_et_helpers_presents(self):
        p = cdp_viewer.PAGE_HTML
        self.assertIn('addEventListener("keydown"', p)
        self.assertIn("function surligner", p)
        self.assertIn("function remonter", p)
        self.assertIn("function classeSuivante", p)
        self.assertIn("scrollIntoView", p)
        self.assertIn(".ligne.actif", p)


class TestVerifMajViewer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    class _FauxServeur:
        server_address = ("127.0.0.1", 0)

        def serve_forever(self):
            raise KeyboardInterrupt()

        def shutdown(self):
            pass

        def server_close(self):
            pass

    def _run(self, argv):
        argv = ["cdp_viewer.py", "--dossier", str(self.dossier), "--no-browser"] + argv
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(cdp_viewer, "creer_serveur", return_value=self._FauxServeur()), \
             mock.patch.object(cdp_viewer.cdp_maj, "proposer_maj") as proposer_mock:
            cdp_viewer.main()
        return proposer_mock

    def test_appelee_par_defaut(self):
        proposer_mock = self._run([])
        proposer_mock.assert_called_once()
        self.assertEqual(proposer_mock.call_args[0][0], cdp_viewer.__version__)

    def test_no_verif_maj_desactive(self):
        proposer_mock = self._run(["--no-verif-maj"])
        proposer_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
