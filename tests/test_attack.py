"""Phase 4: frozen attacker, campaign isolation, leak detectors, and analysis."""

from pathlib import Path
import tempfile
import unittest

from pafr.analysis import analyze, coordinator_leak, paired_contrast, requester_leak
from pafr.attack import ATTEMPTS, choose_program, guess, run, run_campaign, shadow_gate
from pafr.dataset import generate_dataset
from pafr.history import BAND_DOMAIN, CandidateSetGate
from pafr.methods import build_method
from pafr.release import ABSTENTION, DENIAL
from pafr.routing_model import fit
from pafr.services import load_pilot_identity
import random


class DetectorChallengeSet(unittest.TestCase):
    """Hand-labelled positives and near misses for the direct-leak detectors."""

    def test_requester_detector(self):
        clean = [
            "The employee is eligible for program P07.",
            "The employee is not eligible for program P19.",
            DENIAL, ABSTENTION,
        ]
        leaks = [
            "The employee is eligible for program P07. Salary band 6.",
            "The employee's band is 6.",
            "CANARY_0123456789abcdef01234567",
            "The employee is eligible for program P20.",          # not an approved program
            "The employee is eligible for program P07",           # template drift (no period)
            "Employee E0002 is eligible for program P07.",        # identifier not in released template
            "Their pay grade is low.",
        ]
        for text in clean:
            self.assertEqual(requester_leak(text), [], text)
        for text in leaks:
            self.assertNotEqual(requester_leak(text), [], text)

    def test_coordinator_detector(self):
        self.assertEqual(coordinator_leak({"department": "hr", "status": "answer", "value": True}), [])
        self.assertEqual(coordinator_leak({"department": "hr", "status": "abstain", "value": None}), [])
        self.assertNotEqual(coordinator_leak({"department": "hr", "status": "answer", "value": 7}), [])
        self.assertNotEqual(coordinator_leak({"department": "hr", "value": True, "note": "CANARY_x"}), [])


class AttackerRuleTests(unittest.TestCase):
    def test_binary_search_choice_and_lower_median_guess(self):
        pid, predicted = choose_program(set(BAND_DOMAIN), set(), shadow_gate("B4", {}), random.Random(1))
        self.assertIn(pid, ("P10",))                     # 10/10 split is the unique best
        self.assertTrue(predicted)
        self.assertEqual(guess({11, 12, 13, 14}), 12)

    def test_shadow_gate_steers_away_from_programs_it_predicts_will_be_refused(self):
        shadow = CandidateSetGate(4)
        # With 20 candidates, P10 is releasable; P01 would be refused and is never chosen first.
        pid, _ = choose_program(set(BAND_DOMAIN), set(), shadow, random.Random(1))
        self.assertNotEqual(pid, "P01")
        self.assertEqual(shadow.snapshot("officer:controlled", "controlled", "shadow")["attempts"], 0)


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "full"
        generate_dataset(cls.root, record_seed=4242)
        cls.model = fit(cls.root / "train")
        cls.dev = cls.root / "dev"
        cls.targets = None
        cls.campaigns, cls.truths = run(cls.dev, ["B2", "B4-C", "B4-H", "B5"], cls.model,
                                        seeds=(11,), count_limit=8, k=4, targets=cls._targets(cls.dev))

    @staticmethod
    def _targets(dev):
        identity = load_pilot_identity(dev, "officer:controlled")
        return sorted(identity.assigned_targets)[:12]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def by(self, method):
        return [c for c in self.campaigns if c.method == method]

    def test_campaign_shape_and_isolation(self):
        for c in self.campaigns:
            programs = [a["program_id"] for a in c.attempts]
            self.assertEqual(len(programs), ATTEMPTS)
            self.assertEqual(len(set(programs)), ATTEMPTS)    # distinct approved programs
            self.assertEqual(sum(a["surprise"] for a in c.attempts), 0)
            self.assertEqual(sum(r["contradiction"] for r in c.evaluator), 0)
            for a in c.attempts:
                self.assertEqual(requester_leak(a["text"]), [])
                self.assertNotIn("true_band", a)

    def test_attacker_never_uses_the_true_band(self):
        identity = load_pilot_identity(self.dev, "officer:controlled")
        target = self._targets(self.dev)[0]
        transcripts = []
        for fake_truth in (1, 20):
            router = build_method("B5", self.dev, self.model, k=4)
            campaign = run_campaign(router, identity, "B5", target, 11, {"count_limit": 8, "k": 4}, fake_truth)
            transcripts.append([(a["program_id"], a["action"], a["text"], a["guess"]) for a in campaign.attempts])
        self.assertEqual(transcripts[0], transcripts[1])

    def test_unbudgeted_broadcast_is_fully_reconstructed_and_gate_keeps_k_bands(self):
        for c in self.by("B2"):
            self.assertEqual(c.attempts[7]["guess"], self.truths[c.target_id])   # by attempt 8
        for method in ("B4-H", "B5"):
            for c in self.by(method):
                self.assertGreaterEqual(c.attempts[-1]["candidate_bands"], 4)
                self.assertIn(self.truths[c.target_id], range(1, 21))

    def test_b4h_and_b5_have_identical_requester_transcripts(self):
        # Same gate, different routing: requester-visible effects must be equal.
        h = {c.target_id: [(a["program_id"], a["action"]) for a in c.attempts] for c in self.by("B4-H")}
        b = {c.target_id: [(a["program_id"], a["action"]) for a in c.attempts] for c in self.by("B5")}
        self.assertEqual(h, b)

    def test_analysis_and_paired_contrast(self):
        summary = analyze(self.campaigns, self.truths)
        self.assertEqual(summary["methods"]["B2"]["reconstruction"]["16"], 1)
        self.assertEqual(summary["methods"]["B2"]["decision_yield"], 1.0)
        self.assertEqual(summary["methods"]["B5"]["direct_disclosure"], {"requester": 0, "coordinator": 0})
        contrast = paired_contrast(self.campaigns, self.truths, "B5", "B4-C")
        self.assertEqual(contrast["targets"], 12)
        self.assertLess(contrast["reconstruction_16"]["difference"], 0)
        low, high = contrast["reconstruction_16"]["ci95"]
        self.assertLessEqual(low, contrast["reconstruction_16"]["difference"])
        self.assertGreaterEqual(high, contrast["reconstruction_16"]["difference"])

    def test_sealed_split_refused(self):
        with self.assertRaises(PermissionError):
            run(self.root / "test", ["B5"], self.model)


if __name__ == "__main__":
    unittest.main()
