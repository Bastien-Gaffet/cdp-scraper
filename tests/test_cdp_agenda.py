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


if __name__ == "__main__":
    unittest.main()
