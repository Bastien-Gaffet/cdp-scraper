import unittest
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cdp_agenda


class TestMoisAnneeScolaire(unittest.TestCase):
    def test_rentree_annee_courante(self):
        mois = cdp_agenda.mois_annee_scolaire(date(2026, 9, 15))
        self.assertEqual(mois, [
            (2026, 9), (2026, 10), (2026, 11), (2026, 12),
            (2027, 1), (2027, 2), (2027, 3), (2027, 4), (2027, 5), (2027, 6),
        ])

    def test_milieu_annee_scolaire(self):
        mois = cdp_agenda.mois_annee_scolaire(date(2027, 3, 1))
        self.assertEqual(mois[0], (2026, 9))
        self.assertEqual(mois[-1], (2027, 6))

    def test_bascule_au_30_juin(self):
        mois = cdp_agenda.mois_annee_scolaire(date(2026, 6, 30))
        self.assertEqual(mois[0], (2025, 9))
        self.assertEqual(mois[-1], (2026, 6))


class TestParserDateAgenda(unittest.TestCase):
    def test_jour_seul_sans_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Le vendredi 12 septembre 2026")
        self.assertEqual(debut, datetime(2026, 9, 12, 0, 0))
        self.assertIsNone(fin)
        self.assertTrue(journee)

    def test_jour_seul_avec_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Le vendredi 12 septembre 2026 à 8h")
        self.assertEqual(debut, datetime(2026, 9, 12, 8, 0))
        self.assertEqual(fin, datetime(2026, 9, 12, 8, 0))
        self.assertFalse(journee)

    def test_jour_seul_avec_plage_horaire(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Le dimanche 1er mars 2027 de 8h à 12h30")
        self.assertEqual(debut, datetime(2027, 3, 1, 8, 0))
        self.assertEqual(fin, datetime(2027, 3, 1, 12, 30))
        self.assertFalse(journee)

    def test_plusieurs_jours_sans_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Du vendredi 12 septembre 2026 au dimanche 14 septembre 2026")
        self.assertEqual(debut, datetime(2026, 9, 12, 0, 0))
        self.assertEqual(fin, datetime(2026, 9, 14, 0, 0))
        self.assertTrue(journee)

    def test_plusieurs_jours_avec_heure(self):
        debut, fin, journee = cdp_agenda.parser_date_agenda(
            "Du vendredi 12 septembre 2026 à 8h au samedi 13 septembre 2026 à 12h")
        self.assertEqual(debut, datetime(2026, 9, 12, 8, 0))
        self.assertEqual(fin, datetime(2026, 9, 13, 12, 0))
        self.assertFalse(journee)

    def test_texte_non_reconnu_leve_valueerror(self):
        with self.assertRaises(ValueError):
            cdp_agenda.parser_date_agenda("pas une date")


if __name__ == "__main__":
    unittest.main()
