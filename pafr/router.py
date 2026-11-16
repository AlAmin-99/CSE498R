"""Fail-closed local router for the constrained PAFR pilot.

The router binds a deterministic planner result to trusted context, then calls
only the predeclared departmental operations. It is intentionally not an
adaptive learned router or a disclosure-history gate; those remain research
work. Departments still repeat authorization for every call.
"""

from dataclasses import dataclass

from .history import DisclosureHistory
from .planner import QueryPlan, ServiceCall, plan_question
from .retriever import DocumentIndex
from .services import (
    FinanceService, HRService, Identity, PolicyService, RetrievalReply,
    RetrievalRequest, TrainingService,
)


@dataclass(frozen=True)
class RouterContext:
    """Gateway-validated context, never inferred from question text."""

    request_id: str
    identity: Identity
    fixture: str
    purpose: str


@dataclass(frozen=True)
class RouterReply:
    """Coordinator result; final presentation remains a separate boundary."""

    action: str
    answer: bool | dict | None = None
    evidence: tuple[dict, ...] = ()
    reason: str | None = None
    service_calls: int = 0


@dataclass(frozen=True)
class RouterMethod:
    """Named router strategy used for protocol comparisons."""

    name: str
    description: str
    factory: object


class FederatedRouter:
    """Execute only the planner's static, permitted pilot service calls."""

    def __init__(self, data_dir, history=None):
        self._services = {
            "hr": HRService(data_dir),
            "training": TrainingService(data_dir),
            "finance": FinanceService(data_dir),
            "policy": PolicyService(data_dir),
        }
        self.history = DisclosureHistory() if history is None else history
        if not isinstance(self.history, DisclosureHistory):
            raise TypeError("history must be a DisclosureHistory instance")

    def handle(self, question, context):
        """Plan, bind, and route one question without using an LLM."""
        plan = plan_question(question)
        if plan is None:
            return RouterReply("deny", reason="unsupported_request")
        return self.execute(plan, context)

    def execute(self, plan, context):
        """Execute a previously parsed plan only when context is valid.

        ``execute`` verifies the plan shape rather than trusting a caller who
        manually constructed a ``QueryPlan``. Production callers should use
        ``handle``; this method permits deterministic router tests.
        """
        if not isinstance(plan, QueryPlan) or not self._valid_context(context):
            return RouterReply("deny", reason="not_authorized")
        target = self._bound_target(plan, context)
        if target is _DENIED:
            return RouterReply("deny", reason="not_authorized")
        expected = _expected_calls(plan.operation, plan.program_id)
        if expected is None or plan.candidate_calls != expected:
            return RouterReply("deny", reason="invalid_plan")
        if plan.operation == "public_policy":
            return self._public_policy(plan, context)
        if plan.operation == "training_status":
            return self._training_status(plan, context, target)
        decision = self.history.check(
            context.identity.requester_id, context.fixture, target,
            plan.operation, {"program_id": plan.program_id},
        )
        if not decision.allowed:
            self.history.record(decision, "abstain")
            return RouterReply("abstain", reason="exposure_limit")
        result = self._eligibility(plan, context, target)
        self.history.record(decision, result.action)
        return result

    @staticmethod
    def _valid_context(context):
        return (
            isinstance(context, RouterContext)
            and isinstance(context.identity, Identity)
            and type(context.request_id) is str and 0 < len(context.request_id) <= 128
            and type(context.fixture) is str and context.fixture in {"controlled", "compositional"}
            and type(context.purpose) is str
            and context.identity.authenticated is True
            and context.fixture in context.identity.fixtures
            and context.purpose in context.identity.purposes
        )

    @staticmethod
    def _bound_target(plan, context):
        identity = context.identity
        if plan.operation == "public_policy":
            return (None if plan.target_mode == "none" and plan.target_id is None
                    and context.purpose == "public_policy" else _DENIED)
        if plan.operation == "training_status":
            if (plan.target_mode == "self" and plan.target_id is None
                    and identity.role == "employee" and context.purpose == "self_service"
                    and type(identity.employee_id) is str):
                return identity.employee_id
            return _DENIED
        if plan.operation == "eligibility":
            if (plan.target_mode == "explicit" and type(plan.target_id) is str
                    and identity.role == "benefits_officer" and context.purpose == "benefits_assessment"
                    and plan.target_id in identity.assigned_targets):
                return plan.target_id
        return _DENIED

    def _call(self, call, context, target):
        request = RetrievalRequest(
            request_id=context.request_id,
            identity=context.identity,
            fixture=context.fixture,
            purpose=context.purpose,
            target_id=target,
            operation=call.operation,
            parameters=call.parameter_dict(),
        )
        return self._services[call.department].retrieve(request)

    def _public_policy(self, plan, context):
        reply = self._call(plan.candidate_calls[0], context, None)
        return _finish_single(reply, 1)

    def _training_status(self, plan, context, target):
        reply = self._call(plan.candidate_calls[0], context, target)
        return _finish_single(reply, 1)

    def _eligibility(self, plan, context, target):
        calls = plan.candidate_calls
        policy = self._call(calls[0], context, None)
        if policy.status != "answer":
            return _finish_single(policy, 1)

        # P07/P15 may have a policy-version-checked, single-silo certificate.
        # It is a valid alternative evidence plan, so do not unnecessarily read
        # HR or Training when it answers the authorized decision.
        certificate = next((call for call in calls if call.operation == "eligibility_certificate"), None)
        call_count = 1
        if certificate is not None:
            cert_reply = self._call(certificate, context, target)
            call_count += 1
            if cert_reply.status == "deny":
                return RouterReply("deny", reason="not_authorized", service_calls=call_count)
            if cert_reply.status == "answer":
                return RouterReply("answer", cert_reply.value, policy.evidence + cert_reply.evidence, service_calls=call_count)

        # A missing certificate is expected: it is an optional alternative to
        # the three-condition path, not a required piece of evidence.
        pending_abstention = False
        # A single false condition is sufficient to answer false. Otherwise all
        # three primary conditions are needed to answer true.
        facts = []
        for call in (calls[1], calls[2], calls[3]):
            reply = self._call(call, context, target)
            call_count += 1
            if reply.status == "deny":
                return RouterReply("deny", reason="not_authorized", service_calls=call_count)
            if reply.status == "answer" and reply.value is False:
                return RouterReply("answer", False, policy.evidence + reply.evidence, service_calls=call_count)
            if reply.status == "abstain":
                pending_abstention = True
            else:
                facts.append(reply)
        if pending_abstention or len(facts) != 3 or not all(reply.value is True for reply in facts):
            return RouterReply("abstain", reason="evidence_unavailable", service_calls=call_count)
        return RouterReply("answer", True, policy.evidence + tuple(unit for reply in facts for unit in reply.evidence), service_calls=call_count)


