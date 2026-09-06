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
import cdp_config
import cdp_coffre

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


class TestArgsCoffre(unittest.TestCase):
    def test_coffre_chemin(self):
        args = cdp_scraper.parse_args(["--coffre", "x.json"])
        self.assertEqual(args.coffre, "x.json")

    def test_coffre_defaut_none(self):
        args = cdp_scraper.parse_args([])
        self.assertIsNone(args.coffre)

    def test_coffre_ajouter(self):
        args = cdp_scraper.parse_args(["--coffre-ajouter", "mpsi"])
        self.assertEqual(args.coffre_ajouter, "mpsi")

    def test_coffre_supprimer(self):
        args = cdp_scraper.parse_args(["--coffre-supprimer", "mpsi"])
        self.assertEqual(args.coffre_supprimer, "mpsi")

    def test_coffre_lister(self):
        args = cdp_scraper.parse_args(["--coffre-lister"])
        self.assertTrue(args.coffre_lister)

    def test_coffre_changer_mdp(self):
        args = cdp_scraper.parse_args(["--coffre-changer-mdp"])
        self.assertTrue(args.coffre_changer_mdp)


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
        self.chemin_coffre = Path(self.tmp.name) / "coffre.json"
        c = cdp_config._vide()
        for n in ("mpsi", "pcsi"):
            c["classes"].append({"nom": n, "url": f"https://x/{n}",
                                 "login": "l", "dossier": "cours_cdp"})
        cdp_config.enregistrer(self.chemin, c)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv, traites, entrees_input=(), demander_side_effect=None):
        def faux_traiter(cfg, args, mdp, simulation):
            traites.append((cfg["nom"], mdp))
            return {"nom": cfg["nom"], "ok": True, "compteur": {"ok": 1, "echec": 0}, "volume": {}}
        argv = list(argv) + ["--coffre", str(self.chemin_coffre)]
        demander_kwargs = ({"side_effect": demander_side_effect} if demander_side_effect is not None
                           else {"return_value": "motdepasse"})
        with mock.patch.object(cdp_scraper, "parse_args",
                               return_value=cdp_scraper.parse_args(argv)), \
             mock.patch.object(cdp_scraper, "verifier_accord"), \
             mock.patch.object(cdp_scraper.cdp_config, "chemin_config",
                               return_value=self.chemin), \
             mock.patch.object(cdp_scraper, "demander", **demander_kwargs), \
             mock.patch.object(cdp_scraper, "_tty", return_value=False), \
             mock.patch.object(cdp_scraper, "traiter_classe", side_effect=faux_traiter), \
             mock.patch("builtins.input", side_effect=list(entrees_input)):
            cdp_scraper.main()

    def test_noms_filtrent(self):
        traites = []
        self._run(["pcsi"], traites)
        self.assertEqual([n for n, _ in traites], ["pcsi"])

    def test_tout_traite_toutes(self):
        traites = []
        self._run(["--tout"], traites)
        self.assertEqual(sorted(n for n, _ in traites), ["mpsi", "pcsi"])

    def test_aucune_classe_en_coffre_saisie_manuelle(self):
        traites = []
        self._run(["--tout"], traites)
        self.assertTrue(all(mdp == "motdepasse" for _, mdp in traites))

    def test_classe_en_coffre_deverrouillee_sans_ressaisie(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "motmaitre", "mpsi", "secretmpsi")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        traites = []
        self._run(["--tout"], traites, entrees_input=["o"],
                  demander_side_effect=["motmaitre", "motdepasse"])
        mdp_par_classe = dict(traites)
        self.assertEqual(mdp_par_classe["mpsi"], "secretmpsi")
        self.assertEqual(mdp_par_classe["pcsi"], "motdepasse")

    def test_refus_utiliser_coffre_saisie_manuelle_pour_toutes(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "motmaitre", "mpsi", "secretmpsi")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        traites = []
        self._run(["--tout"], traites, entrees_input=["n"])
        self.assertTrue(all(mdp == "motdepasse" for _, mdp in traites))

    def test_trois_echecs_mdp_maitre_replie_en_manuel(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "motmaitre", "mpsi", "secretmpsi")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        traites = []
        self._run(["--tout"], traites, entrees_input=["o"],
                  demander_side_effect=["faux1", "faux2", "faux3", "motdepasse", "motdepasse"])
        self.assertTrue(all(mdp == "motdepasse" for _, mdp in traites))

    def test_mdp_argument_ignore_le_coffre(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "motmaitre", "mpsi", "secretmpsi")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        traites = []
        # entrees_input reste vide (défaut de _run) : le moindre appel à
        # input() ferait échouer le test avec StopIteration, donc l'absence
        # d'exception prouve qu'aucune question sur le coffre n'a été posée.
        self._run(["--tout", "--mdp", "impose"], traites)
        self.assertTrue(all(mdp == "impose" for _, mdp in traites))


