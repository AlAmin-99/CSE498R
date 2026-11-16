"""In-memory disclosure history and a fail-closed eligibility release gate.

The pilot gate limits distinct released eligibility decisions for one trusted
requester, fixture, and target. It deliberately records no raw evidence or
answer values. This is a deterministic count-limit baseline, not the planned
adaptive exposure-risk model, persistent audit store, or cross-user defense.
"""

from dataclasses import dataclass, field
from threading import RLock


@dataclass(frozen=True)
class HistoryScope:
    requester_id: str
    fixture: str
    target_id: str


@dataclass(frozen=True)
class DecisionKey:
    operation: str
    parameters: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    scope: HistoryScope
    key: DecisionKey
    duplicate: bool


@dataclass
class _Bucket:
    released: set[DecisionKey] = field(default_factory=set)
    pending: set[DecisionKey] = field(default_factory=set)
    attempts: int = 0
    withheld: int = 0


class DisclosureHistory:
    """Thread-safe, process-local count gate for protected pilot decisions."""

    def __init__(self, max_distinct_decisions=16):
        if type(max_distinct_decisions) is not int or not 1 <= max_distinct_decisions <= 16:
            raise ValueError("max_distinct_decisions must be an integer from 1 to 16")
        self.max_distinct_decisions = max_distinct_decisions
        self._buckets = {}
        self._lock = RLock()

    def check(self, requester_id, fixture, target_id, operation, parameters):
        """Atomically reserve a proposed protected decision when it is allowed.

        The reservation prevents simultaneous distinct requests from both
        passing a full budget. ``record`` clears it after the router answers or
        abstains, adding it to the released set only for an actual answer.
        """
        scope = _scope(requester_id, fixture, target_id)
        key = _key(operation, parameters)
        with self._lock:
            bucket = self._buckets.setdefault(scope, _Bucket())
            duplicate = key in bucket.released or key in bucket.pending
            allowed = duplicate or len(bucket.released | bucket.pending) < self.max_distinct_decisions
            if allowed and not duplicate:
                bucket.pending.add(key)
            return GateDecision(allowed, scope, key, duplicate)

    def record(self, decision, action):
        """Record one attempted decision after routing.

        Only an actually released ``answer`` consumes a distinct-decision slot.
        Withheld and unavailable requests remain attempts so they cannot reset
        the state or disappear from trusted diagnostics.
        """
        if not isinstance(decision, GateDecision) or action not in {"answer", "abstain", "deny"}:
            raise ValueError("Invalid history event")
        with self._lock:
            bucket = self._buckets.setdefault(decision.scope, _Bucket())
            bucket.attempts += 1
            if not decision.allowed:
                bucket.withheld += 1
            else:
                if not decision.duplicate:
                    bucket.pending.discard(decision.key)
                if action == "answer":
                    bucket.released.add(decision.key)

    def snapshot(self, requester_id, fixture, target_id):
        """Return bounded trusted diagnostics without answer values or evidence."""
        scope = _scope(requester_id, fixture, target_id)
        with self._lock:
            bucket = self._buckets.get(scope, _Bucket())
            return {
                "released_distinct_decisions": len(bucket.released),
                "attempts": bucket.attempts,
                "withheld": bucket.withheld,
                "limit": self.max_distinct_decisions,
            }


def _scope(requester_id, fixture, target_id):
    if not all(type(value) is str and value for value in (requester_id, fixture, target_id)):
        raise ValueError("Invalid disclosure-history scope")
    return HistoryScope(requester_id, fixture, target_id)


def _key(operation, parameters):
    if type(operation) is not str or operation != "eligibility" or type(parameters) is not dict:
        raise ValueError("Invalid protected decision")
    if set(parameters) != {"program_id"} or type(parameters["program_id"]) is not str:
        raise ValueError("Invalid protected decision")
    return DecisionKey(operation, tuple(sorted(parameters.items())))
