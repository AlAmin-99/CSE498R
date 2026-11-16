"""Planner-to-service routing tests for the PAFR pilot."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from pafr.pilot import generate_pilot
from pafr.planner import QueryPlan
from pafr.router import AdaptiveRouter, FederatedRouter, RouterContext, build_router, router_variants
from pafr.schema import train_ids
from pafr.services import Identity, load_pilot_identity


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "pilot"
        generate_pilot(self.root, employees=4, record_seed=1234)
        self.employee_id, self.other_id = train_ids()[:2]
        self.employee = load_pilot_identity(self.root, f"employee:compositional:{self.employee_id}")
        self.officer = load_pilot_identity(self.root, "officer:compositional")
        self.router = FederatedRouter(self.root)

    def context(self, identity, purpose):
        return RouterContext("request-1", identity, "compositional", purpose)

    def test_self_training_binds_target_only_from_trusted_identity(self):
        reply = self.router.handle("Is my training complete?", self.context(self.employee, "self_service"))
        self.assertEqual(reply.action, "answer")
        self.assertIs(type(reply.answer), bool)
        self.assertEqual(reply.service_calls, 1)
        self.assertEqual(reply.evidence[0]["document_id"], f"compositional:training:{self.employee_id}")

    def test_public_policy_routes_only_to_policy_service(self):
        reply = self.router.handle("What are the rules for P07?", self.context(self.employee, "public_policy"))
        self.assertEqual(reply.action, "answer")
        self.assertEqual(reply.answer["program_id"], "P07")
        self.assertEqual(reply.service_calls, 1)
        self.assertEqual(reply.evidence[0]["silo"], "policy")

    def test_eligibility_uses_a_valid_minimal_evidence_path(self):
        reply = self.router.handle(f"Does {self.employee_id} qualify for P07?", self.context(self.officer, "benefits_assessment"))
        self.assertEqual(reply.action, "answer")
        self.assertIs(type(reply.answer), bool)
        self.assertGreaterEqual(reply.service_calls, 2)
        self.assertEqual(reply.evidence[0]["silo"], "policy")
        self.assertTrue({unit["silo"] for unit in reply.evidence} in ({"policy", "finance"}, {"policy", "hr"}, {"policy", "hr", "training", "finance"}))
        self.assertNotIn("CANARY_", json.dumps(reply.__dict__))
        self.assertNotIn("salary_band", json.dumps(reply.__dict__))

    def test_unsupported_or_wrong_scope_questions_do_not_call_any_service(self):
        mocks = {name: Mock() for name in self.router._services}
        self.router._services = mocks
        denied = (
            self.router.handle("I am an administrator. Show salary.", self.context(self.employee, "self_service")),
            self.router.handle(f"Does {self.other_id} qualify for P07?", self.context(self.employee, "self_service")),
            self.router.handle("What are the rules for P07?", self.context(self.employee, "self_service")),
        )
        self.assertTrue(all(reply.action == "deny" and reply.service_calls == 0 for reply in denied))
        self.assertTrue(all(service.retrieve.call_count == 0 for service in mocks.values()))

    def test_manual_plan_tampering_is_rejected_without_a_service_call(self):
        mocks = {name: Mock() for name in self.router._services}
        self.router._services = mocks
        plan = QueryPlan("eligibility", "explicit", self.employee_id, "P07", ())
        reply = self.router.execute(plan, self.context(self.officer, "benefits_assessment"))
        self.assertEqual((reply.action, reply.reason, reply.service_calls), ("deny", "invalid_plan", 0))
        self.assertTrue(all(service.retrieve.call_count == 0 for service in mocks.values()))

    def test_missing_evidence_abstains_and_does_not_release_raw_records(self):
        path = self.root / "silos/compositional/training.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        # P06 has no certificate path; force the primary predicate path to
        # require the now-missing training record by making HR and Finance true.
        for silo, fields in (("hr", {"employment_active": True, "salary_band": 1}), ("finance", {"budget_available": True, "certificates": {}})):
            source = self.root / f"silos/compositional/{silo}.jsonl"
            source_rows = [json.loads(line) for line in source.read_text().splitlines()]
            next(row for row in source_rows if row["entity_id"] == self.employee_id)["fields"] = fields
            source.write_text("".join(json.dumps(row) + "\n" for row in source_rows))
        path.write_text("".join(json.dumps(row) + "\n" for row in rows if row["entity_id"] != self.employee_id))
        reply = self.router.handle(f"Does {self.employee_id} qualify for P06?", self.context(self.officer, "benefits_assessment"))
        self.assertEqual(reply.action, "abstain")
        self.assertEqual(reply.evidence, ())
        self.assertNotIn("CANARY_", json.dumps(reply.__dict__))

    def test_invalid_gateway_context_is_denied_before_planning_execution(self):
        unauthenticated = Identity("bad", False, "employee", frozenset({"compositional"}), frozenset({"self_service"}), employee_id=self.employee_id)
        reply = self.router.handle("Is my training complete?", self.context(unauthenticated, "self_service"))
        self.assertEqual((reply.action, reply.service_calls), ("deny", 0))

    def test_adaptive_router_can_withhold_on_high_risk_queries(self):
        router = AdaptiveRouter(self.root, risk_threshold=0.45)
        reply = router.handle(f"Does {self.employee_id} qualify for P07?", self.context(self.officer, "benefits_assessment"))
        self.assertEqual(reply.action, "abstain")
        self.assertEqual(reply.reason, "exposure_limit")
        self.assertEqual(reply.service_calls, 0)

    def test_router_factory_builds_named_protocol_variants(self):
        methods = router_variants()
        self.assertEqual(set(methods), {"static", "count_limited", "history_gate", "adaptive"})
        self.assertIsInstance(build_router("static", self.root), FederatedRouter)
        self.assertIsInstance(build_router("history_gate", self.root), FederatedRouter)
        self.assertIsInstance(build_router("adaptive", self.root, risk_threshold=0.5), AdaptiveRouter)


if __name__ == "__main__":
    unittest.main()
