"""Learned department-relevance model and the routing orders built on it.

The B4 comparator is a *PAFR-setting adaptation inspired by RAGRoute*, not a
reproduction of its classifier: for each public program it learns, from the
training split only, how often each department alone completes a sufficient
"not eligible" plan and how often a certificate plan exists. Labels come from
the independent gold oracle's approved evidence plans, never from a router.
Features are public program identifiers only; no private embeddings or record
summaries are stored in the model.

Routing orders (all start with the public rule; see ``router.RoutingPolicy``):

``broadcast_routing``   (B2) request every step, then pick one sufficient plan.
``relevance_routing``   (B4, B4-C, B4-H) order to minimize expected calls.
``exposure_routing``    (B5) certificate, then non-salary departments by
                        learned relevance, HR (the salary-dependent fact) last,
                        so the coordinator observes salary information only
                        when no other plan suffices.
"""

import argparse
import json
from pathlib import Path

from .gold import reference_label
from .router import STATIC_STEPS, RoutingPolicy
from .schema import checksum, write_json
from .validation import read_json, read_jsonl

MODEL_NAME = "pafr-relevance-v1"
CONDITIONS = ("hr", "training", "finance")
PROGRAMS = tuple(f"P{j:02d}" for j in range(1, 20))


def fit(train_dir, fixture="compositional"):
    """Fit per-program department relevance on a training split directory."""
    root = Path(train_dir)
    manifest = read_json(root / "evaluator/manifest.json")
    if manifest.get("split") != "train":
        raise ValueError("Routing may be fitted only on the training split")
    identities = read_json(root / "evaluator/identities.json")
    programs = {p["program_id"]: p for p in read_json(root / "public/programs.json")}
    records = [r for silo in CONDITIONS for r in read_jsonl(root / f"silos/{fixture}/{silo}.jsonl")]
    entities = sorted({r["entity_id"] for r in records})
    officers = {}
    for requester, row in identities.items():
        if row.get("role") == "benefits_officer" and fixture in row.get("fixtures", []):
            for entity in row.get("assigned_targets", []):
                officers.setdefault(entity, requester)
    learned = {}
    for pid in PROGRAMS:
        decisive = dict.fromkeys(CONDITIONS, 0)
        certificates = 0
        for entity in entities:
            case = {"case_id": f"fit:{entity}:{pid}", "requester_id": officers[entity], "fixture": fixture,
                    "purpose": "benefits_assessment", "operation": "eligibility", "target_id": entity,
                    "parameters": {"program_id": pid}}
            label = reference_label(case, identities, programs, records)
            for plan in label["evidence_plans"]:
                facts = {unit["fact"] for unit in plan}
                if len(plan) == 2:
                    other = next(unit for unit in plan if unit["silo"] != "policy")
                    if other["fact"].startswith("certificate:"):
                        certificates += 1
                    else:
                        decisive[other["silo"]] += 1
                elif any(f.startswith("certificate:") for f in facts):
                    certificates += 1
        n = len(entities)
        learned[pid] = {"decisive_rate": {s: round(decisive[s] / n, 6) for s in CONDITIONS},
                        "certificate_rate": round(certificates / n, 6)}
    return {"model": MODEL_NAME, "trained_split": "train", "fixture": fixture, "entities": len(entities),
            "train_manifest_sha256": checksum(root / "evaluator/manifest.json"), "programs": learned}


def load_model(path):
    model = read_json(Path(path))
    if model.get("model") != MODEL_NAME or model.get("trained_split") != "train" or set(model["programs"]) != set(PROGRAMS):
        raise ValueError("Not a training-split PAFR routing model")
    return model


def _condition_order(model, pid, exclude=()):
    rates = model["programs"][pid]["decisive_rate"]
    pool = [s for s in CONDITIONS if s not in exclude]
    # Most likely decisive first; fixed department order breaks ties.
    return tuple(sorted(pool, key=lambda s: (-rates[s], CONDITIONS.index(s))))


def _expected_calls(model, pid, order):
    rates = model["programs"][pid]["decisive_rate"]
    expected, reach = 0.0, 1.0
    for silo in order:
        expected += reach
        reach *= 1.0 - rates[silo]
    return expected


def relevance_steps(model, pid):
    order = _condition_order(model, pid)
    rate = model["programs"][pid]["certificate_rate"]
    # Certificate first only when it lowers expected calls: 1 + (1-r)E < E.
    if rate * _expected_calls(model, pid, order) > 1.0:
        return ("certificate", *order)
    return (*order, "certificate")


def exposure_steps(model, pid):
    return ("certificate", *_condition_order(model, pid, exclude=("hr",)), "hr")


def broadcast_routing():
    return RoutingPolicy("broadcast", lambda pid: STATIC_STEPS, broadcast=True)


def relevance_routing(model):
    return RoutingPolicy("relevance", lambda pid: relevance_steps(model, pid))


def exposure_routing(model):
    return RoutingPolicy("exposure", lambda pid: exposure_steps(model, pid))


def main():
    parser = argparse.ArgumentParser(description="Fit the PAFR routing model on a training split")
    parser.add_argument("train_dir", type=Path, nargs="?", default=Path("data/generated/full/train"))
    parser.add_argument("--output", type=Path, default=Path("data/generated/models/routing_model.json"))
    args = parser.parse_args()
    try:
        model = fit(args.train_dir)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    write_json(args.output, model)
    summary = {pid: {"B4": relevance_steps(model, pid), "B5": exposure_steps(model, pid)} for pid in ("P01", "P07", "P12", "P15", "P19")}
    print(json.dumps({"output": str(args.output), "entities": model["entities"], "example_orders": summary}, indent=2))


if __name__ == "__main__":
    main()
