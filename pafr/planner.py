"""Deterministic, constrained question planner for the PAFR pilot.

This parser is not an authority: it cannot authenticate a user, resolve a
``self`` target, or grant a role mentioned in a question.  It only converts a
small allowlist of whole questions into immutable candidate service calls.  A
gateway/router must bind the plan to trusted identity context, and every
department must repeat its own authorization before retrieval.
"""

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class ServiceCall:
    """An allowlisted operation a future router may submit to one service."""

    department: str
    operation: str
    parameters: tuple[tuple[str, str], ...] = ()

    def parameter_dict(self):
        return dict(self.parameters)


@dataclass(frozen=True)
class QueryPlan:
    """A parsed intent, not an authorization decision or execution result."""

    operation: str
    target_mode: str
    target_id: str | None
    program_id: str | None
    candidate_calls: tuple[ServiceCall, ...]


POLICY_CALL = ServiceCall("policy", "public_policy")
TRAINING_STATUS_CALL = ServiceCall("training", "training_status")
TRAINING_COMPLETE_CALL = ServiceCall("training", "training_complete")
FINANCE_BUDGET_CALL = ServiceCall("finance", "budget_available")
HR_CALL_PREFIX = ("hr", "employment_and_salary_ok")
FINANCE_CERTIFICATE_PREFIX = ("finance", "eligibility_certificate")


def plan_question(question):
    """Return a safe structured plan, or ``None`` for all unsupported input.

    Accepted forms intentionally use exact whole-question matching.  Text such
    as role claims, extra instructions, multiple questions, unknown programs,
    or ambiguous targets returns ``None`` and therefore cannot trigger a
    service call.
    """
    text = _normalize(question)
    if text is None:
        return None
    if _self_training(text):
        return QueryPlan("training_status", "self", None, None, (TRAINING_STATUS_CALL,))
    program = _public_policy(text)
    if program is not None:
        return QueryPlan("public_policy", "none", None, program, (_program_call(POLICY_CALL, program),))
    eligibility = _eligibility(text)
    if eligibility is not None:
        target, program = eligibility
        calls = (
            _program_call(POLICY_CALL, program),
            _program_call(ServiceCall(*HR_CALL_PREFIX), program),
            TRAINING_COMPLETE_CALL,
            FINANCE_BUDGET_CALL,
        )
        # A certificate can be an alternative minimal evidence path, but the
        # router—not the question—must decide whether to request it.
        if program in {"P07", "P15"}:
            calls += (_program_call(ServiceCall(*FINANCE_CERTIFICATE_PREFIX), program),)
        return QueryPlan("eligibility", "explicit", target, program, calls)
    return None


def _normalize(question):
    if type(question) is not str or not 0 < len(question) <= 2000:
        return None
    text = " ".join(unicodedata.normalize("NFKC", question).casefold().split()).rstrip(".?!")
    return text or None


def _self_training(text):
    return re.fullmatch(
        r"(?:training|my training(?: status)?|is my training complete|"
        r"have i completed (?:my )?training|what is my training status|"
        r"(?:show|check)(?: me)? my training(?: status)?)",
        text,
    ) is not None


def _public_policy(text):
    match = re.fullmatch(
        r"(?:policy|public policy|what are the rules for(?: program)?|"
        r"what are the published conditions for(?: program)?|"
        r"show the rules for(?: program)?) (p\d{2})",
        text,
    )
    return _program(match[1]) if match else None


def _eligibility(text):
    match = re.fullmatch(
        r"(?:does|is) (e\d{4}) (?:qualify|eligible) for (p\d{2})|"
        r"(?:assess|check eligibility for) (e\d{4}) for (p\d{2})",
        text,
    )
    if not match:
        return None
    target, program = match[1] or match[3], match[2] or match[4]
    program = _program(program)
    return (target.upper(), program) if program is not None else None


def _program(program):
    if re.fullmatch(r"p(?:0[1-9]|1[0-9])", program) is None:
        return None
    return program.upper()


def _program_call(call, program):
    return ServiceCall(call.department, call.operation, (("program_id", program),))
