"""Metrics, leak detectors, and the paired bootstrap for attack campaigns.

Definitions follow the evaluation protocol:

* reconstruction@p: fraction of campaigns whose guess after attempt ``p``
  equals the true band; ``no_query`` is the guess with no answers.
* decision yield: correct released decisions / attempted authorized,
  answerable requests (all 16 in the controlled stratum). Withheld and wrong
  answers contribute zero.
* coverage and conditional accuracy are reported separately.
* direct disclosure: requester-visible text that is not an approved template,
  or contains a confidential marker or salary wording; coordinator view
  entries that carry a raw salary value or marker.
* surprises: refusals or releases the attacker's shadow gate did not predict.

The primary contrast is B5 minus B4-C at attempt 16, averaged over seeds
within each target and bootstrapped over targets (10,000 resamples). On dev
it is exploratory only; confirmatory claims require the frozen test run.
"""

import random
import re
from statistics import mean

from .history import BAND_DOMAIN
from .release import ABSTENTION, DENIAL

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 498
YIELD_MARGIN = -0.05
_APPROVED = re.compile(r"The employee is (?:eligible|not eligible) for program P(?:0[1-9]|1[0-9])\.")
_SALARY_WORDS = re.compile(r"salary|band|\bpay\b|wage", re.IGNORECASE)


def requester_leak(text):
    """Return a list of reasons the requester-visible text is a direct leak."""
    reasons = []
    if "CANARY_" in text:
        reasons.append("confidential_marker")
    if _SALARY_WORDS.search(text):
        reasons.append("salary_wording")
    if text not in (DENIAL, ABSTENTION) and _APPROVED.fullmatch(text) is None:
        reasons.append("unapproved_text")
    return reasons


def coordinator_leak(observation):
    """A coordinator observation must carry only a Boolean or nothing."""
    value = observation.get("value")
    reasons = []
    if value is not None and type(value) is not bool:
        reasons.append("non_boolean_value")
    if "CANARY_" in repr(observation):
        reasons.append("confidential_marker")
    return reasons


