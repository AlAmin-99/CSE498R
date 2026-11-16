"""Disclosure-history and router-gate tests for the PAFR pilot."""

from pathlib import Path
import tempfile
import unittest

from pafr.history import DisclosureHistory
from pafr.pilot import generate_pilot
from pafr.router import FederatedRouter, RouterContext
from pafr.schema import train_ids
from pafr.services import load_pilot_identity


class DisclosureHistoryTests(unittest.TestCase):
    def setUp(self):
        self.history = DisclosureHistory(max_distinct_decisions=1)

    def decision(self, program, requester="officer:a", fixture="controlled", target="E0208"):
        return self.history.check(requester, fixture, target, "eligibility", {"program_id": program})

    def test_first_distinct_release_consumes_limit_and_new_one_is_withheld(self):
        first = self.decision("P07")
        self.assertTrue(first.allowed)
        self.history.record(first, "answer")
        blocked = self.decision("P08")
        self.assertFalse(blocked.allowed)
        self.history.record(blocked, "abstain")
        self.assertEqual(self.history.snapshot("officer:a", "controlled", "E0208"), {
            "released_distinct_decisions": 1, "attempts": 2, "withheld": 1, "limit": 1,
        })

    def test_exact_repeat_is_allowed_without_expanding_distinct_release_count(self):
        first = self.decision("P07")
        self.history.record(first, "answer")
        repeat = self.decision("P07")
        self.assertTrue(repeat.allowed)
        self.assertTrue(repeat.duplicate)
        self.history.record(repeat, "answer")
        self.assertEqual(self.history.snapshot("officer:a", "controlled", "E0208")["released_distinct_decisions"], 1)

    def test_histories_are_isolated_by_requester_fixture_and_target(self):
        first = self.decision("P07")
        self.history.record(first, "answer")
        self.assertTrue(self.decision("P08", requester="officer:b").allowed)
        self.assertTrue(self.decision("P08", fixture="compositional").allowed)
        self.assertTrue(self.decision("P08", target="E0209").allowed)

    def test_abstention_does_not_consume_a_disclosure_slot(self):
        missing = self.decision("P07")
        self.history.record(missing, "abstain")
        self.assertTrue(self.decision("P08").allowed)


class RouterHistoryGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "pilot"
        generate_pilot(self.root, employees=4, record_seed=1234)
        self.employee_id = train_ids()[0]
        self.officer = load_pilot_identity(self.root, "officer:controlled")
        self.history = DisclosureHistory(max_distinct_decisions=1)
        self.router = FederatedRouter(self.root, history=self.history)
        self.context = RouterContext("campaign-1", self.officer, "controlled", "benefits_assessment")

    def test_router_withholds_new_decision_before_calling_services_at_limit(self):
        first = self.router.handle(f"Does {self.employee_id} qualify for P07?", self.context)
        self.assertEqual(first.action, "answer")
        blocked = self.router.handle(f"Does {self.employee_id} qualify for P08?", self.context)
        self.assertEqual((blocked.action, blocked.reason, blocked.service_calls), ("abstain", "exposure_limit", 0))
        snapshot = self.history.snapshot(self.officer.requester_id, "controlled", self.employee_id)
        self.assertEqual(snapshot["released_distinct_decisions"], 1)
        self.assertEqual(snapshot["withheld"], 1)

    def test_public_policy_and_exact_repeat_do_not_consume_another_slot(self):
        public_context = RouterContext("public-1", self.officer, "controlled", "public_policy")
        self.assertEqual(self.router.handle("What are the rules for P07?", public_context).action, "answer")
        first = self.router.handle(f"Does {self.employee_id} qualify for P07?", self.context)
        repeat = self.router.handle(f"Does {self.employee_id} qualify for P07?", self.context)
        self.assertEqual((first.action, repeat.action), ("answer", "answer"))
        self.assertEqual(self.history.snapshot(self.officer.requester_id, "controlled", self.employee_id)["released_distinct_decisions"], 1)


if __name__ == "__main__":
    unittest.main()