class TestCommandesCoffre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin_cfg = Path(self.tmp.name) / "config.json"
        self.chemin_coffre = Path(self.tmp.name) / "coffre.json"
        c = cdp_config._vide()
        c["classes"].append({"nom": "mpsi", "url": "https://x/mpsi",
                             "login": "l", "dossier": "cours_cdp"})
        cdp_config.enregistrer(self.chemin_cfg, c)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv):
        with mock.patch.object(cdp_scraper, "parse_args",
                               return_value=cdp_scraper.parse_args(argv)), \
             mock.patch.object(cdp_scraper, "verifier_accord"), \
             mock.patch.object(cdp_scraper.cdp_config, "chemin_config",
                               return_value=self.chemin_cfg):
            cdp_scraper.main()

    def test_coffre_ajouter_puis_lister(self):
        with mock.patch.object(cdp_scraper, "demander",
                               side_effect=["motmaitre", "secretclasse"]):
            self._run(["--coffre-ajouter", "mpsi", "--coffre", str(self.chemin_coffre)])
        coffre = cdp_coffre.charger(self.chemin_coffre)
        self.assertEqual(cdp_coffre.recuperer(coffre, "motmaitre", "mpsi"), "secretclasse")
        config = cdp_config.charger(self.chemin_cfg)
        self.assertTrue(cdp_config.selectionner(config, ["mpsi"])[0]["coffre_propose"])

    def test_coffre_ajouter_classe_absente_de_la_config(self):
        with mock.patch.object(cdp_scraper, "demander") as demander_mock:
            self._run(["--coffre-ajouter", "inconnue", "--coffre", str(self.chemin_coffre)])
        demander_mock.assert_not_called()
        self.assertFalse(self.chemin_coffre.is_file())

    def test_coffre_lister_vide(self):
        # Ne doit pas planter sans coffre existant ; pas d'assertion de sortie
        # (afficher_coffre imprime sur stdout), on vérifie juste l'absence d'exception.
        self._run(["--coffre-lister", "--coffre", str(self.chemin_coffre)])

    def test_coffre_supprimer(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "motmaitre", "mpsi", "secret")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        self._run(["--coffre-supprimer", "mpsi", "--coffre", str(self.chemin_coffre)])
        self.assertFalse(cdp_coffre.contient(cdp_coffre.charger(self.chemin_coffre), "mpsi"))

    def test_coffre_changer_mdp(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "ancien", "mpsi", "secret")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        with mock.patch.object(cdp_scraper, "demander", side_effect=["ancien", "nouveau"]):
            self._run(["--coffre-changer-mdp", "--coffre", str(self.chemin_coffre)])
        relu = cdp_coffre.charger(self.chemin_coffre)
        self.assertEqual(cdp_coffre.recuperer(relu, "nouveau", "mpsi"), "secret")

    def test_coffre_changer_mdp_coffre_vide_ne_plante_pas(self):
        with mock.patch.object(cdp_scraper, "demander") as demander_mock:
            self._run(["--coffre-changer-mdp", "--coffre", str(self.chemin_coffre)])
        demander_mock.assert_not_called()

    def test_config_supprimer_retire_aussi_le_coffre(self):
        coffre = cdp_coffre._vide()
        cdp_coffre.ajouter(coffre, "motmaitre", "mpsi", "secret")
        cdp_coffre.enregistrer(self.chemin_coffre, coffre)
        self._run(["--config-supprimer", "mpsi", "--coffre", str(self.chemin_coffre)])
        self.assertFalse(cdp_coffre.contient(cdp_coffre.charger(self.chemin_coffre), "mpsi"))

    def test_config_supprimer_sans_coffre_ne_plante_pas(self):
        # Aucun fichier coffre.json : la cascade de suppression doit rester silencieuse.
        self._run(["--config-supprimer", "mpsi", "--coffre", str(self.chemin_coffre)])
        self.assertFalse(self.chemin_coffre.exists())


class TestDecisionCoffre(unittest.TestCase):
    def test_o_enregistrer(self):
        self.assertEqual(cdp_scraper.decision_coffre("o"), "enregistrer")
        self.assertEqual(cdp_scraper.decision_coffre("O"), "enregistrer")

    def test_j_jamais(self):
        self.assertEqual(cdp_scraper.decision_coffre("j"), "jamais")

    def test_n_ou_vide_ou_autre_plus_tard(self):
        for reponse in ("n", "", "x", "  "):
            self.assertEqual(cdp_scraper.decision_coffre(reponse), "plus_tard")


