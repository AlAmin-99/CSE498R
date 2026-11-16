"""Final requester-facing release boundary for constrained router results.

No router reason, raw service value, evidence identifier, or model text is
shown directly to a requester. This module regenerates the deterministic plan
from the original question and permits only a small set of fact-consistent,
template-based responses.
"""

import re

from .planner import plan_question
from .router import RouterContext, RouterReply


DENIAL = "Access denied. This request is not permitted."
ABSTENTION = "I cannot provide an answer for this request."


def release(question, context, result):
    """Return a safe ``(action, text)`` pair for one router result.

    The caller retains internal evidence and reason fields separately. This
    function deliberately returns generic wording for denials and abstentions
    so those states do not expose record existence, service failures, or gate
    state to a requester.
    """
    if not isinstance(context, RouterContext) or not isinstance(result, RouterReply):
        return "abstain", ABSTENTION
    if result.action == "deny":
        return "deny", DENIAL
    plan = plan_question(question)
    if plan is None:
        return "abstain", ABSTENTION
    if result.action != "answer":
        return "abstain", ABSTENTION
    if plan.operation == "public_policy":
        text = _public_policy(plan, context, result)
    elif plan.operation == "training_status":
        text = _training_status(plan, context, result)
    elif plan.operation == "eligibility":
        text = _eligibility(plan, context, result)
    else:
        text = None
    return ("answer", text) if text is not None else ("abstain", ABSTENTION)


def _public_policy(plan, context, result):
    pid = plan.program_id
    value = result.answer
    if not _public_context_ok(context):
        return None
    if not _evidence_is(result.evidence, (("policy", f"policy:{pid}", "program_rule"),)):
        return None
    if value != {
        "program_id": pid,
        "salary_band_max": int(pid[1:]),
        "requires": ["active employment", "completed training", "available budget"],
    }:
        return None
    return (f"Program {pid} requires a salary band of {int(pid[1:])} or below, active employment, "
            "completed training, and available budget.")


def _training_status(plan, context, result):
    target = context.identity.employee_id
    if (not _employee_context_ok(context) or plan.target_mode != "self" or type(target) is not str or type(result.answer) is not bool
            or not _evidence_is(result.evidence, (("training", f"{context.fixture}:training:{target}", "training_status"),))):
        return None
    return "Your training is complete." if result.answer else "Your training is not complete."


def _eligibility(plan, context, result):
    target, pid = plan.target_id, plan.program_id
    if not _officer_context_ok(context, target) or type(result.answer) is not bool or type(target) is not str:
        return None
    policy = ("policy", f"policy:{pid}", "program_rule")
    hr = ("hr", f"{context.fixture}:hr:{target}", "employment_and_salary_ok")
    training = ("training", f"{context.fixture}:training:{target}", "training_complete")
    finance = ("finance", f"{context.fixture}:finance:{target}", "budget_available")
    certificate = ("finance", f"{context.fixture}:finance:{target}", f"certificate:{pid}")
    units = _evidence_units(result.evidence)
    if units is None:
        return None
    permitted = []
    if pid in {"P07", "P15"}:
        permitted.append({policy, certificate})
    if result.answer is True:
        permitted.append({policy, hr, training, finance})
    else:
        permitted.extend(({policy, hr}, {policy, training}, {policy, finance}))
    if units not in permitted:
        return None
    return f"The employee is {'eligible' if result.answer else 'not eligible'} for program {pid}."


def _evidence_is(evidence, expected):
    return _evidence_units(evidence) == set(expected)


def _evidence_units(evidence):
    if type(evidence) is not tuple:
        return None
    units = set()
    for item in evidence:
        if type(item) is not dict or set(item) != {"silo", "document_id", "fact"}:
            return None
        silo, document_id, fact = item["silo"], item["document_id"], item["fact"]
        if not all(type(value) is str for value in (silo, document_id, fact)):
            return None
        if "CANARY_" in document_id or "CANARY_" in fact or re.search(r"\s", document_id):
            return None
        units.add((silo, document_id, fact))
    return units if len(units) == len(evidence) else None


def _public_context_ok(context):
    return (
        context.identity.authenticated is True and context.fixture in context.identity.fixtures
        and context.purpose == "public_policy" and context.purpose in context.identity.purposes
    )


def _employee_context_ok(context):
    identity = context.identity
    return (identity.authenticated is True and identity.role == "employee"
            and context.fixture in identity.fixtures and context.purpose == "self_service"
            and context.purpose in identity.purposes)


def _officer_context_ok(context, target):
    identity = context.identity
    return (identity.authenticated is True and identity.role == "benefits_officer"
            and context.fixture in identity.fixtures and context.purpose == "benefits_assessment"
            and context.purpose in identity.purposes and target in identity.assigned_targets)
