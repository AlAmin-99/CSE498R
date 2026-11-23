"""Phase 5: compositional stratum, operating-point rule, and freeze checks."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pafr import freeze
from pafr.attack import run
from pafr.dataset import generate_dataset
from pafr.routing_model import fit
from pafr.tuning import YIELD_BAND, select


def row(value, recon, yield_, calls=2.0):
    return {"parameter": "k", "value": value, "reconstruction_16": recon, "decision_yield": yield_, "calls_per_attempt": calls}


class SelectionRuleTests(unittest.TestCase):
    def test_lowest_reconstruction_inside_the_yield_band(self):
        rows = [row(1, 1.0, 1.0), row(2, 0.4, 0.92), row(3, 0.15, 0.80), row(4, 0.15, 0.80), row(6, 0.2, 0.52)]
        self.assertEqual(select(rows)["value"], 3)       # ties broken by lower parameter value

    def test_tie_breaks_prefer_yield_then_fewer_calls(self):
        rows = [row(3, 0.2, 0.78), row(4, 0.2, 0.82), row(5, 0.2, 0.82, calls=1.5)]
        self.assertEqual(select(rows)["value"], 5)

    def test_unavailable_when_no_setting_reaches_the_band(self):
        self.assertIsNone(select([row(1, 0.1, 0.5), row(2, 0.9, 0.95)]))
        self.assertEqual(YIELD_BAND, (0.75, 0.85))


class CompositionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "full"
        generate_dataset(cls.root, record_seed=77)
        cls.model = fit(cls.root / "train")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_attacker_ignores_no_until_conditions_are_known(self):
        campaigns, truths = run(self.root / "dev", ["B2"], self.model, seeds=(11,), fixture="compositional")
        for c in campaigns:
            seen_yes = False
            for a in c.attempts:
                if a["action"] == "answer" and "not eligible" not in a["text"]:
                    seen_yes = True
                if not seen_yes:
                    self.assertEqual(a["candidate_bands"], 20)
            self.assertIn(truths[c.target_id], range(1, 21))
            self.assertEqual(sum(a["surprise"] for a in c.attempts), 0)
            self.assertEqual(sum(r["contradiction"] for r in c.evaluator), 0)
            # Evaluator correctness uses true eligibility, so B2 is always right.
            self.assertTrue(all(r["released_correct"] for r in c.evaluator))

    def test_each_target_is_attacked_by_its_assigned_officer(self):
        campaigns, _ = run(self.root / "dev", ["B5"], self.model, seeds=(11,), fixture="compositional", k=3)
        self.assertEqual(len(campaigns), 48)
        self.assertTrue(all(a["action"] != "deny" for c in campaigns for a in c.attempts))


class FreezeTests(unittest.TestCase):
    def test_verify_reports_changed_and_new_files(self):
        recorded = {"sha256": {"pafr/a.py": "1", "pafr/b.py": "2"}, "operating_points": {"B5": {"k": 3}}}
        current = {"pafr/a.py": "1", "pafr/b.py": "CHANGED", "pafr/c.py": "3"}
        with patch.object(freeze, "read_json", side_effect=[recorded, {"selected": {"B5": {"k": 3}}}]), \
                patch.object(freeze, "fingerprints", return_value=current):
            problems = freeze.verify()
        self.assertIn("changed: pafr/b.py", problems)
        self.assertIn("new file not in freeze: pafr/c.py", problems)

    def test_verify_detects_changed_operating_points(self):
        recorded = {"sha256": {}, "operating_points": {"B5": {"k": 3}}}
        with patch.object(freeze, "read_json", side_effect=[recorded, {"selected": {"B5": {"k": 4}}}]), \
                patch.object(freeze, "fingerprints", return_value={}):
            self.assertEqual(freeze.verify(), ["operating points differ from the freeze"])


if __name__ == "__main__":
    unittest.main()