class TestProposerCoffre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin_cfg = Path(self.tmp.name) / "config.json"
        self.chemin_coffre = Path(self.tmp.name) / "coffre.json"
        self.config = cdp_config._vide()
        self.cfg = {"nom": "mpsi", "url": "https://x/mpsi", "login": "l", "dossier": "cours_cdp"}
        cdp_config.ajouter_ou_maj(self.config, self.cfg)
        cdp_config.enregistrer(self.chemin_cfg, self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_deja_tranche_ne_redemande_pas(self):
        cfg = dict(self.cfg, coffre_propose=True)
        with mock.patch.object(cdp_scraper, "_tty", return_value=True), \
             mock.patch("builtins.input") as input_mock:
            cdp_scraper.proposer_coffre(self.config, self.chemin_cfg, cfg, "secret",
                                        str(self.chemin_coffre))
        input_mock.assert_not_called()

    def test_hors_tty_ne_demande_rien(self):
        with mock.patch.object(cdp_scraper, "_tty", return_value=False), \
             mock.patch("builtins.input") as input_mock:
            cdp_scraper.proposer_coffre(self.config, self.chemin_cfg, self.cfg, "secret",
                                        str(self.chemin_coffre))
        input_mock.assert_not_called()

    def test_choix_o_enregistre_et_marque_propose(self):
        with mock.patch.object(cdp_scraper, "_tty", return_value=True), \
             mock.patch("builtins.input", return_value="o"), \
             mock.patch.object(cdp_scraper, "demander", return_value="motmaitre"):
            cdp_scraper.proposer_coffre(self.config, self.chemin_cfg, self.cfg, "secretclasse",
                                        str(self.chemin_coffre))
        coffre = cdp_coffre.charger(self.chemin_coffre)
        self.assertEqual(cdp_coffre.recuperer(coffre, "motmaitre", "mpsi"), "secretclasse")
        config_relue = cdp_config.charger(self.chemin_cfg)
        self.assertTrue(cdp_config.selectionner(config_relue, ["mpsi"])[0]["coffre_propose"])

    def test_choix_n_ne_marque_rien(self):
        with mock.patch.object(cdp_scraper, "_tty", return_value=True), \
             mock.patch("builtins.input", return_value="n"):
            cdp_scraper.proposer_coffre(self.config, self.chemin_cfg, self.cfg, "secret",
                                        str(self.chemin_coffre))
        config_relue = cdp_config.charger(self.chemin_cfg)
        self.assertNotIn("coffre_propose", cdp_config.selectionner(config_relue, ["mpsi"])[0])
        self.assertFalse(self.chemin_coffre.exists())

    def test_choix_j_marque_sans_enregistrer(self):
        with mock.patch.object(cdp_scraper, "_tty", return_value=True), \
             mock.patch("builtins.input", return_value="j"):
            cdp_scraper.proposer_coffre(self.config, self.chemin_cfg, self.cfg, "secret",
                                        str(self.chemin_coffre))
        config_relue = cdp_config.charger(self.chemin_cfg)
        self.assertTrue(cdp_config.selectionner(config_relue, ["mpsi"])[0]["coffre_propose"])
        self.assertFalse(self.chemin_coffre.exists())

    def test_reutilise_mdp_maitre_deja_connu_sans_redemander(self):
        with mock.patch.object(cdp_scraper, "_tty", return_value=True), \
             mock.patch("builtins.input", return_value="o"), \
             mock.patch.object(cdp_scraper, "demander") as demander_mock:
            cdp_scraper.proposer_coffre(self.config, self.chemin_cfg, self.cfg, "secretclasse",
                                        str(self.chemin_coffre), mdp_maitre_connu="motmaitre")
        demander_mock.assert_not_called()
        coffre = cdp_coffre.charger(self.chemin_coffre)
        self.assertEqual(cdp_coffre.recuperer(coffre, "motmaitre", "mpsi"), "secretclasse")


class TestRunClasseUniqueProposeCoffre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin_cfg = Path(self.tmp.name) / "config.json"
        self.config = cdp_config._vide()
        cdp_config.ajouter_ou_maj(self.config, {
            "nom": "mpsi", "url": "https://cahier-de-prepa.fr/mpsi",
            "login": "l", "dossier": "cours_cdp",
        })
        cdp_config.enregistrer(self.chemin_cfg, self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, mdp=None):
        return types.SimpleNamespace(url="https://cahier-de-prepa.fr/mpsi", login="l", mdp=mdp,
                                     sortie="cours_cdp", simulation=False, reprise=False,
                                     coffre=None)

    def test_classe_deja_connue_relancee_par_url_propose_le_coffre(self):
        # Cas réel signalé : une classe mémorisée avant l'existence du coffre,
        # relancée via --url (pas de config vide) — doit quand même déclencher
        # proposer_coffre après un traitement réussi.
        with mock.patch.object(cdp_scraper, "demander", return_value="secretclasse"), \
             mock.patch.object(cdp_scraper, "traiter_classe",
                               return_value={"nom": "mpsi", "ok": True, "compteur": {}, "volume": {}}), \
             mock.patch.object(cdp_scraper, "proposer_coffre") as proposer_mock:
            cdp_scraper.run_classe_unique(self._args(), self.config, self.chemin_cfg)
        proposer_mock.assert_called_once()
        _, _, cfg_arg, mdp_arg, _ = proposer_mock.call_args[0]
        self.assertEqual(cfg_arg["nom"], "mpsi")
        self.assertEqual(mdp_arg, "secretclasse")

    def test_mdp_impose_n_appelle_pas_proposer_coffre(self):
        with mock.patch.object(cdp_scraper, "traiter_classe",
                               return_value={"nom": "mpsi", "ok": True, "compteur": {}, "volume": {}}), \
             mock.patch.object(cdp_scraper, "proposer_coffre") as proposer_mock:
            cdp_scraper.run_classe_unique(self._args(mdp="impose"), self.config, self.chemin_cfg)
        proposer_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
