"""Protocol methods: candidate-set gate, persistence, learned and exposure routing."""

import json
from pathlib import Path
import tempfile
import unittest

from pafr.dataset import generate_dataset
from pafr.endtoend import evaluate
from pafr.history import CandidateSetGate, DisclosureHistory, NoGate
from pafr.methods import METHOD_IDS, build_method
from pafr.router import RouterContext
from pafr.routing_model import exposure_steps, fit, relevance_steps
from pafr.services import load_pilot_identity
from pafr.validation import read_jsonl


def ask(gate, program, answer=None, target="E0001"):
    """Check one program; record the given answer if released, else a withhold."""
    decision = gate.check("officer:x", "controlled", target, "eligibility", {"program_id": program})
    if decision.allowed:
        gate.record(decision, "answer", answer)
    else:
        gate.record(decision, "abstain")
    return decision.allowed


class CandidateSetGateTests(unittest.TestCase):
    def test_extreme_first_questions_are_withheld_and_middle_ones_released(self):
        gate = CandidateSetGate(k=4)
        self.assertFalse(ask(gate, "P01"))          # "yes" would reveal band 1 exactly
        self.assertFalse(ask(gate, "P19"))          # "no" would reveal band 20 exactly
        self.assertTrue(ask(gate, "P10", False))    # bands 11..20 remain
        self.assertEqual(gate.snapshot("officer:x", "controlled", "E0001")["candidate_bands"], 10)

    def test_worst_case_split_below_k_is_withheld_and_determined_answers_released(self):
        gate = CandidateSetGate(k=4)
        ask(gate, "P10", False)                     # 11..20
        self.assertTrue(ask(gate, "P15", False))    # yes->11..15 (5), no->16..20 (5)
        self.assertFalse(ask(gate, "P17"))          # yes->16..17 (2) < 4
        self.assertTrue(ask(gate, "P05", False))    # already determined: no new information
        snap = gate.snapshot("officer:x", "controlled", "E0001")
        self.assertEqual((snap["candidate_bands"], snap["withheld"]), (5, 1))

    def test_refusals_depend_only_on_the_requester_transcript(self):
        # Two targets with different true bands but the same released answers
        # must receive identical release decisions for every next program.
        first, second = CandidateSetGate(k=3), CandidateSetGate(k=3)
        for gate, target in ((first, "E0001"), (second, "E0002")):
            ask(gate, "P08", True, target)
        for program in (f"P{j:02d}" for j in range(1, 20)):
            a = first.check("officer:x", "controlled", "E0001", "eligibility", {"program_id": program}).allowed
            b = second.check("officer:x", "controlled", "E0002", "eligibility", {"program_id": program}).allowed
            self.assertEqual(a, b, program)
            for gate, target in ((first, "E0001"), (second, "E0002")):
                gate._buckets[next(s for s in gate._buckets if s.target_id == target)].pending.clear()

    def test_k_one_never_withholds_and_contradictions_do_not_empty_the_set(self):
        gate = CandidateSetGate(k=1)
        self.assertTrue(all(ask(gate, f"P{j:02d}", True) for j in range(1, 20)))
        gate = CandidateSetGate(k=2)
        ask(gate, "P10", False)                     # 11..20
        ask(gate, "P05", True)                      # contradicts the salary-only model
        self.assertEqual(gate.snapshot("officer:x", "controlled", "E0001")["candidate_bands"], 10)

    def test_one_pending_decision_at_a_time(self):
        gate = CandidateSetGate(k=2)
        first = gate.check("officer:x", "controlled", "E0001", "eligibility", {"program_id": "P10"})
        second = gate.check("officer:x", "controlled", "E0001", "eligibility", {"program_id": "P11"})
        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)

    def test_invalid_configuration(self):
        for k in (0, 21, "4", 4.0):
            with self.assertRaises(ValueError):
                CandidateSetGate(k=k)
        with self.assertRaises(ValueError):
            CandidateSetGate(k=4).record(
                CandidateSetGate(k=4).check("officer:x", "controlled", "E0001", "eligibility", {"program_id": "P10"}),
                "answer")


