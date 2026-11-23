"""Local web demo for PAFR: officer questions and side-by-side attack campaigns.

Runs only on 127.0.0.1 with Python's standard library. It uses the same
planner, router, gates, release boundary, and (optionally) local Llama as the
terminal demo and the experiments. The identity is picked by the operator from
the trusted mock table; this is not a login. The sealed test split is never
listed and the router refuses it regardless.

The page shows a trusted *operator view* (departments contacted, gate state,
and optionally the true band) next to what the requester sees. In a real
deployment the requester would see only the answer text.

    .venv/bin/python -m pafr.web            # then open http://127.0.0.1:8498
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from threading import Lock

from .attack import FIXTURE as ATTACK_FIXTURE, REQUESTER as ATTACK_REQUESTER, run_campaign
from .demo import OfficerDemo
from .history import BAND_DOMAIN
from .methods import METHOD_IDS, build_method
from .ollama import MODEL
from .planner import plan_question
from .routing_model import load_model
from .sealing import SealedSplitError, is_sealed
from .services import ServiceError, load_pilot_identity
from .validation import read_json, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "web_static" / "index.html"
DATASETS = {
    "pilot": ROOT / "data/generated/pilot",
    "train": ROOT / "data/generated/full/train",
    "dev": ROOT / "data/generated/full/dev",
}
MODEL_PATH = ROOT / "data/generated/models/routing_model.json"
STATIC_METHOD = "static"
MAX_BODY = 4096
MAX_SESSIONS = 64


class TemplateClient:
    """LLM switched off: release the approved template sentence unchanged."""

    def answer(self, question, fact, allowed_answers):
        return allowed_answers[0]


class DemoApp:
    def __init__(self, datasets=None, model_path=MODEL_PATH, client_factory=None):
        self.datasets = {name: Path(path) for name, path in (datasets or DATASETS).items()}
        self.model_path = Path(model_path)
        self.client_factory = client_factory
        self._sessions = {}
        self._lock = Lock()
        self._model = None

    # -- helpers ---------------------------------------------------------
    def _dataset(self, name):
        path = self.datasets.get(name)
        if path is None or not (path / "evaluator/manifest.json").exists():
            raise ValueError("Unknown or missing dataset")
        if is_sealed(path):
            raise SealedSplitError("The sealed test split is not available in the demo.")
        return path

    def _routing_model(self):
        if self._model is None:
            self._model = load_model(self.model_path)
        return self._model

    def _router(self, path, method, k, limit):
        if method == STATIC_METHOD:
            return None
        model = self._routing_model() if method != "B2" else None
        return build_method(method, path, model, count_limit=limit, k=k)

    # -- API ---------------------------------------------------------------
    def config(self):
        datasets = {}
        for name, path in self.datasets.items():
            if not (path / "evaluator/manifest.json").exists() or is_sealed(path):
                continue
            identities = read_json(path / "evaluator/identities.json")
            officers = {officer: {"fixture": row["fixtures"][0], "targets": sorted(row["assigned_targets"])}
                        for officer, row in sorted(identities.items()) if row.get("role") == "benefits_officer"}
            datasets[name] = {"officers": officers}
        return {"datasets": datasets, "methods": [STATIC_METHOD, *METHOD_IDS],
                "model_available": self.model_path.exists(), "llm_model": MODEL,
                "llm_available": self.client_factory is not None and _ollama_up()}

    def create_session(self, body):
        path = self._dataset(body.get("dataset"))
        officer = body.get("officer")
        identity = load_pilot_identity(path, officer)
        if identity.role != "benefits_officer" or len(identity.fixtures) != 1:
            raise ValueError("Choose a benefits officer")
        fixture = next(iter(identity.fixtures))
        method = body.get("method", STATIC_METHOD)
        if method not in (STATIC_METHOD, *METHOD_IDS):
            raise ValueError("Unknown method")
        k, limit = _int(body.get("k", 4), 1, 20), _int(body.get("limit", 8), 1, 16)
        llm = body.get("llm") is True
        client = (self.client_factory() if self.client_factory else None) if llm else TemplateClient()
        demo = OfficerDemo(path, fixture, client=client, limit=limit, officer=officer,
                           router=self._router(path, method, k, limit))
        session_id = secrets.token_urlsafe(16)
        with self._lock:
            if len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(next(iter(self._sessions)))
            self._sessions[session_id] = {"demo": demo, "method": method, "k": k, "limit": limit, "llm": llm}
        return {"session_id": session_id, "fixture": fixture, "method": method, "targets": demo.targets(),
                "gate": _gate_label(method, k, limit), "llm": llm}

    def ask(self, body):
        with self._lock:
            session = self._sessions.get(body.get("session_id"))
        if session is None:
            raise ValueError("Session expired; start a new session")
        question = body.get("question")
        if type(question) is not str or not 0 < len(question) <= 500:
            raise ValueError("Ask a question of 1-500 characters")
        demo = session["demo"]
        reply = demo.handle(question)
        result = demo.last_result
        target = _target_of(question, demo)
        plan = plan_question(question)
        return {
            "requester_view": {"action": reply.action, "text": reply.text,
                               "source": ("llm" if session["llm"] else "template") if reply.action == "answer" else None},
            "operator_view": {
                "operation": plan.operation if plan else None,
                "program_id": plan.program_id if plan else None,
                "router_action": result.action if result else "not_routed",
                "reason": result.reason if result else "unsupported_or_wrong_purpose",
                "service_calls": result.service_calls if result else 0,
                "departments": [{"department": o["department"], "step": o["step"], "status": o["status"],
                                 "value": o["value"]} for o in (result.observations if result else ())],
                "target": target,
                "gate": demo.history_for(target) if target else None,
                "candidates": _candidates(demo, target) if target else None,
            },
        }

    def attack(self, body):
        path = self._dataset(body.get("dataset", "dev"))
        target = body.get("target")
        identity = load_pilot_identity(path, ATTACK_REQUESTER)
        if target not in identity.assigned_targets:
            raise ValueError("Choose a target assigned to officer:controlled")
        methods = body.get("methods") or ["B4-C", "B5"]
        if not (1 <= len(methods) <= 5 and all(m in METHOD_IDS for m in methods)):
            raise ValueError("Choose one to five protocol methods")
        k, limit = _int(body.get("k", 4), 1, 20), _int(body.get("limit", 8), 1, 16)
        seed = _int(body.get("seed", 11), 0, 10_000)
        model = self._routing_model()
        truths = {r["entity_id"]: r["fields"]["salary_band"] for r in read_jsonl(path / f"silos/{ATTACK_FIXTURE}/hr.jsonl")}
        truth = truths[target]
        config = {"count_limit": limit, "k": k}
        results = []
        for method in methods:
            router = build_method(method, path, model, count_limit=limit, k=k)
            campaign = run_campaign(router, identity, method, target, seed, config, truth)
            results.append({"method": method, "gate": _gate_label(method, k, limit),
                            "attempts": _with_candidate_sets(campaign),
                            "final_guess": campaign.attempts[-1]["guess"],
                            "recovered": campaign.attempts[-1]["guess"] == truth,
                            "answered": sum(a["action"] == "answer" for a in campaign.attempts),
                            "calls": sum(r["service_calls"] for r in campaign.evaluator),
                            "hr_seen": sum(r["coordinator_hr_observations"] for r in campaign.evaluator)})
        return {"target": target, "true_band": truth, "results": results}


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected an integer from {low} to {high}")
    return value


def _gate_label(method, k, limit):
    if method == STATIC_METHOD:
        return f"static pilot router, count limit {limit}"
    return {"B2": "broadcast, no gate", "B4": "learned routing, no gate",
            "B4-C": f"learned routing, count limit {limit}", "B4-H": f"learned routing, candidate-set gate k={k}",
            "B5": f"PAFR: exposure-aware routing, candidate-set gate k={k}"}[method]


def _ollama_up():
    """Quick local check; never contacts anything but 127.0.0.1."""
    from urllib.request import ProxyHandler, build_opener
    try:
        with build_opener(ProxyHandler({})).open("http://127.0.0.1:11434/api/tags", timeout=0.5) as response:
            return response.status == 200
    except OSError:
        return False


def _target_of(question, demo):
    plan = plan_question(question)
    if plan is not None and plan.operation == "eligibility" and plan.target_id in demo.identity.assigned_targets:
        return plan.target_id
    return None


def _candidates(demo, target):
    """Bands the candidate-set gate still considers possible (CandidateSetGate only)."""
    gate = demo.history
    scope = next((s for s in getattr(gate, "_buckets", {})
                  if s.target_id == target and s.requester_id == demo.identity.requester_id), None)
    bucket = gate._buckets.get(scope) if scope else None
    if bucket is None or not hasattr(gate, "k"):
        return None
    return sorted(bucket.candidates)


def _with_candidate_sets(campaign):
    candidates, rows = set(BAND_DOMAIN), []
    for attempt in campaign.attempts:
        if attempt["action"] == "answer":
            cutoff = int(attempt["program_id"][1:])
            eligible = attempt["text"].startswith("The employee is eligible")
            candidates = {b for b in candidates if (b <= cutoff) is eligible} or candidates
        rows.append({"attempt": attempt["attempt"], "program_id": attempt["program_id"], "action": attempt["action"],
                     "text": attempt["text"], "guess": attempt["guess"], "candidates": sorted(candidates)})
    return rows


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PAFRDemo/1"

        def log_message(self, *args):
            pass

        def _host_ok(self):
            # Reject other Host names (DNS rebinding) and any cross-origin request.
            port = self.server.server_address[1]
            host_ok = self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            return host_ok and (origin is None or origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"})

        def _send(self, status, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self' 'unsafe-inline'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "forbidden"})
            if self.path in ("/", "/index.html"):
                return self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/config":
                return self._send(200, app.config())
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "forbidden"})
            routes = {"/api/session": app.create_session, "/api/ask": app.ask, "/api/attack": app.attack}
            handler = routes.get(self.path)
            if handler is None:
                return self._send(404, {"error": "not found"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._send(415, {"error": "expected application/json"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("Request body too large or empty")
                body = json.loads(self.rfile.read(length))
                if type(body) is not dict:
                    raise ValueError("Expected a JSON object")
                return self._send(200, handler(body))
            except SealedSplitError as exc:
                return self._send(403, {"error": str(exc)})
            except (ValueError, KeyError, TypeError, ServiceError, OSError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": str(exc) or "invalid request"})

    return Handler


def serve(port=8498, app=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app or DemoApp()))
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8498)
    args = parser.parse_args()
    from .ollama import OllamaClient
    server = serve(args.port, DemoApp(client_factory=OllamaClient))
    print(f"PAFR web demo on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
