import unittest
import sys
import os
import tempfile
from unittest import mock
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
        self.assertEqual(cdp_scraper.__version__, "1.4.0")


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

    def test_empreinte_conserve_docdonnees(self):
        page = (
            '<section>'
            '<p class="doc"><span class="docdonnees">(pdf, 1 jan, 100 ko)</span> '
            '<a href="download?id=42&amp;v=abcde">'
            '<span class="icone"></span><span class="nom">Cours 1</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(docs[0]["empreinte"], "pdf, 1 jan, 100 ko")

    def test_empreinte_vide_si_pas_de_docdonnees(self):
        page = (
            '<section>'
            '<p class="doc">'
            '<a href="download?id=7&amp;v=x">'
            '<span class="nom">Sans donnees</span></a></p>'
            '</section>'
        )
        _, docs = cdp_scraper.analyser_page(page, self.URL)
        self.assertEqual(docs[0]["empreinte"], "")


class _RespTelecharge:
    """Réponse de téléchargement minimale pour telecharger (stream=True)."""

    def __init__(self, contenu: bytes, headers=None):
        self._contenu = contenu
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=65536):
        yield self._contenu

    def close(self):
        pass


class _SessionTelecharge:
    def __init__(self, contenu: bytes, headers=None):
        self._resp = _RespTelecharge(contenu, headers)

    def get(self, url, timeout=None, stream=False):
        return self._resp


class TestTelechargerAtomique(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ecrit_le_fichier_et_renvoie_nom(self):
        sess = _SessionTelecharge(b"PDFDATA")
        doc = {"url": "https://x/download?id=1&dl", "id": "1",
               "nom": "cours.pdf", "type": "pdf", "chemin": "Phys"}
        statut, taille, nom = cdp_scraper.telecharger(sess, doc, self.base, False, 1, 1)
        self.assertEqual(statut, "ok")
        self.assertEqual(taille, 7)
        self.assertEqual((self.base / "Phys" / nom).read_bytes(), b"PDFDATA")

    def test_ecrase_un_fichier_existant(self):
        (self.base / "Phys").mkdir(parents=True)
        (self.base / "Phys" / "cours.pdf").write_bytes(b"VIEUX")
        sess = _SessionTelecharge(b"NOUVEAU")
        doc = {"url": "https://x/download?id=1&dl", "id": "1",
               "nom": "cours.pdf", "type": "pdf", "chemin": "Phys"}
        statut, _, nom = cdp_scraper.telecharger(sess, doc, self.base, False, 1, 1)
        self.assertEqual(statut, "ok")
        self.assertEqual((self.base / "Phys" / "cours.pdf").read_bytes(), b"NOUVEAU")

    def test_pas_de_part_residuel_apres_succes(self):
        sess = _SessionTelecharge(b"DATA")
        doc = {"url": "https://x/download?id=1&dl", "id": "1",
               "nom": "cours.pdf", "type": "pdf", "chemin": ""}
        cdp_scraper.telecharger(sess, doc, self.base, False, 1, 1)
        self.assertEqual(list(self.base.glob("*.part")), [])

    def test_contenu_genere_ecrit_html(self):
        doc = {"id": "pc_x", "nom": "Programme.html", "chemin": "Maths",
               "contenu_html": "<p>colles</p>"}
        statut, _, nom = cdp_scraper.telecharger(None, doc, self.base, False, 1, 1)
        self.assertEqual(statut, "ok")
        self.assertEqual(nom, "Programme.html")
        self.assertTrue((self.base / "Maths" / "Programme.html").is_file())

    def test_coupure_en_flux_echec_sans_fichier_ni_part(self):
        # Une coupure réseau en plein téléchargement ne doit laisser ni fichier
        # cible (tronqué) ni .part résiduel : statut "echec", rien sur le disque.
        class _RespCoupe:
            headers = {}

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size=65536):
                yield b"debut"
                raise cdp_scraper.requests.ConnectionError("coupure")

            def close(self):
                pass

        class _SessionCoupe:
            def get(self, url, timeout=None, stream=False):
                return _RespCoupe()

        doc = {"url": "https://x/download?id=1&dl", "id": "1",
               "nom": "cours.pdf", "type": "pdf", "chemin": "Phys"}
        statut, taille, _ = cdp_scraper.telecharger(_SessionCoupe(), doc, self.base, False, 1, 1)
        self.assertEqual(statut, "echec")
        self.assertEqual(taille, 0)
        self.assertFalse((self.base / "Phys" / "cours.pdf").exists())
        self.assertEqual(list((self.base / "Phys").glob("*.part")), [])


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


class TestDrapeauxSynchro(unittest.TestCase):
    def test_complet_et_reprise_exclusifs(self):
        with mock.patch.object(sys, "argv",
                               ["cdp_scraper.py", "--complet", "--reprise"]):
            with self.assertRaises(SystemExit):
                cdp_scraper.parse_args()

    def test_complet_seul_ok(self):
        with mock.patch.object(sys, "argv", ["cdp_scraper.py", "--complet"]):
            args = cdp_scraper.parse_args()
        self.assertTrue(args.complet)
        self.assertFalse(args.reprise)

    def test_reprise_seul_ok(self):
        with mock.patch.object(sys, "argv", ["cdp_scraper.py", "--reprise"]):
            args = cdp_scraper.parse_args()
        self.assertTrue(args.reprise)
        self.assertFalse(args.complet)


