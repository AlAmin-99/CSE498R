"""Fail-closed single-silo retrieval services for the synthetic PAFR pilot.

Each service accepts a structured request rather than natural-language input.
It repeats scope checks before opening its own data and releases only a bounded
derived value plus evidence metadata. Raw rows, canaries, and untrusted notes
never leave this module. Logical service separation is not host isolation.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .schema import POLICY_VERSION, evidence


class ServiceError(ValueError):
    """The trusted caller supplied invalid structured context."""


@dataclass(frozen=True)
class Identity:
    """Gateway-validated claims; prompt text must never construct these."""

    requester_id: str
    authenticated: bool
    role: str | None = None
    fixtures: frozenset[str] = frozenset()
    purposes: frozenset[str] = frozenset()
    assigned_targets: frozenset[str] = frozenset()
    employee_id: str | None = None


@dataclass(frozen=True)
class RetrievalRequest:
    request_id: str
    identity: Identity
    fixture: str
    purpose: str
    target_id: str | None
    operation: str
    parameters: dict


@dataclass(frozen=True)
class RetrievalReply:
    """A minimized reply; evidence is empty for deny and abstain."""

    status: str
    operation: str
    value: bool | dict | None = None
    evidence: tuple[dict, ...] = ()
    reason: str | None = None


def load_pilot_identity(data_dir, requester_id):
    """Load one trusted mock identity for tests or future demo integration."""
    try:
        rows = json.loads((Path(data_dir) / "evaluator/identities.json").read_text(encoding="utf-8"))
        row = rows[requester_id]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ServiceError("Trusted identity data is unavailable or invalid.") from exc
    if type(row) is not dict or type(row.get("authenticated")) is not bool:
        raise ServiceError("Trusted identity data is unavailable or invalid.")
    for key in ("fixtures", "purposes", "assigned_targets"):
        if key in row and (type(row[key]) is not list or not all(type(v) is str for v in row[key])):
            raise ServiceError("Trusted identity data is unavailable or invalid.")
    if row.get("role") is not None and type(row["role"]) is not str:
        raise ServiceError("Trusted identity data is unavailable or invalid.")
    if row.get("employee_id") is not None and type(row["employee_id"]) is not str:
        raise ServiceError("Trusted identity data is unavailable or invalid.")
    return Identity(
        requester_id=requester_id, authenticated=row["authenticated"], role=row.get("role"),
        fixtures=frozenset(row.get("fixtures", [])), purposes=frozenset(row.get("purposes", [])),
        assigned_targets=frozenset(row.get("assigned_targets", [])), employee_id=row.get("employee_id"),
    )


class DepartmentService:
    """Base for a service that may open exactly one private pilot silo."""

    silo = None

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def retrieve(self, request):
        """Authorize before reading any departmental document."""
        if not isinstance(request, RetrievalRequest):
            raise ServiceError("Expected a structured retrieval request.")
        if not self._well_formed(request) or not self._authorized(request):
            return RetrievalReply("deny", request.operation, reason="not_authorized")
        try:
            return self._answer(request, self._target_rows(request))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            # Avoid revealing whether permitted evidence was absent, malformed,
            # or temporarily unreadable to the requester-facing layer.
            return RetrievalReply("abstain", request.operation, reason="evidence_unavailable")

    @staticmethod
    def _well_formed(request):
        identity = request.identity
        return (
            type(request.request_id) is str and 0 < len(request.request_id) <= 128
            and isinstance(identity, Identity) and type(identity.requester_id) is str
            and type(identity.authenticated) is bool
            and type(request.fixture) is str and request.fixture in {"controlled", "compositional"}
            and type(request.purpose) is str and type(request.operation) is str
            and type(request.parameters) is dict
            and (request.target_id is None or type(request.target_id) is str)
        )

    @staticmethod
    def _context_allowed(request):
        identity = request.identity
        return identity.authenticated is True and request.fixture in identity.fixtures and request.purpose in identity.purposes

    def _officer_scope(self, request):
        identity = request.identity
        return (self._context_allowed(request) and identity.role == "benefits_officer"
                and request.purpose == "benefits_assessment" and type(request.target_id) is str
                and request.target_id in identity.assigned_targets)

    def _employee_scope(self, request):
        identity = request.identity
        return (self._context_allowed(request) and identity.role == "employee"
                and request.purpose == "self_service" and request.target_id == identity.employee_id)

    def _target_rows(self, request):
        if self.silo == "policy" and request.target_id is None:
            return []
        if not isinstance(request.target_id, str) or re.fullmatch(r"E\d{4}", request.target_id) is None:
            raise ValueError("Invalid target ID.")
        path = self.data_dir / "silos" / request.fixture / f"{self.silo}.jsonl"
        matches = []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("entity_id") == request.target_id:
                    if (row.get("fixture") != request.fixture or row.get("silo") != self.silo
                            or row.get("split") != "train" or type(row.get("fields")) is not dict):
                        raise ValueError("Invalid department record.")
                    matches.append(row)
        return matches

    @staticmethod
    def _one_row(rows):
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("Conflicting department records.")
        return rows[0]

    def _authorized(self, request):
        raise NotImplementedError

    def _answer(self, request, rows):
        raise NotImplementedError


def _valid_program(program_id):
    return type(program_id) is str and re.fullmatch(r"P(?:0[1-9]|1[0-9])", program_id) is not None


class HRService(DepartmentService):
    """Release the approved eligibility predicate, never an HR row or salary."""

    silo = "hr"

    def _authorized(self, request):
        return (request.operation == "employment_and_salary_ok" and self._officer_scope(request)
                and set(request.parameters) == {"program_id"} and _valid_program(request.parameters["program_id"]))

    def _answer(self, request, rows):
        row = self._one_row(rows)
        if row is None:
            return RetrievalReply("abstain", request.operation, reason="evidence_unavailable")
        fields = row["fields"]
        active, band = fields.get("employment_active"), fields.get("salary_band")
        if type(active) is not bool or type(band) is not int or not 1 <= band <= 20:
            raise ValueError("Invalid HR fields.")
        cutoff = int(request.parameters["program_id"][1:])
        return RetrievalReply("answer", request.operation, active and band <= cutoff,
                              (evidence("hr", row["document_id"], "employment_and_salary_ok"),))


class TrainingService(DepartmentService):
    """Release a minimal training Boolean only for an approved scope."""

    silo = "training"

    def _authorized(self, request):
        if request.operation == "training_status":
            return self._employee_scope(request) and request.parameters == {}
        return request.operation == "training_complete" and self._officer_scope(request) and request.parameters == {}

    def _answer(self, request, rows):
        row = self._one_row(rows)
        if row is None:
            return RetrievalReply("abstain", request.operation, reason="evidence_unavailable")
        complete = row["fields"].get("training_complete")
        if type(complete) is not bool:
            raise ValueError("Invalid training fields.")
        fact = "training_status" if request.operation == "training_status" else "training_complete"
        return RetrievalReply("answer", request.operation, complete,
                              (evidence("training", row["document_id"], fact),))


class FinanceService(DepartmentService):
    """Release an approved budget Boolean or approved precomputed certificate."""

    silo = "finance"

    def _authorized(self, request):
        if request.operation == "budget_available":
            return self._officer_scope(request) and request.parameters == {}
        return (request.operation == "eligibility_certificate" and self._officer_scope(request)
                and set(request.parameters) == {"program_id"}
                and request.parameters.get("program_id") in {"P07", "P15"})

    def _answer(self, request, rows):
        row = self._one_row(rows)
        if row is None:
            return RetrievalReply("abstain", request.operation, reason="evidence_unavailable")
        fields = row["fields"]
        if request.operation == "budget_available":
            available = fields.get("budget_available")
            if type(available) is not bool:
                raise ValueError("Invalid finance fields.")
            return RetrievalReply("answer", request.operation, available,
                                  (evidence("finance", row["document_id"], "budget_available"),))
        certificate = fields.get("certificates", {}).get(request.parameters["program_id"])
        if certificate is None:
            return RetrievalReply("abstain", request.operation, reason="evidence_unavailable")
        if (type(certificate) is not dict or set(certificate) != {"policy_version", "eligible"}
                or certificate.get("policy_version") != POLICY_VERSION or type(certificate.get("eligible")) is not bool):
            raise ValueError("Invalid certificate.")
        pid = request.parameters["program_id"]
        return RetrievalReply("answer", request.operation, certificate["eligible"],
                              (evidence("finance", row["document_id"], f"certificate:{pid}"),))


class PolicyService(DepartmentService):
    """Read public policy only after a valid public-policy scope check."""

    silo = "policy"

    def _authorized(self, request):
        return (request.operation == "public_policy" and self._context_allowed(request)
                and request.purpose in {"public_policy", "benefits_assessment"} and request.target_id is None
                and set(request.parameters) == {"program_id"} and _valid_program(request.parameters["program_id"]))

    def _answer(self, request, rows):
        programs = json.loads((self.data_dir / "public/programs.json").read_text(encoding="utf-8"))
        pid = request.parameters["program_id"]
        matches = [row for row in programs if row.get("program_id") == pid]
        if len(matches) != 1:
            return RetrievalReply("abstain", request.operation, reason="evidence_unavailable")
        row, fields = matches[0], matches[0].get("fields")
        if (type(fields) is not dict or row.get("document_id") != f"policy:{pid}"
                or fields.get("salary_band_max") != int(pid[1:])
                or fields.get("requires") != ["employment_active", "training_complete", "budget_available"]
                or fields.get("policy_version") != POLICY_VERSION):
            raise ValueError("Invalid public policy.")
        value = {"program_id": pid, "salary_band_max": fields["salary_band_max"],
                 "requires": ["active employment", "completed training", "available budget"]}
        return RetrievalReply("answer", request.operation, value,
                              (evidence("policy", row["document_id"], "program_rule"),))
