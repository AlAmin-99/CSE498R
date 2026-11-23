"""End-to-end check: router and release boundary against independent gold labels.

Every labelled pilot case is run through ``FederatedRouter`` and ``release``
with a fresh disclosure history (ordinary task cases must not prime one
another). Results are compared with ``evaluator/gold.jsonl``, which the
independent rules in ``gold.py`` produced. Evaluator scenario overlays are
applied to a temporary copy of the corpus; the base corpus is never modified.

Two question modes are reported separately:

``structured``
    The case's labelled operation, target, and program are turned into the
    planner's canonical wording. This checks binding, authorization, routing,
    and evidence selection independently of natural-language coverage.
``natural``
    The case's original question text is used unchanged. This additionally
    measures what the constrained allowlist planner accepts.

This is a functional correctness check on training-split pilot data, not a
privacy evaluation or a model-accuracy measurement. No LLM is called.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile

from .history import DisclosureHistory
from .release import release
from .methods import METHOD_IDS, build_method
from .router import FederatedRouter, RouterContext
from .routing_model import load_model
from .sealing import SealedSplitError, require_unsealed
from .services import load_pilot_identity
from .validation import case_records, read_json, read_jsonl

MODES = ("structured", "natural")
# The self-service operation names its evidence fact differently from the
# officer operation, but both release the same training_complete field.
_FACT_ALIASES = {"training_status": "training_complete"}


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    family: str
    mode: str
    expected_action: str
    actual_action: str
    released_action: str
    answer_ok: bool
    evidence_ok: bool
    service_calls: int
    note: str = ""
    hr_observations: int = 0

    @property
    def passed(self):
        return (self.expected_action == self.actual_action == self.released_action
                and self.answer_ok and self.evidence_ok)

    @property
    def withheld(self):
        """An answerable case withheld by a disclosure gate: lost yield, not an error."""
        return (self.expected_action == "answer" and self.actual_action == "abstain"
                and self.released_action == "abstain" and self.note == "exposure_limit")


def canonical_question(case):
    """Planner wording for a labelled case; ``None`` for unsupported operations."""
    op, params = case["operation"], case["parameters"]
    if op == "training_status" and params == {}:
        return "Is my training complete?"
    if op == "public_policy" and set(params) == {"program_id"}:
        return f"What are the rules for {params['program_id']}?"
    if op == "eligibility" and set(params) == {"program_id"} and type(case["target_id"]) is str:
        return f"Does {case['target_id']} qualify for {params['program_id']}?"
    return None


def evaluate(data_dir, modes=MODES, unseal=False, router_factory=None):
    """Return a list of ``CaseResult`` for every case and requested mode.

    A sealed split is refused unless ``unseal`` is explicitly true.
    ``router_factory(view)`` builds a fresh router (and gate state) per case;
    by default the static pilot router with a count gate is used.
    """
    root = Path(data_dir)
    require_unsealed(root, unseal)
    cases = read_jsonl(root / "evaluator/cases.jsonl")
    gold = {row["case_id"]: row for row in read_jsonl(root / "evaluator/gold.jsonl")}
    scenarios = {row["scenario_id"]: row for row in read_jsonl(root / "evaluator/scenarios.jsonl")}
    records = _base_records(root)
    results = []
    with tempfile.TemporaryDirectory(prefix="pafr-e2e-") as scratch:
        for case in cases:
            scenario = scenarios.get(case["scenario_id"]) if case["scenario_id"] else None
            view = _scenario_view(root, Path(scratch) / "view", case_records(records, scenario)) if scenario else root
            for mode in modes:
                results.append(_run_case(view, case, gold[case["case_id"]], mode, unseal, router_factory))
    return results


def summarize(results):
    """Aggregate pass counts per mode and per family, plus the confusion matrix."""
    summary = {}
    for mode in sorted({r.mode for r in results}):
        rows = [r for r in results if r.mode == mode]
        families = {}
        for family in sorted({r.family for r in rows}):
            fam = [r for r in rows if r.family == family]
            families[family] = {"passed": sum(r.passed for r in fam), "withheld": sum(r.withheld for r in fam),
                                "total": len(fam)}
        confusion = Counter(f"{r.expected_action}->{r.released_action}" for r in rows)
        summary[mode] = {
            "passed": sum(r.passed for r in rows),
            "withheld": sum(r.withheld for r in rows),
            "errors": sum(not r.passed and not r.withheld for r in rows),
            "total": len(rows),
            "service_calls": sum(r.service_calls for r in rows),
            "coordinator_hr_observations": sum(r.hr_observations for r in rows),
            "families": families,
            "confusion": dict(sorted(confusion.items())),
        }
    return summary


def _run_case(view, case, expected, mode, unseal=False, router_factory=None):
    question = case["question"] if mode == "natural" else canonical_question(case)
    identity = load_pilot_identity(view, case["requester_id"])
    context = RouterContext(f"e2e:{case['case_id']}:{mode}", identity, case["fixture"], case["purpose"])
    if question is None:
        actual_action, answer, evidence, calls, hr_seen = "deny", None, (), 0, 0
        released_action = "deny"
        note = "no supported wording for this operation"
    else:
        router = (router_factory(view) if router_factory is not None
                  else FederatedRouter(view, history=DisclosureHistory(), unseal=unseal))
        reply = router.handle(question, context)
        actual_action, answer, evidence, calls = reply.action, reply.answer, reply.evidence, reply.service_calls
        hr_seen = sum(o["department"] == "hr" and o["status"] == "answer" for o in reply.observations)
        released_action, _ = release(question, context, reply)
        note = reply.reason or ""
    answer_ok = actual_action != "answer" or _answer_matches(case, expected, answer)
    evidence_ok = actual_action != "answer" or _evidence_matches(expected, evidence)
    return CaseResult(case["case_id"], case["family"], mode, expected["action"], actual_action,
                      released_action, answer_ok, evidence_ok, calls, note, hr_seen)


def _answer_matches(case, expected, answer):
    if case["operation"] == "public_policy":
        # Gold stores raw policy fields; the service releases a display form.
        return type(answer) is dict and type(expected["answer"]) is dict and (
            answer.get("program_id") == case["parameters"]["program_id"]
            and answer.get("salary_band_max") == expected["answer"].get("salary_band_max"))
    return answer is expected["answer"] if type(answer) is bool else answer == expected["answer"]


def _evidence_matches(expected, evidence):
    """The released evidence must equal one of the gold sufficient plans."""
    used = frozenset(_unit(item) for item in evidence)
    return any(used == frozenset(_unit(item) for item in plan) for plan in expected["evidence_plans"])


def _unit(item):
    fact = _FACT_ALIASES.get(item["fact"], item["fact"])
    return item["silo"], item["document_id"], fact


def _base_records(root):
    records = []
    for path in sorted((root / "silos").glob("*/*.jsonl")):
        records.extend(read_jsonl(path))
    return records


def _scenario_view(root, view, records):
    """Write a disposable corpus copy holding one case's overlaid records."""
    if view.exists():
        shutil.rmtree(view)
    shutil.copytree(root / "public", view / "public")
    (view / "evaluator").mkdir(parents=True)
    shutil.copy2(root / "evaluator/identities.json", view / "evaluator/identities.json")
    grouped = {}
    for record in records:
        grouped.setdefault((record["fixture"], record["silo"]), []).append(record)
    for fixture_dir in (root / "silos").iterdir():
        if fixture_dir.is_dir():
            for silo_file in fixture_dir.glob("*.jsonl"):
                grouped.setdefault((fixture_dir.name, silo_file.stem), [])
    for (fixture, silo), rows in grouped.items():
        path = view / "silos" / fixture / f"{silo}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    return view


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("data_dir", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[1] / "data/generated/pilot")
    parser.add_argument("--mode", choices=MODES, action="append", help="Default: both modes")
    parser.add_argument("--failures", action="store_true", help="List every failing case")
    parser.add_argument("--unseal", action="store_true",
                        help="Allow the sealed test split; only for the frozen final run")
    parser.add_argument("--method", choices=METHOD_IDS,
                        help="Protocol method (default: the static pilot router)")
    parser.add_argument("--model", type=Path, default=Path("data/generated/models/routing_model.json"),
                        help="Routing model fitted on the training split (B4, B4-C, B4-H, B5)")
    parser.add_argument("--count-limit", type=int, default=16, help="B4-C count limit (1-16)")
    parser.add_argument("--k", type=int, default=4, help="B4-H/B5 minimum candidate bands (1-20)")
    args = parser.parse_args()
    read_json(args.data_dir / "evaluator/manifest.json")  # fail early on a missing dataset
    factory = None
    if args.method is not None:
        model = load_model(args.model) if args.method != "B2" else None
        def factory(view):
            return build_method(args.method, view, model, args.count_limit, args.k, unseal=args.unseal)
    try:
        results = evaluate(args.data_dir, tuple(args.mode or MODES), unseal=args.unseal, router_factory=factory)
    except SealedSplitError as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(summarize(results), indent=2))
    if args.failures:
        for r in results:
            if not r.passed and not r.withheld:
                print(f"FAIL [{r.mode}] {r.case_id}: expected {r.expected_action}, router {r.actual_action}, "
                      f"released {r.released_action}, answer_ok={r.answer_ok}, evidence_ok={r.evidence_ok} {r.note}")
    structured = [r for r in results if r.mode == "structured"]
    return 0 if all(r.passed or r.withheld for r in structured) else 1


if __name__ == "__main__":
    raise SystemExit(main())