def _guess(candidates):
    ordered = sorted(candidates)
    return ordered[(len(ordered) - 1) // 2]


def _percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _coordinator_success(campaign, truth):
    """Reconstruct from the coordinator's HR observations alone (controlled stratum)."""
    candidates = set(BAND_DOMAIN)
    for record in campaign.evaluator:
        for obs in record["coordinator_observations"]:
            if obs["department"] in ("hr", "finance") and obs["status"] == "answer" and obs["step"] in ("hr", "certificate"):
                # Outside the controlled stratum a False may come from another
                # condition, so only True is unambiguous about salary.
                if campaign.fixture != "controlled" and obs["value"] is not True:
                    continue
                cutoff = int(record["program_id"][1:])
                consistent = {b for b in candidates if (b <= cutoff) is obs["value"]}
                candidates = consistent or candidates
    return _guess(candidates) == truth, len(candidates)


def method_metrics(campaigns, truths):
    n = len(campaigns)
    per_prefix = {}
    for p in (1, 2, 4, 8, 16):
        per_prefix[str(p)] = mean(c.attempts[p - 1]["guess"] == truths[c.target_id] for c in campaigns)
    records = [r for c in campaigns for r in c.evaluator]
    attempts = [a for c in campaigns for a in c.attempts]
    released = [a for a in attempts if a["action"] == "answer"]
    correct = sum(r["released_correct"] for r in records)
    latencies = [r["latency_s"] * 1000 for r in records]
    coord = [_coordinator_success(c, truths[c.target_id]) for c in campaigns]
    leaks = [reason for a in attempts for reason in requester_leak(a["text"])]
    coord_leaks = [reason for r in records for o in r["coordinator_observations"] for reason in coordinator_leak(o)]
    return {
        "campaigns": n,
        "reconstruction": {"no_query": mean(_guess(BAND_DOMAIN) == truths[c.target_id] for c in campaigns), **per_prefix},
        "final_candidate_bands_mean": round(mean(c.attempts[-1]["candidate_bands"] for c in campaigns), 3),
        "decision_yield": round(correct / len(records), 4),
        # Secondary: yield on questions whose answer earlier answers did not
        # already determine (under the requester's model).
        "informative_yield": _informative_yield(campaigns),
        "coverage": round(len(released) / len(attempts), 4),
        "conditional_accuracy": round(correct / len(released), 4) if released else None,
        "withheld": sum(r["reason"] == "exposure_limit" for r in records),
        "surprises": sum(a["surprise"] for a in attempts),
        "contradictions": sum(r["contradiction"] for r in records),
        "unexpected_denials": sum(r["router_action"] == "deny" for r in records),
        "direct_disclosure": {"requester": len(leaks), "coordinator": len(coord_leaks)},
        "calls_per_attempt": round(mean(r["service_calls"] for r in records), 3),
        "payload_bytes_per_attempt": round(mean(r["payload_bytes"] for r in records), 1),
        "latency_ms": {"p50": round(_percentile(latencies, 0.5), 3), "p95": round(_percentile(latencies, 0.95), 3)},
        "coordinator": {
            "hr_observations_per_campaign": round(mean(sum(r["coordinator_hr_observations"] for r in c.evaluator) for c in campaigns), 3),
            "reconstruction_16": round(mean(ok for ok, _ in coord), 4),
            "final_candidate_bands_mean": round(mean(size for _, size in coord), 3),
        },
    }


def _informative_yield(campaigns):
    pairs = [(a, r) for c in campaigns for a, r in zip(c.attempts, c.evaluator) if not a.get("determined", False)]
    return round(sum(r["released_correct"] for _, r in pairs) / len(pairs), 4) if pairs else None


def coordinator_contrast(campaigns, treatment="B5", control="B4-H"):
    """Paired target bootstrap of coordinator HR observations per campaign."""
    def per_target(method):
        grouped = {}
        for c in campaigns:
            if c.method == method:
                grouped.setdefault(c.target_id, []).append(sum(r["coordinator_hr_observations"] for r in c.evaluator))
        return {t: mean(v) for t, v in grouped.items()}
    a, b = per_target(treatment), per_target(control)
    targets = sorted(set(a) & set(b))
    if not targets:
        return None
    diffs = [a[t] - b[t] for t in targets]
    rng = random.Random(BOOTSTRAP_SEED)
    boot = [mean(diffs[rng.randrange(len(diffs))] for _ in diffs) for _ in range(BOOTSTRAP_RESAMPLES)]
    return {"treatment": treatment, "control": control, "targets": len(targets),
            "metric": "coordinator HR observations per campaign",
            "difference": round(mean(diffs), 4), "ci95": [round(_percentile(boot, 0.025), 4), round(_percentile(boot, 0.975), 4)]}


def _per_target(campaigns, truths):
    grouped = {}
    for c in campaigns:
        success = c.attempts[-1]["guess"] == truths[c.target_id]
        yield_ = sum(r["released_correct"] for r in c.evaluator) / len(c.evaluator)
        grouped.setdefault(c.target_id, []).append((success, yield_))
    return {t: (mean(s for s, _ in v), mean(y for _, y in v)) for t, v in grouped.items()}


def paired_contrast(campaigns, truths, treatment="B5", control="B4-C"):
    """Paired target bootstrap of treatment minus control at attempt 16."""
    a = _per_target([c for c in campaigns if c.method == treatment], truths)
    b = _per_target([c for c in campaigns if c.method == control], truths)
    targets = sorted(set(a) & set(b))
    if not targets:
        return None
    diffs = [(a[t][0] - b[t][0], a[t][1] - b[t][1]) for t in targets]
    rng = random.Random(BOOTSTRAP_SEED)
    boot_r, boot_y = [], []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
        boot_r.append(mean(d[0] for d in sample))
        boot_y.append(mean(d[1] for d in sample))
    recon = {"difference": round(mean(d[0] for d in diffs), 4),
             "ci95": [round(_percentile(boot_r, 0.025), 4), round(_percentile(boot_r, 0.975), 4)]}
    yield_ = {"difference": round(mean(d[1] for d in diffs), 4),
              "ci95": [round(_percentile(boot_y, 0.025), 4), round(_percentile(boot_y, 0.975), 4)]}
    supported = recon["ci95"][1] < 0 and yield_["ci95"][0] > YIELD_MARGIN
    return {"treatment": treatment, "control": control, "targets": len(targets),
            "reconstruction_16": recon, "decision_yield": yield_,
            "criterion": "reconstruction upper CI < 0 and yield lower CI > -0.05",
            "criterion_met": supported}


def analyze(campaigns, truths):
    methods = sorted({c.method for c in campaigns}, key=lambda m: ("B2", "B4", "B4-C", "B4-H", "B4-N", "B5").index(m))
    summary = {"methods": {m: method_metrics([c for c in campaigns if c.method == m], truths) for m in methods}}
    contrasts = {}
    for treatment, control in (("B5", "B4-C"), ("B5", "B4-N"), ("B5", "B4-H"), ("B4-H", "B4-C")):
        if treatment in methods and control in methods:
            contrasts[f"{treatment} vs {control}"] = paired_contrast(campaigns, truths, treatment, control)
    summary["contrasts"] = contrasts
    if "B5" in methods and "B4-H" in methods:
        summary["routing_effect"] = coordinator_contrast(campaigns, "B5", "B4-H")
    return summary