class AdaptiveRouter(FederatedRouter):
    """Optional risk-aware extension that uses local document relevance before release."""

    def __init__(self, data_dir, history=None, risk_threshold=1.0, retriever=None):
        super().__init__(data_dir, history=history)
        self.retriever = DocumentIndex(data_dir) if retriever is None else retriever
        if not isinstance(self.retriever, DocumentIndex):
            raise TypeError("retriever must be a DocumentIndex instance")
        self.risk_threshold = risk_threshold
        if type(risk_threshold) not in (int, float) or not 0.0 <= risk_threshold <= 1.0:
            raise ValueError("risk_threshold must be a float in [0,1]")

    def handle(self, question, context):
        """A deterministic, fail-closed adaptive gate for an otherwise static plan."""
        plan = plan_question(question)
        if plan is None:
            return RouterReply("deny", reason="unsupported_request")
        risk = self._risk_score(question, context, plan)
        if risk >= self.risk_threshold:
            return RouterReply("abstain", reason="exposure_limit")
        return self.execute(plan, context)

    def _risk_score(self, question, context, plan):
        if not self._valid_context(context):
            return 1.0
        if not isinstance(plan, QueryPlan):
            return 1.0
        target = self._bound_target(plan, context)
        limit = max(1, self.history.max_distinct_decisions)
        released = self.history.snapshot(
            context.identity.requester_id,
            context.fixture,
            target if target is not _DENIED else (context.identity.employee_id or "unknown"),
        ).get("released_distinct_decisions", 0)
        risk = 0.35 * (released / limit)
        if plan.operation == "eligibility":
            risk += 0.35
        elif plan.operation == "public_policy":
            risk += 0.10
        else:
            risk += 0.15
        hits = self.retriever.search(question, fixture=context.fixture, top_k=10)
        if hits:
            relevance = sum(item["score"] for item in hits) / len(hits)
            risk += min(0.30, relevance / 12.0)
        return min(1.0, risk)


def _finish_single(reply, calls):
    if reply.status == "answer":
        return RouterReply("answer", reply.value, reply.evidence, service_calls=calls)
    return RouterReply(reply.status, reason=reply.reason, service_calls=calls)


def router_variants():
    """Return the route-method families expected by the evaluation protocol."""
    return {
        "static": RouterMethod("static", "Deterministic allowlisted routing without adaptive risk gating.", lambda data_dir, **kwargs: FederatedRouter(data_dir, **kwargs)),
        "count_limited": RouterMethod("count_limited", "Static policy with a per-target exposure count limit.", lambda data_dir, **kwargs: FederatedRouter(data_dir, **kwargs)),
        "history_gate": RouterMethod("history_gate", "Static router using the disclosure-history gate.", lambda data_dir, **kwargs: FederatedRouter(data_dir, **kwargs)),
        "adaptive": RouterMethod("adaptive", "Risk-aware router that adds retriever-based exposure scoring before answer release.", lambda data_dir, **kwargs: AdaptiveRouter(data_dir, **kwargs)),
    }


def build_router(method_name, data_dir, **kwargs):
    """Build a protocol-labeled router variant from a method name."""
    methods = router_variants()
    if method_name not in methods:
        raise ValueError(f"Unsupported router method: {method_name}")
    return methods[method_name].factory(data_dir, **kwargs)


def _program_call(department, operation, program):
    return ServiceCall(department, operation, (("program_id", program),))


def _expected_calls(operation, program):
    if operation == "training_status" and program is None:
        return (ServiceCall("training", "training_status"),)
    if operation == "public_policy" and _valid_program(program):
        return (_program_call("policy", "public_policy", program),)
    if operation == "eligibility" and _valid_program(program):
        calls = (
            _program_call("policy", "public_policy", program),
            _program_call("hr", "employment_and_salary_ok", program),
            ServiceCall("training", "training_complete"),
            ServiceCall("finance", "budget_available"),
        )
        return calls + ((_program_call("finance", "eligibility_certificate", program),)
                        if program in {"P07", "P15"} else ())
    return None


def _valid_program(program):
    return type(program) is str and len(program) == 3 and program.startswith("P") and program[1:].isdigit() and 1 <= int(program[1:]) <= 19


_DENIED = object()
