"""Fail-closed local router for the constrained PAFR pilot.

The router binds a deterministic planner result to trusted context, then calls
only the predeclared departmental operations. It is intentionally not an
adaptive learned router or a disclosure-history gate; those remain research
work. Departments still repeat authorization for every call.
"""

from dataclasses import dataclass
import json

from .history import DisclosureHistory, ReleaseGate
from .planner import QueryPlan, ServiceCall, plan_question
from .retriever import DocumentIndex
from .sealing import require_unsealed
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
    # Coordinator view: every departmental reply the coordinator observed,
    # including replies not needed for the final answer. Never shown to a
    # requester; used to measure coordinator exposure.
    observations: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RoutingPolicy:
    """Order in which eligibility evidence is requested after the public rule.

    ``steps`` lists ``certificate``, ``hr``, ``training`` and ``finance`` in
    request order. Sequential routing stops at the first sufficient plan;
    ``broadcast`` requests every step and then selects one sufficient plan.
    """

    name: str
    steps: object  # callable: program_id -> tuple[str, ...]
    broadcast: bool = False


STATIC_STEPS = ("certificate", "hr", "training", "finance")
STATIC_ROUTING = RoutingPolicy("static", lambda program: STATIC_STEPS)
_STEP_DEPARTMENTS = {"certificate": "finance", "hr": "hr", "training": "training", "finance": "finance"}


@dataclass(frozen=True)
class RouterMethod:
    """Named router strategy used for protocol comparisons."""

    name: str
    description: str
    factory: object


class FederatedRouter:
    """Execute only the planner's static, permitted pilot service calls."""

    def __init__(self, data_dir, history=None, unseal=False, routing=None):
        require_unsealed(data_dir, unseal)
        self.last_payload_bytes = 0  # set per request; trusted diagnostics only
        self.routing = STATIC_ROUTING if routing is None else routing
        if not isinstance(self.routing, RoutingPolicy):
            raise TypeError("routing must be a RoutingPolicy")
        self._services = {
            "hr": HRService(data_dir),
            "training": TrainingService(data_dir),
            "finance": FinanceService(data_dir),
            "policy": PolicyService(data_dir),
        }
        self.history = DisclosureHistory() if history is None else history
        if not isinstance(self.history, ReleaseGate):
            raise TypeError("history must be a ReleaseGate instance")

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
        self.last_payload_bytes = 0
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
        self.history.record(decision, result.action, result.answer if result.action == "answer" else None)
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
            if (plan.target_mode == "self"
                    and (plan.target_id is None or plan.target_id == identity.employee_id)
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
        reply = self._services[call.department].retrieve(request)
        self.last_payload_bytes += _payload_bytes(call.department, request, reply)
        return reply

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
        by_step = {"hr": calls[1], "training": calls[2], "finance": calls[3]}
        certificate = next((call for call in calls if call.operation == "eligibility_certificate"), None)
        if certificate is not None:
            by_step["certificate"] = certificate
        steps = tuple(self.routing.steps(plan.program_id))
        if sorted(set(steps)) != sorted(STATIC_STEPS) or len(steps) != len(STATIC_STEPS):
            raise ValueError("Routing policy must order exactly the four evidence steps")
        steps = tuple(step for step in steps if step in by_step)

        replies, observations = {}, []
        for step in steps:
            reply = self._call(by_step[step], context, target)
            replies[step] = reply
            observations.append({"department": _STEP_DEPARTMENTS[step], "step": step,
                                 "status": reply.status, "value": reply.value})
            if reply.status == "deny":
                return RouterReply("deny", reason="not_authorized", service_calls=1 + len(replies),
                                   observations=tuple(observations))
            if not self.routing.broadcast and _sufficient(replies):
                break
        return _decide(policy, replies, 1 + len(replies), tuple(observations))


def _sufficient(replies):
    """True once the replies so far complete one sufficient evidence plan."""
    certificate = replies.get("certificate")
    if certificate is not None and certificate.status == "answer":
        return True
    conditions = [replies.get(step) for step in ("hr", "training", "finance")]
    if any(r is not None and r.status == "answer" and r.value is False for r in conditions):
        return True
    return all(r is not None and r.status == "answer" and r.value is True for r in conditions)


def _decide(policy, replies, call_count, observations):
    """Select one sufficient plan: certificate, then a failing condition, then all true."""
    def reply(action, answer=None, evidence=(), reason=None):
        return RouterReply(action, answer, evidence, reason, call_count, observations)

    certificate = replies.get("certificate")
    if certificate is not None and certificate.status == "answer":
        return reply("answer", certificate.value, policy.evidence + certificate.evidence)
    conditions = [replies.get(step) for step in ("hr", "training", "finance")]
    for condition in conditions:
        if condition is not None and condition.status == "answer" and condition.value is False:
            return reply("answer", False, policy.evidence + condition.evidence)
    if all(c is not None and c.status == "answer" and c.value is True for c in conditions):
        return reply("answer", True, policy.evidence + tuple(u for c in conditions for u in c.evidence))
    return reply("abstain", reason="evidence_unavailable")


class AdaptiveRouter(FederatedRouter):
    """Optional risk-aware extension that uses local document relevance before release."""

    def __init__(self, data_dir, history=None, risk_threshold=1.0, retriever=None, unseal=False):
        super().__init__(data_dir, history=history, unseal=unseal)
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


def _payload_bytes(department, request, reply):
    """Application payload volume at one fixed JSON boundary (not network traffic)."""
    message = {
        "to": department,
        "request": {"request_id": request.request_id, "requester_id": request.identity.requester_id,
                    "role": request.identity.role, "fixture": request.fixture, "purpose": request.purpose,
                    "target_id": request.target_id, "operation": request.operation, "parameters": request.parameters},
        "reply": {"status": reply.status, "operation": reply.operation, "value": reply.value,
                  "evidence": list(reply.evidence), "reason": reply.reason},
    }
    return len(json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8"))


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
