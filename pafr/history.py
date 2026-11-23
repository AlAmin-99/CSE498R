"""Disclosure-history release gates for protected eligibility decisions.

Every gate is keyed by one trusted requester, fixture, and target, and sees
only the requester-visible outcome of earlier requests. No raw evidence is
stored. Three gates share one interface (``check`` before routing, ``record``
after it, ``snapshot`` for trusted diagnostics):

``NoGate``
    Never withholds (methods B2 and B4).
``DisclosureHistory``
    Count limit on distinct released decisions (method B4-C).
``CandidateSetGate``
    PAFR's gate (methods B4-H and B5). It tracks which salary bands remain
    consistent with the eligibility answers this requester has already
    received about this target, and releases a new program decision only if
    *either* possible answer would still leave at least ``k`` bands. The
    decision depends only on the requester's own transcript and the public
    cutoffs, so a refusal reveals nothing the requester could not compute.

Optional ``state_path`` persistence keeps state across sessions. Only the
trusted harness may delete the file; question text and refusals cannot reset
it. Gates are process-local and lock-protected; the file is not a database
and is not safe for concurrent processes. None of this is a cross-user or
coordinator-wide defense.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from threading import RLock

BAND_DOMAIN = tuple(range(1, 21))  # public salary-band domain


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


class ReleaseGate:
    """Common interface; subclasses define ``_allowed`` and ``_released``."""

    _needs_answer = False

    def __init__(self, state_path=None):
        self._lock = RLock()
        self._buckets = {}
        self.state_path = Path(state_path) if state_path is not None else None
        if self.state_path is not None and self.state_path.exists():
            self._load()

    def check(self, requester_id, fixture, target_id, operation, parameters):
        """Atomically decide and reserve a proposed protected decision."""
        scope = _scope(requester_id, fixture, target_id)
        key = _key(operation, parameters)
        with self._lock:
            bucket = self._buckets.setdefault(scope, self._new_bucket())
            duplicate = key in bucket.released or key in bucket.pending
            allowed = duplicate or self._allowed(bucket, key)
            if allowed and not duplicate:
                bucket.pending.add(key)
            return GateDecision(allowed, scope, key, duplicate)

    def record(self, decision, action, answer=None):
        """Record one attempted decision after routing.

        Only an actually released ``answer`` changes what the requester knows.
        Withheld and unavailable requests remain attempts so they cannot reset
        state or disappear from trusted diagnostics.
        """
        if not isinstance(decision, GateDecision) or action not in {"answer", "abstain", "deny"}:
            raise ValueError("Invalid history event")
        if answer is not None and type(answer) is not bool:
            raise ValueError("A released eligibility decision must be a Boolean")
        if action == "answer" and decision.allowed and self._needs_answer and type(answer) is not bool:
            raise ValueError("This gate needs the released Boolean decision")
        with self._lock:
            bucket = self._buckets.setdefault(decision.scope, self._new_bucket())
            bucket.attempts += 1
            if not decision.allowed:
                bucket.withheld += 1
            else:
                if not decision.duplicate:
                    bucket.pending.discard(decision.key)
                if action == "answer" and decision.key not in bucket.released:
                    bucket.released.add(decision.key)
                    self._released(bucket, decision.key, answer)
            self._save()

    def snapshot(self, requester_id, fixture, target_id):
        """Bounded trusted diagnostics without answer values or evidence."""
        scope = _scope(requester_id, fixture, target_id)
        with self._lock:
            bucket = self._buckets.get(scope, self._new_bucket())
            return {"released_distinct_decisions": len(bucket.released), "attempts": bucket.attempts,
                    "withheld": bucket.withheld, **self._extra_snapshot(bucket)}

    # Subclass hooks ---------------------------------------------------
    def _new_bucket(self):
        return _Bucket()

    def _allowed(self, bucket, key):
        raise NotImplementedError

    def _released(self, bucket, key, answer):
        pass

    def _extra_snapshot(self, bucket):
        return {}

    def _config(self):
        return {}

    # Persistence ------------------------------------------------------
    def _save(self):
        if self.state_path is None:
            return
        state = {"gate": type(self).__name__, "config": self._config(), "buckets": [
            {"scope": [s.requester_id, s.fixture, s.target_id],
             "released": [_key_json(k) for k in sorted(b.released, key=lambda k: (k.operation, k.parameters))],
             "attempts": b.attempts, "withheld": b.withheld, **self._bucket_state(b)}
            for s, b in sorted(self._buckets.items(), key=lambda item: (item[0].requester_id, item[0].fixture, item[0].target_id))
        ]}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _load(self):
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("gate") != type(self).__name__ or state.get("config") != self._config():
            raise ValueError("History file belongs to a different gate or configuration")
        for row in state["buckets"]:
            bucket = self._new_bucket()
            bucket.released = {_key(*_unkey_json(k)) for k in row["released"]}
            bucket.attempts, bucket.withheld = int(row["attempts"]), int(row["withheld"])
            self._restore_bucket(bucket, row)
            self._buckets[_scope(*row["scope"])] = bucket

    def _bucket_state(self, bucket):
        return {}

    def _restore_bucket(self, bucket, row):
        pass


@dataclass
class _Bucket:
    released: set[DecisionKey] = field(default_factory=set)
    pending: set[DecisionKey] = field(default_factory=set)
    attempts: int = 0
    withheld: int = 0
    candidates: frozenset[int] = frozenset(BAND_DOMAIN)


class NoGate(ReleaseGate):
    """Records attempts but never withholds (unbudgeted reference methods)."""

    def _allowed(self, bucket, key):
        return True


class DisclosureHistory(ReleaseGate):
    """Count limit on distinct released decisions per requester and target."""

    def __init__(self, max_distinct_decisions=16, state_path=None):
        if type(max_distinct_decisions) is not int or not 1 <= max_distinct_decisions <= 16:
            raise ValueError("max_distinct_decisions must be an integer from 1 to 16")
        self.max_distinct_decisions = max_distinct_decisions
        super().__init__(state_path)

    def _allowed(self, bucket, key):
        return len(bucket.released | bucket.pending) < self.max_distinct_decisions

    def _extra_snapshot(self, bucket):
        return {"limit": self.max_distinct_decisions}

    def _config(self):
        return {"max_distinct_decisions": self.max_distinct_decisions}


class CandidateSetGate(ReleaseGate):
    """Withhold a program decision whose worst-case answer leaves < k bands.

    Requester model: the public rule ``Pj`` requires ``salary_band <= j``.
    The gate assumes, conservatively, that the requester knows every other
    condition is true, so "eligible" means ``band <= j`` and "not eligible"
    means ``band > j``. If a released answer contradicts the tracked set (only
    possible when another condition actually failed), that answer is treated
    as carrying no salary information under this model.

    A new decision for ``Pj`` is released if each outcome that is still
    possible leaves at least ``k`` candidate bands. An outcome already ruled
    out by earlier answers reveals nothing new, so a determined answer is
    always released. ``k = 1`` never withholds.

    Only one pending protected decision per scope is allowed at a time, so
    concurrent requests cannot both pass the worst-case check.
    """

    _needs_answer = True

    def __init__(self, k=4, state_path=None):
        if type(k) is not int or not 1 <= k <= len(BAND_DOMAIN):
            raise ValueError("k must be an integer from 1 to 20")
        self.k = k
        super().__init__(state_path)

    def _allowed(self, bucket, key):
        if bucket.pending:
            return False
        cutoff = _cutoff(key)
        yes = {b for b in bucket.candidates if b <= cutoff}
        no = bucket.candidates - yes
        return all(len(outcome) >= self.k for outcome in (yes, no) if outcome)

    def _released(self, bucket, key, answer):
        cutoff = _cutoff(key)
        consistent = frozenset(b for b in bucket.candidates if (b <= cutoff) is answer)
        if consistent:
            bucket.candidates = consistent

    def _extra_snapshot(self, bucket):
        return {"k": self.k, "candidate_bands": len(bucket.candidates)}

    def _config(self):
        return {"k": self.k}

    def _bucket_state(self, bucket):
        return {"candidates": sorted(bucket.candidates)}

    def _restore_bucket(self, bucket, row):
        candidates = frozenset(int(b) for b in row["candidates"])
        if not candidates or not candidates <= set(BAND_DOMAIN):
            raise ValueError("Invalid stored candidate set")
        bucket.candidates = candidates


def _cutoff(key):
    program = dict(key.parameters)["program_id"]
    if len(program) != 3 or program[0] != "P" or not program[1:].isdigit() or not 1 <= int(program[1:]) <= 19:
        raise ValueError("Unknown program")
    return int(program[1:])


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


def _key_json(key):
    return [key.operation, dict(key.parameters)]


def _unkey_json(value):
    operation, parameters = value
    return operation, dict(parameters)
