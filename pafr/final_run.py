"""Phase 6: the single confirmatory run on the sealed test split.

Refuses to start unless the freeze package verifies, the Git working tree is
clean, and the recorded commit is checked out. It then unseals the test split
for this process only, runs every method on both strata at the frozen
operating points, and writes results that are never used to change settings.

    .venv/bin/python -m pafr.final_run --confirm
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .analysis import analyze
from .attack import run
from .freeze import DATA, MANIFEST, MODEL_PATH, ROOT, git_state, verify
from .routing_model import load_model
from .schema import write_json, write_jsonl
from .validation import read_json


def preflight():
    problems = verify()
    manifest = read_json(MANIFEST)
    git = git_state()
    if not git["clean"]:
        problems.append("Git working tree has uncommitted changes in pafr/ or research/")
    if not manifest["git"]["clean"]:
        problems.append("Freeze was created from uncommitted code; commit, re-run `pafr.freeze create`, "
                        "commit the manifest, then run again")
    elif manifest["git"]["head"] != git["head"]:
        changed = _changed_since(manifest["git"]["head"])
        if changed is None or set(changed) - {"research/freeze/freeze_manifest.json"}:
            problems.append(f"Commits after the frozen commit {manifest['git']['head'][:10]} change more than the "
                            f"freeze manifest: {changed}")
    return problems, manifest


def _changed_since(commit):
    """Files changed between the frozen commit and HEAD, or None if it is not an ancestor."""
    import subprocess
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT)
    if ancestor.returncode != 0:
        return None
    diff = subprocess.run(["git", "diff", "--name-only", commit, "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return [line for line in diff.stdout.splitlines() if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm", action="store_true", help="Required: acknowledge this is the one confirmatory test run")
    args = parser.parse_args()
    problems, manifest = preflight()
    if problems:
        parser.exit(2, "Refusing the final run:\n- " + "\n- ".join(problems) + "\n")
    if not args.confirm:
        parser.exit(2, "Preflight passed. Re-run with --confirm to open the sealed test split.\n")
    output = ROOT / "research/results" / f"final-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    if output.exists():
        parser.exit(2, f"Refusing to overwrite {output}\n")
    points = manifest["operating_points"]
    model = load_model(MODEL_PATH)
    results = {"freeze_manifest_created": manifest["created_utc"], "git_head": manifest["git"]["head"],
               "operating_points": points, "strata": {}}
    for fixture in manifest["run"]["strata"]:
        campaigns, truths = [], None
        for method in manifest["run"]["methods"]:
            c, truths = run(DATA / "test", [method], model, seeds=tuple(manifest["run"]["seeds"]),
                            count_limit=points["B4-C"]["count_limit"], k=points["B5"]["k"], unseal=True, fixture=fixture)
            campaigns += c
        results["strata"][fixture] = analyze(campaigns, truths)
        write_jsonl(output / f"{fixture}_attacker_transcripts.jsonl",
                    [{"method": c.method, "target_id": c.target_id, "seed": c.seed, "attempts": c.attempts} for c in campaigns])
    write_json(output / "summary.json", results)
    primary = results["strata"]["controlled"]["contrasts"]["B5 vs B4-C"]
    print(json.dumps({"output": str(output.relative_to(ROOT)), "primary_contrast": primary}, indent=2))


if __name__ == "__main__":
    main()
