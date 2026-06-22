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


if __name__ == "__main__":
    unittest.main()
