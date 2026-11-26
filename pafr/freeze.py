"""Phase 5 freeze package: record, verify, and gate the final test run.

``create`` writes ``research/freeze/freeze_manifest.json`` with SHA-256
fingerprints of every source file, the protocol document, the dataset
manifests, the routing model, and the selected operating points, plus seeds,
analysis settings, the local LLM configuration and digest, and the Git state.

``verify`` recomputes every fingerprint and lists differences. The final test
run (``pafr.final_run``) refuses to start unless verification passes *and*
the Git working tree is clean at the recorded commit, which the protocol
requires to identify the frozen package.

    .venv/bin/python -m pafr.freeze create
    .venv/bin/python -m pafr.freeze verify
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from urllib.request import ProxyHandler, build_opener

from .analysis import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, YIELD_MARGIN
from .attack import ATTEMPTS, DEFAULT_SEEDS, PREFIXES
from .methods import METHOD_IDS
from .ollama import MODEL
from .schema import checksum, write_json
from .validation import read_json

ROOT = Path(__file__).resolve().parents[1]
FREEZE_DIR = ROOT / "research/freeze"
MANIFEST = FREEZE_DIR / "freeze_manifest.json"
DATA = ROOT / "data/generated/full"
MODEL_PATH = ROOT / "data/generated/models/routing_model.json"
OPERATING_POINTS = FREEZE_DIR / "operating_points.json"
PROTOCOL = ROOT / "research/design/evaluation_protocol.md"
LLM_OPTIONS = {"num_ctx": 2048, "num_predict": 96, "temperature": 0, "seed": 42}


def _source_files():
    return sorted(p for p in (ROOT / "pafr").rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def fingerprints():
    files = {str(p.relative_to(ROOT)): checksum(p) for p in _source_files()}
    files[str(PROTOCOL.relative_to(ROOT))] = checksum(PROTOCOL)
    files[str(OPERATING_POINTS.relative_to(ROOT))] = checksum(OPERATING_POINTS)
    files["data/generated/full/manifest.json"] = checksum(DATA / "manifest.json")
    for split in ("train", "dev", "test"):
        path = DATA / split / "evaluator/manifest.json"
        files[str(path.relative_to(ROOT))] = checksum(path)
    files["data/generated/models/routing_model.json"] = checksum(MODEL_PATH)
    return files


def git_state():
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    status = git("status", "--porcelain", "--", "pafr", "research/freeze", "research/design")
    return {"head": git("rev-parse", "HEAD"), "clean": status == "", "uncommitted": status.splitlines() if status else []}


def llm_digest():
    """Digest of the local model from Ollama, or None if Ollama is not running."""
    try:
        with build_opener(ProxyHandler({})).open("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            models = json.loads(response.read())["models"]
        return next((m["digest"] for m in models if m["name"] == MODEL), None)
    except (OSError, ValueError, KeyError):
        return None


def create():
    points = read_json(OPERATING_POINTS)
    if not points.get("primary_comparison_available"):
        raise ValueError("Operating points are unavailable; the primary comparison cannot be frozen")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "candidate",
        "protocol": {"document": str(PROTOCOL.relative_to(ROOT)), "amendment": "Amendment 1 (2026-11-23, pre-freeze)",
                     "primary_contrast": "B5 vs B4-C at attempt 16, controlled stratum",
                     "key_secondary": ["B5 vs B4-N reconstruction (denial leakage), both strata",
                                       "B5 vs B4-H coordinator HR observations (routing effect), compositional stratum",
                                       "B5 vs B4-C reconstruction, compositional stratum"],
                     "criterion": f"reconstruction upper CI < 0 and decision-yield lower CI > {YIELD_MARGIN}"},
        "operating_points": points["selected"],
        "run": {"methods": list(METHOD_IDS), "strata": ["controlled", "compositional"],
                "seeds": list(DEFAULT_SEEDS), "attempts": ATTEMPTS, "prefixes": list(PREFIXES),
                "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED}, "llm_called_in_campaigns": False},
        "llm": {"model": MODEL, "digest": llm_digest(), "options": LLM_OPTIONS},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "git": git_state(),
        "sha256": fingerprints(),
    }
    write_json(MANIFEST, manifest)
    return manifest


def verify():
    """Return a list of problems; empty means the package matches the manifest."""
    manifest = read_json(MANIFEST)
    problems = []
    current = fingerprints()
    for path, digest in manifest["sha256"].items():
        if current.get(path) != digest:
            problems.append(f"changed: {path}")
    for path in sorted(set(current) - set(manifest["sha256"])):
        problems.append(f"new file not in freeze: {path}")
    if read_json(OPERATING_POINTS)["selected"] != manifest["operating_points"]:
        problems.append("operating points differ from the freeze")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("create", "verify"))
    args = parser.parse_args()
    if args.command == "create":
        manifest = create()
        print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "files": len(manifest["sha256"]),
                          "operating_points": manifest["operating_points"], "llm_digest": manifest["llm"]["digest"],
                          "git": manifest["git"]}, indent=2))
    else:
        problems = verify()
        git = git_state()
        print(json.dumps({"matches_freeze": not problems, "problems": problems, "git_clean": git["clean"],
                          "git_head": git["head"]}, indent=2))
        raise SystemExit(0 if not problems else 1)


if __name__ == "__main__":
    main()
