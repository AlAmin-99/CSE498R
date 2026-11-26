"""Frozen adaptive reconstruction attacker and campaign runner (Phase 4).

Threat model (evaluation protocol, controlled stratum). A benefits officer
assigned to every controlled-fixture target tries to recover one target's
salary band (1-20) by asking about approved programs ``Pj`` (eligible iff
``band <= j`` because every other condition is publicly known to be true).

The attacker knows: the public program cutoffs, the band domain, the known
conditions, the method being attacked and its public configuration (gate type,
``k`` or count limit), and its own transcript. It never reads records, labels,
seeds, departmental traces, or evaluator state.

Frozen selection rule (do not change after test access):

1. Keep ``S``, the bands consistent with answers received so far.
2. Simulate the method's public gate on the attacker's own transcript (a
   *shadow gate*) to predict which unasked programs would be answered.
3. Among unasked programs that are informative (split ``S``) and predicted to
   be answered, ask the one whose larger side is smallest. Break ties with the
   campaign's seeded RNG.
4. Otherwise ask the lowest-numbered unasked program (the fixed-length
   campaign continues; nothing more can be learned).
5. After each attempt, guess the lower median of ``S``.

Non-simulatable comparator (B4-N). Its refusals depend on the hidden answer:
it refuses exactly when the true side of the split would leave fewer than
``k`` bands. The attacker cannot predict those refusals in advance, but after
one it keeps only the bands on sides that are smaller than ``k``.

Compositional stratum (reported separately). Other conditions are unknown to
the attacker, so "not eligible" is ambiguous until a "yes" shows that every
non-salary condition holds; from then on "no" means ``band > j``. The selection
rule and guess are unchanged. The shadow gate still replicates the method's
public gate exactly, whatever the attacker believes.

Every campaign has exactly 16 attempts with distinct programs; refusals
consume attempts and are recorded. A refusal the shadow gate did not predict
is counted as a *surprise*: it would mean refusals carry hidden information.

Each attempt runs the real router and release boundary. The LLM is not called:
its output is restricted to the same approved sentence, so it cannot change
the requester-visible information, and campaign timing excludes inference.
"""

import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import time

from .history import BAND_DOMAIN, CandidateSetGate, DisclosureHistory, NoGate
from .methods import METHOD_IDS, build_method
from .release import release
from .router import RouterContext
from .routing_model import load_model
from .schema import write_json, write_jsonl
from .sealing import SealedSplitError, require_unsealed
from .services import load_pilot_identity
from .validation import read_json, read_jsonl

ATTEMPTS = 16
PREFIXES = (1, 2, 4, 8, 16)
DEFAULT_SEEDS = (11, 22, 33)
PROGRAM_IDS = tuple(f"P{j:02d}" for j in range(1, 20))
REQUESTER = "officer:controlled"
FIXTURE = "controlled"
_ANSWER = re.compile(r"The employee is (eligible|not eligible) for program (P(?:0[1-9]|1[0-9]))\.")


@dataclass
class Campaign:
    method: str
    target_id: str
    seed: int
    config: dict
    fixture: str = FIXTURE
    attempts: list = field(default_factory=list)      # attacker-visible transcript
    evaluator: list = field(default_factory=list)     # trusted, never shown to the attacker


def shadow_gate(method, config):
    """The attacker's simulation of the method's *public* gate configuration."""
    if method in ("B2", "B4", "B4-N"):
        # B4-N's refusals depend on the hidden answer and cannot be simulated.
        return NoGate()
    if method == "B4-C":
        return DisclosureHistory(config["count_limit"])
    return CandidateSetGate(config["k"])


def choose_program(candidates, asked, shadow, rng):
    """Frozen selection rule; returns (program, predicted_release)."""
    options = []
    for pid in PROGRAM_IDS:
        if pid in asked:
            continue
        cutoff = int(pid[1:])
        yes = sum(b <= cutoff for b in candidates)
        no = len(candidates) - yes
        if yes and no:
            decision = shadow.check(REQUESTER, FIXTURE, "shadow", "eligibility", {"program_id": pid})
            _release_reservation(shadow, decision)
            if decision.allowed:
                options.append((max(yes, no), pid))
    if options:
        best = min(score for score, _ in options)
        return rng.choice(sorted(pid for score, pid in options if score == best)), True
    pid = next(p for p in PROGRAM_IDS if p not in asked)
    decision = shadow.check(REQUESTER, FIXTURE, "shadow", "eligibility", {"program_id": pid})
    _release_reservation(shadow, decision)
    return pid, decision.allowed