class TestArgsConfig(unittest.TestCase):
    def test_noms_positionnels(self):
        args = cdp_scraper.parse_args(["mpsi", "pcsi"])
        self.assertEqual(args.noms, ["mpsi", "pcsi"])

    def test_aucun_nom_liste_vide(self):
        args = cdp_scraper.parse_args([])
        self.assertEqual(args.noms, [])

    def test_flags_config(self):
        args = cdp_scraper.parse_args(["--config", "x.json", "--tout"])
        self.assertEqual(args.config, "x.json")
        self.assertTrue(args.tout)

    def test_config_lister_et_supprimer(self):
        args = cdp_scraper.parse_args(["--config-lister"])
        self.assertTrue(args.config_lister)
        args = cdp_scraper.parse_args(["--config-supprimer", "mpsi"])
        self.assertEqual(args.config_supprimer, "mpsi")


class TestIndicesMenu(unittest.TestCase):
    def test_vide_tous(self):
        self.assertEqual(cdp_scraper._indices_menu("", 3), [0, 1, 2])

    def test_tout_tous(self):
        self.assertEqual(cdp_scraper._indices_menu("tout", 3), [0, 1, 2])

    def test_liste(self):
        self.assertEqual(cdp_scraper._indices_menu("1,3", 3), [0, 2])

    def test_espaces_et_doublons_ignores(self):
        self.assertEqual(cdp_scraper._indices_menu("2, 2 , 1", 3), [1, 0])

    def test_hors_plage_et_non_numerique_ignores(self):
        self.assertEqual(cdp_scraper._indices_menu("0,4,a,2", 3), [1])


import types

class TestTraiterClasse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self):
        return types.SimpleNamespace(reprise=False, complet=False, sans_colles=True,
                                     profondeur=None, delai=0.0)

    def test_connexion_echouee_resume_ko(self):
        cfg = {"nom": "mpsi", "url": "https://x/mpsi", "login": "a", "dossier": self.dossier}
        with mock.patch.object(cdp_scraper, "creer_session", return_value=object()), \
             mock.patch.object(cdp_scraper, "connexion", return_value=(False, "401")):
            resume = cdp_scraper.traiter_classe(cfg, self._args(), "secret", True)
        self.assertFalse(resume["ok"])
        self.assertEqual(resume["nom"], "mpsi")

    def test_simulation_compte_les_documents(self):
        cfg = {"nom": "mpsi", "url": "https://x/mpsi", "login": "a", "dossier": self.dossier}
        doc = {"id": "1", "nom": "a.pdf", "url": "u", "chemin": "", "type": "pdf"}
        with mock.patch.object(cdp_scraper, "creer_session", return_value=object()), \
             mock.patch.object(cdp_scraper, "connexion", return_value=(True, "ok")), \
             mock.patch.object(cdp_scraper, "crawler", return_value=[doc]), \
             mock.patch.object(cdp_scraper, "telecharger",
                               return_value=("simulation", 10, "a.pdf")) as tele:
            resume = cdp_scraper.traiter_classe(cfg, self._args(), "secret", True)
        self.assertTrue(resume["ok"])
        self.assertEqual(resume["compteur"]["simulation"], 1)
        tele.assert_called_once()
        self.assertEqual(list(Path(self.dossier).glob("**/.cdp-manifest.json")), [])

    def test_manifeste_version_future_resume_ko_sans_exit(self):
        cfg = {"nom": "mpsi", "url": "https://x/mpsi", "login": "a", "dossier": self.dossier}
        doc = {"id": "1", "nom": "a.pdf", "url": "u", "chemin": "", "type": "pdf"}
        with mock.patch.object(cdp_scraper, "creer_session", return_value=object()), \
             mock.patch.object(cdp_scraper, "connexion", return_value=(True, "ok")), \
             mock.patch.object(cdp_scraper, "crawler", return_value=[doc]), \
             mock.patch.object(cdp_scraper.cdp_manifeste, "charger",
                               side_effect=cdp_scraper.cdp_manifeste.ManifesteVersionFuture("trop récent")):
            resume = cdp_scraper.traiter_classe(cfg, self._args(), "secret", True)
        self.assertFalse(resume["ok"])
        self.assertEqual(resume["nom"], "mpsi")


class TestMainSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / "config.json"
        import cdp_config
        c = cdp_config._vide()
        for n in ("mpsi", "pcsi"):
            c["classes"].append({"nom": n, "url": f"https://x/{n}",
                                 "login": "l", "dossier": "cours_cdp"})
        cdp_config.enregistrer(self.chemin, c)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv, traites):
        def faux_traiter(cfg, args, mdp, simulation):
            traites.append(cfg["nom"])
            return {"nom": cfg["nom"], "ok": True, "compteur": {"ok": 1, "echec": 0}, "volume": {}}
        with mock.patch.object(cdp_scraper, "parse_args",
                               return_value=cdp_scraper.parse_args(argv)), \
             mock.patch.object(cdp_scraper, "verifier_accord"), \
             mock.patch.object(cdp_scraper.cdp_config, "chemin_config",
                               return_value=self.chemin), \
             mock.patch.object(cdp_scraper, "demander", return_value="motdepasse"), \
             mock.patch.object(cdp_scraper, "traiter_classe", side_effect=faux_traiter):
            cdp_scraper.main()

    def test_noms_filtrent(self):
        traites = []
        self._run(["pcsi"], traites)
        self.assertEqual(traites, ["pcsi"])

    def test_tout_traite_toutes(self):
        traites = []
        self._run(["--tout"], traites)
        self.assertEqual(sorted(traites), ["mpsi", "pcsi"])


if __name__ == "__main__":
    unittest.main()