class PersistenceTests(unittest.TestCase):
    def test_gate_state_survives_a_new_session_and_rejects_other_configs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "history.json"
            gate = CandidateSetGate(k=4, state_path=path)
            ask(gate, "P10", False)
            ask(gate, "P15", False)
            ask(gate, "P17")
            reloaded = CandidateSetGate(k=4, state_path=path)
            self.assertEqual(reloaded.snapshot("officer:x", "controlled", "E0001"),
                             gate.snapshot("officer:x", "controlled", "E0001"))
            self.assertFalse(ask(reloaded, "P17"))
            with self.assertRaises(ValueError):
                CandidateSetGate(k=5, state_path=path)
            with self.assertRaises(ValueError):
                DisclosureHistory(4, state_path=path)

    def test_count_gate_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "count.json"
            gate = DisclosureHistory(2, state_path=path)
            ask(gate, "P03", True)
            ask(gate, "P04", True)
            self.assertFalse(ask(DisclosureHistory(2, state_path=path), "P05"))


class MethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "full"
        generate_dataset(cls.root, record_seed=2026)
        cls.model = fit(cls.root / "train")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_model_is_fitted_only_on_training_data(self):
        with self.assertRaises(ValueError):
            fit(self.root / "dev")
        self.assertEqual(self.model["trained_split"], "train")
        text = json.dumps(self.model)
        self.assertNotIn("CANARY_", text)
        self.assertNotIn("E0", text)  # no entity identifiers in the model

    def test_routing_orders(self):
        for j in range(1, 20):
            pid = f"P{j:02d}"
            self.assertEqual(sorted(relevance_steps(self.model, pid)), ["certificate", "finance", "hr", "training"])
            steps = exposure_steps(self.model, pid)
            self.assertEqual((steps[0], steps[-1]), ("certificate", "hr"))

    def test_every_method_matches_gold_or_withholds_on_dev(self):
        for method in METHOD_IDS:
            with self.subTest(method=method):
                results = evaluate(self.root / "dev", modes=("structured",),
                                   router_factory=lambda view: build_method(method, view, self.model, k=4))
                self.assertEqual([r for r in results if not r.passed and not r.withheld], [])
                withheld = sum(r.withheld for r in results)
                self.assertEqual(withheld > 0, method in ("B4-H", "B4-N", "B5"))

    def test_gate_and_routing_tradeoffs(self):
        def totals(method):
            results = evaluate(self.root / "dev", modes=("structured",),
                               router_factory=lambda view: build_method(method, view, self.model, k=4))
            return sum(r.service_calls for r in results), sum(r.hr_observations for r in results)
        b2, b4, b4h, b5 = (totals(m) for m in ("B2", "B4", "B4-H", "B5"))
        self.assertLess(b4[0], b2[0])               # learned routing makes fewer calls than broadcast
        self.assertLess(b5[1], b4h[1])              # exposure routing shows the coordinator less HR
        self.assertEqual(b4, totals("B4-C"))        # a cap of 16 never binds on single questions

    def test_broadcast_observes_every_department_and_b5_avoids_hr_when_possible(self):
        identities = json.loads((self.root / "dev/evaluator/identities.json").read_text())
        rows = {r["entity_id"]: r for r in read_jsonl(self.root / "dev/silos/compositional/training.jsonl")}
        untrained = next(e for e, r in rows.items() if not r["fields"]["training_complete"])
        officer = next(i for i, row in identities.items()
                       if i.startswith("officer:compositional") and untrained in row["assigned_targets"])
        context = RouterContext("t", load_pilot_identity(self.root / "dev", officer), "compositional", "benefits_assessment")
        question = f"Does {untrained} qualify for P12?"
        b2 = build_method("B2", self.root / "dev").handle(question, context)
        self.assertEqual({o["department"] for o in b2.observations}, {"hr", "training", "finance"})
        b5 = build_method("B5", self.root / "dev", self.model, k=1).handle(question, context)
        self.assertEqual((b5.action, b5.answer), ("answer", False))
        self.assertNotIn("hr", {o["department"] for o in b5.observations})

    def test_methods_need_a_model_and_respect_the_seal(self):
        with self.assertRaises(ValueError):
            build_method("B5", self.root / "dev")
        with self.assertRaises(ValueError):
            build_method("B9", self.root / "dev", self.model)
        with self.assertRaises(PermissionError):
            build_method("B4", self.root / "test", self.model)
        self.assertIsInstance(build_method("B2", self.root / "dev").history, NoGate)


if __name__ == "__main__":
    unittest.main()
