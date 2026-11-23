"""Run: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from trends import util as U  # noqa: E402


class Util(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(U.dist_furlongs("2m4f88y"), 20.4)
        self.assertAlmostEqual(U.dist_furlongs("1m7f182y"), 15.83)
        self.assertEqual(U.dist_furlongs("2m4½f"), 20.5)
        self.assertEqual(U.dist_furlongs("20.5f"), 20.5)
        self.assertEqual(U.dist_furlongs("5f"), 5.0)

    def test_people(self):
        self.assertTrue(U.same_person("O Greenall & J Guerriero", "Oliver Greenall & Josh Guerriero"))
        self.assertTrue(U.same_person("J & A O'Neill", "Jonjo & A J O'Neill"))
        self.assertTrue(U.same_person("Miss V Williams", "Venetia Williams"))
        self.assertFalse(U.same_person("Miss V Williams", "Christian Williams"))
        self.assertTrue(U.same_person("J M Quinlan", "Jack Quinlan"))
        self.assertFalse(U.same_person("J M Quinlan", "Sean Quinlan"))
        self.assertTrue(U.same_person("Jonjo O'Neill Jr.", "Jonjo O'Neill Jr"))

    def test_sp(self):
        self.assertEqual(U.sp_to_dec("9/4F"), 3.25)
        self.assertEqual(U.sp_to_dec("Evens"), 2.0)
        self.assertTrue(U.sp_is_fav("9/4F"))
        self.assertFalse(U.sp_is_fav("11/2"))


class EndToEnd(unittest.TestCase):
    """Southwell 24 Nov 2026 against hand-checked late-November renewals."""

    @classmethod
    def setUpClass(cls):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "tests", "make_fixture.py")], stdout=subprocess.DEVNULL)
        cls.tmp = tempfile.mkdtemp()
        hist = os.path.join(cls.tmp, "h.csv.gz")
        fx = os.path.join(ROOT, "tests", "fixtures")
        run = lambda *a: subprocess.check_call([sys.executable, "-m", "trends", "--history", hist, *a], cwd=ROOT, stdout=subprocess.DEVNULL)
        run("history", os.path.join(fx, "southwell_history.csv"))
        run("cards", os.path.join(fx, "southwell_racecards_2026-11-24.json"))
        with open(os.path.join(ROOT, "docs", "data", "cards", "2026-11-24.json")) as fh:
            cls.doc = json.load(fh)
        cls.races = {r["off"]: r for m in cls.doc["meetings"] for r in m["races"]}

    def winners(self, off):
        return [x["winner"] for x in self.races[off]["renewals"]]

    def test_handicap_chase_renewals(self):
        self.assertEqual(self.winners("11:56"), ["Bravethewaves", "Jasmin De Grugy", "Sageburg County", "Gemirande"])

    def test_distractor_races_excluded(self):
        self.assertNotIn("Ile De Jersey", self.winners("11:56"))
        self.assertNotIn("Rockola", self.winners("14:26"))

    def test_maiden_age_trend(self):
        ins = [i["txt"] for i in self.races["12:56"]["summary"]["insights"]]
        self.assertIn("All 3 winners aged 5", ins)

    def test_novice_chase_favourites(self):
        r = self.races["12:26"]
        self.assertEqual(r["summary"]["fav_wins"], 0)
        self.assertEqual(r["summary"]["n"], 3)

    def test_defending_winner_flagged(self):
        bw = next(x for x in self.races["11:56"]["runners"] if x["horse"] == "Bravethewaves")
        kinds = {f["k"] for f in bw["flags"] if f["ok"]}
        self.assertIn("cdwin", kinds)
        self.assertIn("trainer", kinds)
        self.assertIn("jockey", kinds)

    def test_weight_rule_follows_headline_trend(self):
        ey = next(x for x in self.races["14:56"]["runners"] if x["horse"] == "Eyeeye")
        wt = next(f for f in ey["flags"] if f["k"] == "wt")
        self.assertFalse(wt["ok"])  # 14lb off top; 3/4 winners within 6lb

    def test_no_history_race(self):
        self.assertEqual(self.races["15:26"]["summary"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
