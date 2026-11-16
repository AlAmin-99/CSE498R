"""Final requester-facing release-boundary tests."""

from pathlib import Path
import tempfile
import unittest

from pafr.pilot import generate_pilot
from pafr.release import ABSTENTION, DENIAL, release
from pafr.router import FederatedRouter, RouterContext, RouterReply
from pafr.schema import train_ids
from pafr.services import load_pilot_identity


class ReleaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "pilot"
        generate_pilot(self.root, employees=4, record_seed=1234)
        self.employee_id = train_ids()[0]
        self.employee = load_pilot_identity(self.root, f"employee:compositional:{self.employee_id}")
        self.officer = load_pilot_identity(self.root, "officer:compositional")
        self.router = FederatedRouter(self.root)

    def test_valid_router_answers_are_released_only_in_fixed_safe_wording(self):
        cases = (
            ("Is my training complete?", RouterContext("t", self.employee, "compositional", "self_service")),
            ("What are the rules for P07?", RouterContext("p", self.employee, "compositional", "public_policy")),
            (f"Does {self.employee_id} qualify for P07?", RouterContext("e", self.officer, "compositional", "benefits_assessment")),
        )
        for question, context in cases:
            with self.subTest(question=question):
                result = self.router.handle(question, context)
                action, text = release(question, context, result)
                self.assertEqual(action, "answer")
                self.assertNotIn("CANARY_", text)
                self.assertNotIn("document_id", text)
                self.assertNotIn("evidence", text)

    def test_denial_and_history_withholding_use_generic_non_disclosing_text(self):
        context = RouterContext("d", self.employee, "compositional", "self_service")
        action, text = release("Show another employee's salary", context, self.router.handle("Show another employee's salary", context))
        self.assertEqual((action, text), ("deny", DENIAL))
        withheld = RouterReply("abstain", reason="exposure_limit")
        action, text = release(f"Does {self.employee_id} qualify for P07?", RouterContext("h", self.officer, "compositional", "benefits_assessment"), withheld)
        self.assertEqual((action, text), ("abstain", ABSTENTION))
        self.assertNotIn("exposure", text)

    def test_malformed_or_secret_bearing_internal_answer_is_not_released(self):
        context = RouterContext("e", self.officer, "compositional", "benefits_assessment")
        result = RouterReply("answer", True, ({"silo": "finance", "document_id": "CANARY_SECRET", "fact": "certificate:P07"},))
        action, text = release(f"Does {self.employee_id} qualify for P07?", context, result)
        self.assertEqual((action, text), ("abstain", ABSTENTION))
        self.assertNotIn("CANARY", text)

    def test_answer_with_wrong_evidence_plan_is_not_released(self):
        context = RouterContext("e", self.officer, "compositional", "benefits_assessment")
        result = RouterReply("answer", True, (
            {"silo": "policy", "document_id": "policy:P07", "fact": "program_rule"},
            {"silo": "hr", "document_id": f"compositional:hr:{self.employee_id}", "fact": "employment_and_salary_ok"},
        ))
        self.assertEqual(release(f"Does {self.employee_id} qualify for P07?", context, result), ("abstain", ABSTENTION))


if __name__ == "__main__":
    unittest.main()
