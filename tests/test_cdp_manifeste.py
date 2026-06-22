import unittest
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_manifeste


class TestChargerEnregistrer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.classe = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_renvoie_manifeste_vide(self):
        m = cdp_manifeste.charger(self.classe)
        self.assertEqual(m["version"], cdp_manifeste.VERSION)
        self.assertEqual(m["documents"], {})

    def test_round_trip(self):
        m = cdp_manifeste.charger(self.classe)
        m["documents"]["42"] = {"nom": "x.pdf"}
        cdp_manifeste.enregistrer(self.classe, m)
        relu = cdp_manifeste.charger(self.classe)
        self.assertEqual(relu["documents"]["42"]["nom"], "x.pdf")

    def test_json_corrompu_repart_a_vide(self):
        (self.classe / cdp_manifeste.NOM_FICHIER).write_text("{pas du json", encoding="utf-8")
        m = cdp_manifeste.charger(self.classe)
        self.assertEqual(m["documents"], {})

    def test_version_future_leve(self):
        futur = {"version": cdp_manifeste.VERSION + 1, "documents": {}}
        (self.classe / cdp_manifeste.NOM_FICHIER).write_text(
            json.dumps(futur), encoding="utf-8")
        with self.assertRaises(cdp_manifeste.ManifesteVersionFuture):
            cdp_manifeste.charger(self.classe)

    def test_enregistrer_est_atomique_pas_de_tmp_residuel(self):
        m = cdp_manifeste.charger(self.classe)
        cdp_manifeste.enregistrer(self.classe, m)
        residus = list(self.classe.glob("*.tmp"))
        self.assertEqual(residus, [])


class TestEmpreinte(unittest.TestCase):
    def test_doc_normal_utilise_docdonnees(self):
        doc = {"id": "1", "empreinte": "pdf, 1 jan, 100 ko"}
        self.assertEqual(cdp_manifeste.empreinte(doc), "pdf, 1 jan, 100 ko")

    def test_doc_sans_empreinte_renvoie_vide(self):
        self.assertEqual(cdp_manifeste.empreinte({"id": "1"}), "")

    def test_contenu_genere_hashe(self):
        a = cdp_manifeste.empreinte({"id": "pc_x", "contenu_html": "<p>A</p>"})
        b = cdp_manifeste.empreinte({"id": "pc_x", "contenu_html": "<p>B</p>"})
        self.assertTrue(a.startswith("h:"))
        self.assertNotEqual(a, b)

    def test_contenu_genere_stable(self):
        c1 = cdp_manifeste.empreinte({"contenu_html": "<p>même</p>"})
        c2 = cdp_manifeste.empreinte({"contenu_html": "<p>même</p>"})
        self.assertEqual(c1, c2)


class TestPlanifier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.classe = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _ecrire(self, chemin, nom):
        d = self.classe / chemin
        d.mkdir(parents=True, exist_ok=True)
        (d / nom).write_bytes(b"x")

    def _entree(self, **kw):
        base = {"url": "u", "nom": "f.pdf", "chemin": "Phys", "type": "pdf",
                "empreinte": "pdf, 1 jan, 100 ko", "taille": 1, "statut": "ok",
                "premiere_vue": "2026-01-01T00:00:00",
                "derniere_maj": "2026-01-01T00:00:00", "erreur": None}
        base.update(kw)
        return base

    def test_id_inconnu_est_nouveau(self):
        crawl = [{"id": "9", "empreinte": "pdf, 1 jan, 100 ko",
                  "chemin": "Phys", "nom": "f.pdf"}]
        plan = cdp_manifeste.planifier(crawl, cdp_manifeste._vide(), self.classe)
        self.assertEqual([d["id"] for d in plan["nouveau"]], ["9"])

    def test_empreinte_identique_et_present_est_a_jour(self):
        self._ecrire("Phys", "f.pdf")
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree()
        crawl = [{"id": "9", "empreinte": "pdf, 1 jan, 100 ko"}]
        plan = cdp_manifeste.planifier(crawl, man, self.classe)
        self.assertEqual([d["id"] for d in plan["a_jour"]], ["9"])

    def test_empreinte_differente_est_modifie(self):
        self._ecrire("Phys", "f.pdf")
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree()
        crawl = [{"id": "9", "empreinte": "pdf, 2 fev, 200 ko"}]
        plan = cdp_manifeste.planifier(crawl, man, self.classe)
        self.assertEqual([d["id"] for d in plan["modifie"]], ["9"])

    def test_fichier_absent_est_a_reprendre(self):
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree()  # fichier jamais écrit
        crawl = [{"id": "9", "empreinte": "pdf, 1 jan, 100 ko"}]
        plan = cdp_manifeste.planifier(crawl, man, self.classe)
        self.assertEqual([d["id"] for d in plan["a_reprendre"]], ["9"])

    def test_statut_echec_est_a_reprendre(self):
        self._ecrire("Phys", "f.pdf")
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree(statut="echec")
        crawl = [{"id": "9", "empreinte": "pdf, 1 jan, 100 ko"}]
        plan = cdp_manifeste.planifier(crawl, man, self.classe)
        self.assertEqual([d["id"] for d in plan["a_reprendre"]], ["9"])

    def test_id_manquant_du_crawl_est_disparu(self):
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree()
        plan = cdp_manifeste.planifier([], man, self.classe)
        self.assertEqual(plan["disparus"], ["9"])

    def test_complet_force_modifie(self):
        self._ecrire("Phys", "f.pdf")
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree()
        crawl = [{"id": "9", "empreinte": "pdf, 1 jan, 100 ko"}]
        plan = cdp_manifeste.planifier(crawl, man, self.classe, complet=True)
        self.assertEqual([d["id"] for d in plan["modifie"]], ["9"])

    def test_empreinte_vide_et_present_reste_a_jour(self):
        self._ecrire("Phys", "f.pdf")
        man = cdp_manifeste._vide()
        man["documents"]["9"] = self._entree(empreinte="")
        crawl = [{"id": "9"}]  # pas d'empreinte non plus
        plan = cdp_manifeste.planifier(crawl, man, self.classe)
        self.assertEqual([d["id"] for d in plan["a_jour"]], ["9"])