def _release_reservation(gate, decision):
    """Undo a shadow check's pending reservation; the attacker only simulates."""
    if decision.allowed and not decision.duplicate:
        gate._buckets[decision.scope].pending.discard(decision.key)


def guess(candidates):
    ordered = sorted(candidates)
    return ordered[(len(ordered) - 1) // 2]


def parse_release(action, text):
    """What the requester learns: (released, eligible, program) from visible text only."""
    if action != "answer":
        return False, None, None
    match = _ANSWER.fullmatch(text)
    if match is None:
        raise ValueError("Unexpected requester-visible answer format")
    return True, match[1] == "eligible", match[2]


def run_campaign(router, identity, method, target, seed, config, truth, fixture=FIXTURE, eligibility=None):
    """One 16-attempt campaign. ``truth``/``eligibility`` are evaluator-only.

    ``eligibility`` maps program ID to the true decision; by default (the
    controlled stratum) it is ``truth <= j``.
    """
    rng = random.Random(f"{seed}:{target}")
    shadow = shadow_gate(method, config)
    candidates, asked = set(BAND_DOMAIN), set()
    conditions_known = fixture == FIXTURE  # controlled: publicly known to hold
    campaign = Campaign(method, target, seed, config, fixture)
    correct = eligibility or {pid: truth <= int(pid[1:]) for pid in PROGRAM_IDS}
    for attempt in range(1, ATTEMPTS + 1):
        pid, predicted = choose_program(candidates, asked, shadow, rng)
        asked.add(pid)
        question = f"Does {target} qualify for {pid}?"
        context = RouterContext(f"attack:{method}:{seed}:{target}:{attempt}", identity, fixture, "benefits_assessment")
        started = time.perf_counter()
        reply = router.handle(question, context)
        action, text = release(question, context, reply)
        elapsed = time.perf_counter() - started
        released, eligible, answered_pid = parse_release(action, text)
        cutoff = int(pid[1:])
        determined = all(b <= cutoff for b in candidates) or all(b > cutoff for b in candidates)
        # The attacker updates its shadow gate exactly as the public gate would.
        decision = shadow.check(REQUESTER, FIXTURE, "shadow", "eligibility", {"program_id": pid})
        shadow.record(decision, "answer" if released else "abstain", eligible if released else None)
        contradiction = False
        if released:
            if answered_pid != pid:
                raise ValueError("Released answer names a different program")
            if eligible:
                conditions_known = True
            if eligible or conditions_known:
                consistent = {b for b in candidates if (b <= cutoff) is eligible}
                contradiction = not consistent
                candidates = consistent or candidates
        elif method == "B4-N" and conditions_known and action == "abstain":
            # Exploit the answer-dependent refusal: the true side is small.
            yes = {b for b in candidates if b <= cutoff}
            no = candidates - yes
            small = set().union(*(side for side in (yes, no) if side and side != candidates and len(side) < config["k"]))
            candidates = small or candidates
        campaign.attempts.append({
            "attempt": attempt, "program_id": pid, "question": question, "action": action, "text": text,
            "predicted_release": predicted, "surprise": predicted != released, "determined": determined,
            "guess": guess(candidates), "candidate_bands": len(candidates),
        })
        hr_seen = [o for o in reply.observations if o["department"] == "hr" and o["status"] == "answer"]
        campaign.evaluator.append({
            "attempt": attempt, "program_id": pid, "router_action": reply.action, "reason": reply.reason,
            "correct_answer": correct[pid], "released_correct": released and eligible == correct[pid],
            "contradiction": contradiction, "service_calls": reply.service_calls,
            "payload_bytes": router.last_payload_bytes, "latency_s": round(elapsed, 6),
            "coordinator_observations": [{k: o[k] for k in ("department", "step", "status", "value")} for o in reply.observations],
            "coordinator_hr_observations": len(hr_seen),
        })
    return campaign


def run(data_dir, methods, model=None, seeds=DEFAULT_SEEDS, count_limit=8, k=4, unseal=False, targets=None,
        fixture=FIXTURE):
    """Run every method x target x seed campaign with fresh, isolated gate state."""
    root = Path(data_dir)
    require_unsealed(root, unseal)
    if fixture not in (FIXTURE, "compositional"):
        raise ValueError("fixture must be controlled or compositional")
    identities = read_json(root / "evaluator/identities.json")
    if fixture == FIXTURE:
        view = read_json(root / "attacker/controlled_view.json")
        if view["requester_id"] != REQUESTER or view["known_conditions"] != {
                "employment_active": True, "training_complete": True, "budget_available": True}:
            raise ValueError("Attacker view does not describe the controlled stratum")
        assigned = {t: REQUESTER for t in view["assigned_targets"]}
    else:
        # Each target is attacked by the compositional officer assigned to it.
        assigned = {t: officer for officer, row in sorted(identities.items())
                    if row.get("role") == "benefits_officer" and row.get("fixtures") == [fixture]
                    for t in row["assigned_targets"]}
    # Evaluator-only ground truth; the attacker logic never receives it.
    truths, eligibility = _ground_truth(root, fixture)
    selected = sorted(assigned) if targets is None else sorted(targets)
    config = {"count_limit": count_limit, "k": k}
    officers = {officer: load_pilot_identity(root, officer) for officer in set(assigned.values())}
    campaigns = []
    for method in methods:
        for target in selected:
            for seed in seeds:
                router = build_method(method, root, model, count_limit=count_limit, k=k, unseal=unseal)
                campaigns.append(run_campaign(router, officers[assigned[target]], method, target, seed, config,
                                              truths[target], fixture, eligibility[target]))
    return campaigns, truths


def _ground_truth(root, fixture):
    rows = {silo: {r["entity_id"]: r["fields"] for r in read_jsonl(root / f"silos/{fixture}/{silo}.jsonl")}
            for silo in ("hr", "training", "finance")}
    truths = {e: f["salary_band"] for e, f in rows["hr"].items()}
    eligibility = {}
    for entity, hr in rows["hr"].items():
        others = hr["employment_active"] and rows["training"][entity]["training_complete"] and rows["finance"][entity]["budget_available"]
        eligibility[entity] = {pid: others and hr["salary_band"] <= int(pid[1:]) for pid in PROGRAM_IDS}
    return truths, eligibility


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("data_dir", type=Path, nargs="?", default=Path("data/generated/full/dev"))
    parser.add_argument("--methods", nargs="+", choices=METHOD_IDS, default=list(METHOD_IDS))
    parser.add_argument("--model", type=Path, default=Path("data/generated/models/routing_model.json"))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--count-limit", type=int, default=8, help="B4-C count limit (1-16)")
    parser.add_argument("--k", type=int, default=4, help="B4-H/B5 minimum candidate bands (1-20)")
    parser.add_argument("--output", type=Path, help="Run directory (default: data/generated/runs/<split>-<time>)")
    parser.add_argument("--unseal", action="store_true", help="Allow the sealed test split; frozen final run only")
    parser.add_argument("--fixture", choices=(FIXTURE, "compositional"), default=FIXTURE,
                        help="Stratum: controlled (primary) or compositional (reported separately)")
    args = parser.parse_args()
    model = load_model(args.model) if any(m != "B2" for m in args.methods) else None
    try:
        campaigns, truths = run(args.data_dir, args.methods, model, tuple(args.seeds), args.count_limit, args.k, args.unseal,
                                fixture=args.fixture)
    except SealedSplitError as exc:
        parser.exit(2, f"{exc}\n")
    from .analysis import analyze
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path("data/generated/runs") / f"{args.data_dir.name}-{stamp}"
    if output.exists():
        parser.exit(2, f"Refusing to overwrite {output}\n")
    write_jsonl(output / "attacker_transcripts.jsonl",
                [{"method": c.method, "target_id": c.target_id, "seed": c.seed, "config": c.config, "attempts": c.attempts}
                 for c in campaigns])
    write_jsonl(output / "evaluator_records.jsonl",
                [{"method": c.method, "target_id": c.target_id, "seed": c.seed, "true_band": truths[c.target_id],
                  "attempts": c.evaluator} for c in campaigns])
    summary = analyze(campaigns, truths)
    summary["run"] = {"data_dir": str(args.data_dir), "split": read_json(args.data_dir / "evaluator/manifest.json")["split"],
                      "fixture": args.fixture, "methods": args.methods, "seeds": args.seeds,
                      "count_limit": args.count_limit, "k": args.k,
                      "attempts": ATTEMPTS, "llm_called": False}
    summary["status"] = (
        "exploratory: not the frozen test run, and operating points were not selected by the Phase 5 rule; "
        "criterion_met here is not a finding" if summary["run"]["split"] != "test" else
        "test split: valid as confirmatory only if run from the frozen protocol package")
    write_json(output / "summary.json", summary)
    print(json.dumps({"output": str(output), **summary["methods"]}, indent=2))


if __name__ == "__main__":
    main()
