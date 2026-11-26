"""Phase 5: predeclared development sweep and operating-point selection.

Follows the evaluation protocol's "Development and operating points" section.
Everything here runs on the **development** split only; the test split stays
sealed.

Predeclared grids (fixed before the sweep, recorded in the output):

* B4-C count limit: 1..16
* B5 candidate-set ``k``: 1..16  (at most 16 privacy operating points)
* B4-H and B4-N inherit B5's selected ``k`` unchanged.

Selection rule, applied identically to B4-C and B5 on the primary
(controlled) stratum: keep settings whose campaign decision yield lies in the
acceptance band [0.75, 0.85]; choose the lowest reconstruction@16; break ties
by higher yield, then fewer department calls per attempt, then the lower
parameter value (fixed configuration order). If no setting reaches the band,
the primary comparison is recorded as unavailable before any test access.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .analysis import coordinator_contrast, method_metrics, paired_contrast
from .methods import METHOD_IDS
from .attack import DEFAULT_SEEDS, run
from .routing_model import load_model
from .schema import write_json
from .validation import read_json

COUNT_GRID = tuple(range(1, 17))
K_GRID = tuple(range(1, 17))
YIELD_BAND = (0.75, 0.85)
TARGET_YIELD = 0.80


def sweep(dev_dir, model, seeds=DEFAULT_SEEDS):
    """Run the full predeclared grid on the controlled stratum; return all rows."""
    rows = {"B4-C": [], "B5": []}
    for method, grid, key in (("B4-C", COUNT_GRID, "count_limit"), ("B5", K_GRID, "k")):
        for value in grid:
            campaigns, truths = run(dev_dir, [method], model, seeds=seeds, **{key: value})
            metrics = method_metrics(campaigns, truths)
            rows[method].append({
                "parameter": key, "value": value,
                "reconstruction_16": metrics["reconstruction"]["16"],
                "decision_yield": metrics["decision_yield"],
                "calls_per_attempt": metrics["calls_per_attempt"],
                "final_candidate_bands_mean": metrics["final_candidate_bands_mean"],
            })
    return rows


def select(rows):
    """Apply the protocol's selection rule to one method's sweep rows."""
    low, high = YIELD_BAND
    eligible = [r for r in rows if low <= r["decision_yield"] <= high]
    if not eligible:
        return None
    return min(eligible, key=lambda r: (r["reconstruction_16"], -r["decision_yield"], r["calls_per_attempt"], r["value"]))


def tune(dev_dir, model_path, seeds=DEFAULT_SEEDS):
    dev_dir = Path(dev_dir)
    split = read_json(dev_dir / "evaluator/manifest.json")["split"]
    if split != "dev":
        raise ValueError("Operating points may be selected only on the development split")
    model = load_model(model_path)
    rows = sweep(dev_dir, model, seeds)
    chosen = {method: select(rows[method]) for method in rows}
    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": split, "stratum": "controlled", "seeds": list(seeds),
        "grids": {"B4-C": {"count_limit": list(COUNT_GRID)}, "B5": {"k": list(K_GRID)}},
        "rule": {"yield_band": list(YIELD_BAND), "target_yield": TARGET_YIELD,
                 "order": ["lowest reconstruction_16", "higher decision_yield", "fewer calls_per_attempt", "lower parameter value"]},
        "sweep": rows,
        "selected": {
            "B4-C": chosen["B4-C"] and {"count_limit": chosen["B4-C"]["value"]},
            "B5": chosen["B5"] and {"k": chosen["B5"]["value"]},
            "B4-H": chosen["B5"] and {"k": chosen["B5"]["value"], "inherited_from": "B5"},
            "B4-N": chosen["B5"] and {"k": chosen["B5"]["value"], "inherited_from": "B5"},
        },
        "primary_comparison_available": all(chosen.values()),
    }
    if result["primary_comparison_available"]:
        limit, k = chosen["B4-C"]["value"], chosen["B5"]["value"]
        strata = {}
        for fixture in ("controlled", "compositional"):
            campaigns = []
            truths = None
            for method in METHOD_IDS:
                c, truths = run(dev_dir, [method], model, seeds=seeds, count_limit=limit, k=k, fixture=fixture)
                campaigns += c
            strata[fixture] = {
                "methods": {m: method_metrics([c for c in campaigns if c.method == m], truths)
                            for m in METHOD_IDS},
                "contrast_B5_vs_B4C": paired_contrast(campaigns, truths, "B5", "B4-C"),
                "contrast_B5_vs_B4N": paired_contrast(campaigns, truths, "B5", "B4-N"),
                "contrast_B5_vs_B4H": paired_contrast(campaigns, truths, "B5", "B4-H"),
                "routing_effect_B5_vs_B4H": coordinator_contrast(campaigns, "B5", "B4-H"),
            }
        result["at_selected_points"] = strata
        contrast = strata["controlled"]["contrast_B5_vs_B4C"]
        width = {k: round(v["ci95"][1] - v["ci95"][0], 4) for k, v in
                 (("reconstruction_16", contrast["reconstruction_16"]), ("decision_yield", contrast["decision_yield"]))}
        result["sample_size_check"] = {
            "dev_targets": contrast["targets"], "dev_ci95_width": width,
            "note": "Development CI widths for the primary contrast with 48 targets; the test split also has 48.",
        }
    result["status"] = "exploratory development results; not confirmatory"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dev_dir", type=Path, nargs="?", default=Path("data/generated/full/dev"))
    parser.add_argument("--model", type=Path, default=Path("data/generated/models/routing_model.json"))
    parser.add_argument("--output", type=Path, default=Path("research/freeze/operating_points.json"))
    args = parser.parse_args()
    result = tune(args.dev_dir, args.model)
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output), "selected": result["selected"],
                      "primary_comparison_available": result["primary_comparison_available"],
                      "sample_size_check": result.get("sample_size_check")}, indent=2))


if __name__ == "__main__":
    main()