class TestMajEntree(unittest.TestCase):
    def setUp(self):
        self.man = cdp_manifeste._vide()
        self.doc = {"id": "9", "url": "https://x/download?id=9&dl",
                    "nom": "listing.pdf", "chemin": "Phys", "type": "pdf",
                    "empreinte": "pdf, 1 jan, 100 ko"}

    def test_creation_pose_premiere_vue(self):
        cdp_manifeste.maj_entree(self.man, self.doc, "ok", "reel.pdf", 1234,
                                 "2026-06-22T10:00:00")
        e = self.man["documents"]["9"]
        self.assertEqual(e["premiere_vue"], "2026-06-22T10:00:00")
        self.assertEqual(e["derniere_maj"], "2026-06-22T10:00:00")
        self.assertEqual(e["nom"], "reel.pdf")
        self.assertEqual(e["taille"], 1234)
        self.assertEqual(e["statut"], "ok")
        self.assertEqual(e["empreinte"], "pdf, 1 jan, 100 ko")
        self.assertIsNone(e["erreur"])

    def test_maj_conserve_premiere_vue(self):
        cdp_manifeste.maj_entree(self.man, self.doc, "ok", "reel.pdf", 1,
                                 "2026-01-01T00:00:00")
        cdp_manifeste.maj_entree(self.man, self.doc, "ok", "reel.pdf", 2,
                                 "2026-06-22T10:00:00")
        e = self.man["documents"]["9"]
        self.assertEqual(e["premiere_vue"], "2026-01-01T00:00:00")
        self.assertEqual(e["derniere_maj"], "2026-06-22T10:00:00")

    def test_echec_enregistre_erreur(self):
        cdp_manifeste.maj_entree(self.man, self.doc, "echec", "listing.pdf", 0,
                                 "2026-06-22T10:00:00", erreur="500")
        e = self.man["documents"]["9"]
        self.assertEqual(e["statut"], "echec")
        self.assertEqual(e["erreur"], "500")


class TestMarquerDisparus(unittest.TestCase):
    def test_marque_statut_disparu(self):
        man = cdp_manifeste._vide()
        man["documents"]["9"] = {"statut": "ok"}
        cdp_manifeste.marquer_disparus(man, ["9"])
        self.assertEqual(man["documents"]["9"]["statut"], "disparu")


class TestEntreesAReprendre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.classe = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_selectionne_echecs_avec_url(self):
        man = cdp_manifeste._vide()
        man["documents"]["1"] = {"url": "u1", "nom": "a.pdf", "chemin": "P",
                                 "type": "pdf", "statut": "echec"}
        man["documents"]["2"] = {"url": "u2", "nom": "b.pdf", "chemin": "P",
                                 "type": "pdf", "statut": "ok"}
        (self.classe / "P").mkdir()
        (self.classe / "P" / "b.pdf").write_bytes(b"x")  # 2 présent et ok
        docs = cdp_manifeste.entrees_a_reprendre(man, self.classe)
        self.assertEqual([d["id"] for d in docs], ["1"])
        self.assertEqual(docs[0]["url"], "u1")

    def test_inclut_ok_mais_fichier_manquant(self):
        man = cdp_manifeste._vide()
        man["documents"]["3"] = {"url": "u3", "nom": "c.pdf", "chemin": "P",
                                 "type": "pdf", "statut": "ok"}  # fichier absent
        docs = cdp_manifeste.entrees_a_reprendre(man, self.classe)
        self.assertEqual([d["id"] for d in docs], ["3"])

    def test_ignore_entrees_sans_url(self):
        man = cdp_manifeste._vide()
        man["documents"]["pc_x"] = {"nom": "Programme.html", "chemin": "Maths",
                                    "statut": "echec"}  # pas d'url
        docs = cdp_manifeste.entrees_a_reprendre(man, self.classe)
        self.assertEqual(docs, [])


if __name__ == "__main__":
    unittest.main()
