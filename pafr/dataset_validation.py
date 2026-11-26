"""Validate the full three-split PAFR dataset against its declared rules.

Checks structure, split separation, sealing, checksums, attacker-view
minimality, record invariants, scenario isolation, and recomputes every gold
label with the independent oracle in ``gold.py``. For a sealed split the
report contains counts only, never label distributions.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from .dataset import (
    CAPABILITIES, CONDITION_FIELD, DENY_FAMILIES, EVIDENCE_FAMILIES, FAMILIES, SEALED_SPLITS, SPLITS,
    attacker_view, evidence_choice, expected_identities, home_officer, other_officer, programs,
)
from .gold import reference_label
from .schema import FIXTURES, INJECTION, PLANNED_SPLITS, POLICY_VERSION, SCHEMA_VERSION, SILOS, SPLIT_SEED, checksum, document_id, split_ids
from .sealing import SEAL_FILE, SEAL_TEXT
from .validation import case_records, read_json, read_jsonl, require, same

_MARKER = re.compile(r"CANARY_[0-9a-f]{24}")
_RECORD_KEYS = {"document_id", "fixture", "silo", "entity_id", "split", "version", "fields",
                "confidential_marker", "untrusted_note"}
_CASE_KEYS = {"case_id", "split", "fixture", "family", "requester_id", "purpose", "target_id",
              "operation", "parameters", "question", "scenario_id"}


def validate_dataset(directory):
    """Validate every split; return per-split summaries."""
    root = Path(directory)
    require(root.is_dir() and not root.is_symlink(), "Expected a dataset directory, not a symlink")
    require(not any(p.is_symlink() for p in root.rglob("*")), "Dataset must not contain symlinks")
    top = read_json(root / "manifest.json")
    same(sorted(top), sorted(["schema_version", "generator_version", "dataset", "split_seed", "planned_split_counts",
                              "sealed_splits", "split_manifest_sha256"]), "Top-level manifest fields changed")
    require(top["schema_version"] == SCHEMA_VERSION and top["dataset"] == "full", "Unsupported dataset schema")
    require(top["split_seed"] == SPLIT_SEED, "Split seed changed")
    same(top["planned_split_counts"], PLANNED_SPLITS, "Planned split counts changed")
    same(top["sealed_splits"], sorted(SEALED_SPLITS), "Sealed split list changed")
    same(sorted(p.name for p in root.iterdir()), sorted([*SPLITS, "manifest.json"]), "Unexpected top-level entries")
    ids = split_ids()
    seen_entities, seeds = set(), set()
    summaries = {}
    for split in SPLITS:
        directory = root / split
        require(checksum(directory / "evaluator/manifest.json") == top["split_manifest_sha256"][split],
                f"Split manifest checksum mismatch: {split}")
        summary, seed = _validate_split(directory, split, ids[split])
        require(not seen_entities & set(ids[split]), "Entity appears in more than one split")
        seen_entities |= set(ids[split])
        seeds.add(seed)
        summaries[split] = summary
    require(len(seeds) == 1, "Splits were generated with different private seeds")
    require(len(seen_entities) == sum(PLANNED_SPLITS.values()), "Split entities do not cover the planned pool")
    return summaries


def _validate_split(root, split, entities):
    entities = sorted(entities)
    n = len(entities)
    manifest = read_json(root / "evaluator/manifest.json")
    same(sorted(manifest), sorted(["schema_version", "generator_version", "dataset", "split", "sealed", "split_seed",
                                   "private_record_seed", "generated_entity_ids", "families", "counts", "sha256"]),
         "Split manifest fields changed")
    require(manifest["split"] == split and manifest["dataset"] == "full", "Manifest describes another split")
    sealed = split in SEALED_SPLITS
    require(manifest["sealed"] is sealed, "Manifest sealing flag is wrong")
    same(manifest["generated_entity_ids"], entities, "Split entities differ from the fixed split assignment")
    same(manifest["families"], list(FAMILIES), "Case families changed")
    seed = manifest["private_record_seed"]
    require(type(seed) is int and 0 <= seed < 2**128, "Invalid private seed")

    files = {"public/programs.json", "public/capabilities.json", "attacker/controlled_view.json",
             "evaluator/identities.json", "evaluator/cases.jsonl", "evaluator/gold.jsonl", "evaluator/scenarios.jsonl"}
    files.update(f"silos/{fixture}/{silo}.jsonl" for fixture in FIXTURES for silo in SILOS)
    if sealed:
        files.add(SEAL_FILE)
        require((root / SEAL_FILE).is_file(), f"Sealed split is missing its {SEAL_FILE} marker")
        require((root / SEAL_FILE).read_text(encoding="utf-8") == SEAL_TEXT, "Seal marker text changed")
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    same(sorted(actual), sorted(files | {"evaluator/manifest.json"}), "Unexpected or missing files")
    same(sorted(manifest["sha256"]), sorted(files), "Checksum manifest has unexpected paths")
    for filename in files:
        require(checksum(root / filename) == manifest["sha256"][filename], f"Checksum mismatch: {split}/{filename}")

    catalogue = read_json(root / "public/programs.json")
    same(catalogue, programs(), "Public program catalogue differs from the declared rules")
    program_map = {p["program_id"]: p for p in catalogue}
    same(read_json(root / "public/capabilities.json"), CAPABILITIES, "Capability profile changed")
    same(read_json(root / "attacker/controlled_view.json"), attacker_view(split, entities),
         "Attacker view contains hidden values or unexpected fields")
    identities = read_json(root / "evaluator/identities.json")
    same(identities, expected_identities(entities), "Trusted identity fixtures changed")

    records, by_key = [], {}
    for fixture in FIXTURES:
        for silo in SILOS:
            rows = read_jsonl(root / f"silos/{fixture}/{silo}.jsonl")
            require(len(rows) == n, "Wrong record count")
            for row in rows:
                _check_record(row, fixture, silo, split, entities)
                key = fixture, row["entity_id"], silo
                require(key not in by_key, "Duplicate private record")
                by_key[key] = row
                records.append(row)
    require(len({r["confidential_marker"] for r in records}) == len(records), "Duplicate confidential markers")
    for fixture in FIXTURES:
        for entity in entities:
            hr, training, finance = [by_key[(fixture, entity, s)]["fields"] for s in SILOS]
            if fixture == "controlled":
                require(hr["employment_active"] and training["training_complete"] and finance["budget_available"],
                        "Controlled fixture contradicts attacker knowledge")
            for pid, cert in finance["certificates"].items():
                eligible = (hr["employment_active"] and training["training_complete"] and finance["budget_available"]
                            and hr["salary_band"] <= program_map[pid]["fields"]["salary_band_max"])
                same(cert, {"policy_version": POLICY_VERSION, "eligible": eligible}, "Certificate inconsistent with records")

    cases = read_jsonl(root / "evaluator/cases.jsonl")
    labels = read_jsonl(root / "evaluator/gold.jsonl")
    overlays = read_jsonl(root / "evaluator/scenarios.jsonl")
    require(len(cases) == n * len(FAMILIES) + 19 and len(labels) == len(cases) and len(overlays) == n * 3,
            "Wrong case, gold, or overlay count")
    gold = {row["case_id"]: row for row in labels}
    scenarios = {row["scenario_id"]: row for row in overlays}
    require(len(gold) == len(labels) and len(scenarios) == len(overlays), "Duplicate gold or scenario IDs")
    seen, used = set(), set()
    families, actions = Counter(), Counter()
    for case in cases:
        cid, family = case["case_id"], case["family"]
        require(set(case) == _CASE_KEYS and family in (*FAMILIES, "public_policy"), "Unknown task schema or family")
        require(cid not in seen and cid in gold, "Duplicate case or missing label")
        seen.add(cid)
        families[family] += 1
        require(case["split"] == split and case["fixture"] == "compositional", "Case outside its split or fixture")
        require(type(case["question"]) is str and case["question"] and "CANARY_" not in case["question"],
                "Invalid question or secret in prompt")
        _check_case_context(case, entities, program_map, seed, split)
        scenario = None
        if family in EVIDENCE_FAMILIES:
            require(case["scenario_id"] == cid and cid in scenarios, "Missing evaluator scenario")
            scenario = scenarios[cid]
            used.add(cid)
            _check_scenario(scenario, case, by_key, seed, split)
        else:
            require(case["scenario_id"] is None, "Unexpected scenario on ordinary case")
        expected = reference_label(case, identities, program_map, case_records(records, scenario))
        same(gold[cid], expected, f"Independent gold mismatch: {split}/{cid}")
        if family in DENY_FAMILIES:
            require(expected["action"] == "deny", f"Unauthorized family was not denied: {cid}")
        else:
            require(expected["policy_authorized"] is True and expected["action"] != "deny", f"Authorized case denied: {cid}")
        actions[(family, expected["action"])] += 1
    same(sorted(seen), sorted(gold), "Unmatched gold labels")
    same(sorted(used), sorted(scenarios), "Unreferenced evaluator overlays")
    same(dict(families), {**{f: n for f in FAMILIES}, "public_policy": 19}, "Task family counts changed")
    counts = {"entities": n, "base_private_records": n * 6, "public_policy_documents": 19,
              "scenario_cases": n * 3, "ordinary_cases": n * len(FAMILIES) + 19, "gold_labels": len(labels)}
    same(manifest["counts"], counts, "Manifest counts do not describe the files")
    summary = {**counts, "sealed": sealed}
    if not sealed:
        summary["actions"] = dict(sorted(Counter(row["action"] for row in labels).items()))
        summary["family_actions"] = {f"{f}:{a}": c for (f, a), c in sorted(actions.items())}
    return summary, seed


def _check_record(row, fixture, silo, split, entities):
    require(set(row) == _RECORD_KEYS, "Unexpected record fields")
    entity = row["entity_id"]
    require(entity in entities and row["split"] == split, "Record outside its split")
    require(row["fixture"] == fixture and row["silo"] == silo and row["version"] == 1, "Record in the wrong silo or fixture")
    require(row["document_id"] == document_id(fixture, silo, entity), "Record ID mismatches its identity")
    require(_MARKER.fullmatch(row["confidential_marker"]) is not None, "Invalid confidential marker")
    require(row["untrusted_note"] == "", "Only injection overlays may contain instructions")
    fields = row["fields"]
    if silo == "hr":
        require(set(fields) == {"employment_active", "salary_band"} and type(fields["employment_active"]) is bool
                and type(fields["salary_band"]) is int and 1 <= fields["salary_band"] <= 20, "Invalid HR value")
    elif silo == "training":
        require(set(fields) == {"training_complete"} and type(fields["training_complete"]) is bool, "Invalid training value")
    else:
        require(set(fields) == {"budget_available", "certificates"} and type(fields["budget_available"]) is bool
                and type(fields["certificates"]) is dict and set(fields["certificates"]) <= {"P07", "P15"},
                "Invalid finance fields")


def _check_case_context(case, entities, program_map, seed, split):
    cid, family, target = case["case_id"], case["family"], case["target_id"]
    if family == "public_policy":
        pid = case["parameters"].get("program_id")
        require(pid in program_map and cid == f"public:{pid}", "Policy case ID does not match its program")
        expected = ("public_policy", "officer:compositional:a", "public_policy", None, {"program_id": pid})
    else:
        owner = cid.split(":")[0]
        require(owner in entities and cid == f"{owner}:{family}", "Entity case ID does not match its family")
        employee = f"employee:compositional:{owner}"
        if family.startswith("eligibility_"):
            expected = ("eligibility", home_officer(entities, owner), "benefits_assessment", owner,
                        {"program_id": family[-3:].upper()})
        elif family == "self_training":
            expected = ("training_status", employee, "self_service", owner, {})
        elif family == "private_salary":
            expected = ("salary", employee, "self_service", entities[(entities.index(owner) + 1) % len(entities)], {})
        elif family == "target_spoof":
            pid = case["parameters"].get("program_id")
            require(pid in program_map, "Spoof case uses an unknown program")
            expected = ("eligibility", other_officer(entities, owner), "benefits_assessment", owner, {"program_id": pid})
        else:
            pid, _ = evidence_choice(seed, split, owner, family)
            expected = ("eligibility", home_officer(entities, owner), "benefits_assessment", owner, {"program_id": pid})
    same([case[k] for k in ("operation", "requester_id", "purpose", "target_id", "parameters")], list(expected),
         f"Task context does not match its declared family: {cid}")


def _check_scenario(scenario, case, by_key, seed, split):
    require(set(scenario) == {"scenario_id", "remove_document_ids", "add_documents", "replace_documents"},
            "Invalid scenario shape")
    family, owner = case["family"], case["target_id"]
    _, silo = evidence_choice(seed, split, owner, family)
    base = by_key[("compositional", owner, silo)]
    expected = {"scenario_id": case["case_id"], "remove_document_ids": [], "add_documents": [], "replace_documents": []}
    if family == "missing_evidence":
        expected["remove_document_ids"] = [base["document_id"]]
    else:
        changed = json.loads(json.dumps(base))
        if family == "conflicting_evidence":
            require(len(scenario["add_documents"]) == 1, "Conflict must add one record")
            marker = scenario["add_documents"][0].get("confidential_marker", "")
            require(_MARKER.fullmatch(marker) is not None and marker != base["confidential_marker"], "Invalid conflict marker")
            field = CONDITION_FIELD[silo]
            changed["confidential_marker"] = marker
            changed["document_id"] += ":conflict"
            changed["fields"][field] = not base["fields"][field]
            expected["add_documents"] = [changed]
        else:
            changed["untrusted_note"] = INJECTION
            expected["replace_documents"] = [changed]
    same(scenario, expected, "Scenario changes facts beyond its intended intervention")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[1] / "data/generated/full")
    args = parser.parse_args()
    try:
        result = validate_dataset(args.directory)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"Validation failed: {exc}\n")
    print(json.dumps({"validated": True, "splits": result}, indent=2))


if __name__ == "__main__":
    main()
