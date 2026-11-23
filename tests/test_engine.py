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


class RacingFormBook(unittest.TestCase):
    """SFF format: Sp is the fractional price as a number, Favs marks favourites, Type h/c/b/blank."""

    def test_sff_rows(self):
        from trends import importers
        hdr = "Id,Course,RaceDate,RaceTime,Race,Type,Class,AgeLimit,Prize,Ran,Distance,Yards,Going,Limit,WinTime,Seconds,FPos,DstBtn,TotalBtn,CardNo,HorseName,Draw,Sp,Age,Stone,Lbs,WeightLBS,Favs,Aid,Trainer,Jockey,Allow,OR,Comments\n"
        rows = [
            "1,Naas (IRE),28-Apr-25,14:00,Maiden Hurdle,h,,4YO plus,1,3,2m,3520,Yielding,,,,1,,0,1,Winner One,,0.615384615,5,11,4,158,Fav,,W P Mullins,P Townend,,,x",
            "1,Naas (IRE),28-Apr-25,14:00,Maiden Hurdle,h,,4YO plus,1,3,2m,3520,Yielding,,,,2,1,1,2,Second,,4,6,11,4,158,,,G Elliott,J Kennedy,,,x",
            "2,Southwell,30-Apr-25,17:05,Some Handicap,,6,3YO plus,1,2,1m3f,2442,Standard (AW - Tapeta),60,,,1,,0,1,Aw Horse,,5.5,4,9,6,132,,,Ollie Pears,J Doyle,,62,x",
            "2,Southwell,30-Apr-25,17:05,Some Handicap,,6,3YO plus,1,2,1m3f,2442,Standard (AW - Tapeta),60,,,2,1,1,2,Fav Horse,,1.5,4,9,12,138,Fav,,A Trainer,B Rider,,68,x",
        ]
        p = os.path.join(tempfile.mkdtemp(), "sff.csv")
        with open(p, "w", encoding="cp1252") as fh:
            fh.write(hdr + "\n".join(rows) + "\n")
        races = {r["course"]: r for r in importers.results_csv_to_races([p])}
        naas, sw = races["Naas (IRE)"], races["Southwell"]
        self.assertEqual((naas["region"], naas["type"], naas["fav_won"], naas["win_sp"]), ("ire", "hurdle", 1, "8/13F"))
        self.assertAlmostEqual(naas["dist_f"], 16.0)
        self.assertEqual((sw["surface"], sw["hcap"], sw["fav_won"], sw["fav_horse"]), ("aw", 1, 0, "Fav Horse"))
        self.assertEqual((sw["win_dec"], sw["win_from_top"], sw["win_or"]), (6.5, 6, 62))

    def test_course_names(self):
        self.assertEqual(U.course_name_key("Chelmsford City"), U.course_name_key("Chelmsford (AW)"))
        self.assertEqual(U.course_name_key("Naas (IRE)"), "naas")


class EndToEnd(unittest.TestCase):
    """Southwell 24 Nov 2026 against hand-checked late-November renewals."""

    @classmethod
    def setUpClass(cls):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "tests", "make_fixture.py")], stdout=subprocess.DEVNULL)
        cls.tmp = tempfile.mkdtemp()
        hist = os.path.join(cls.tmp, "h.csv.gz")
        fx = os.path.join(ROOT, "tests", "fixtures")
        env = dict(os.environ, RT_SITE=os.path.join(cls.tmp, "site"))  # never touch the live docs/
        run = lambda *a: subprocess.check_call([sys.executable, "-m", "trends", "--history", hist, *a], cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
        run("history", os.path.join(fx, "southwell_history.csv"))
        run("cards", os.path.join(fx, "southwell_racecards_2026-11-24.json"))
        with open(os.path.join(cls.tmp, "site", "data", "cards", "2026-11-24.json")) as fh:
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
