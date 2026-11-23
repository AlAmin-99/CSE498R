"""Full three-split dataset: generation, validation, sealing, and gold agreement."""

import json
from pathlib import Path
import tempfile
import unittest

from pafr.dataset import FAMILIES, generate_dataset, officer_groups
from pafr.dataset_validation import validate_dataset
from pafr.endtoend import evaluate
from pafr.pilot import generate_pilot
from pafr.router import FederatedRouter
from pafr.schema import PLANNED_SPLITS, checksum, split_ids, write_json, write_jsonl
from pafr.sealing import SEAL_FILE, SealedSplitError
from pafr.validation import read_jsonl


class FullDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "full"
        cls.counts = generate_dataset(cls.root, record_seed=1234)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_split_sizes_are_disjoint_and_cover_the_planned_pool(self):
        ids = split_ids()
        self.assertEqual({s: len(v) for s, v in ids.items()}, PLANNED_SPLITS)
        self.assertEqual(len(set().union(*ids.values())), 240)
        for split, n in PLANNED_SPLITS.items():
            self.assertEqual(self.counts[split]["entities"], n)
            self.assertEqual(self.counts[split]["ordinary_cases"], n * len(FAMILIES) + 19)

    def test_only_the_test_split_is_sealed_and_tools_refuse_it(self):
        self.assertTrue((self.root / "test" / SEAL_FILE).exists())
        self.assertFalse((self.root / "train" / SEAL_FILE).exists())
        self.assertFalse((self.root / "dev" / SEAL_FILE).exists())
        with self.assertRaises(SealedSplitError):
            FederatedRouter(self.root / "test")
        with self.assertRaises(SealedSplitError):
            evaluate(self.root / "test")
        FederatedRouter(self.root / "test", unseal=True)  # explicit trusted unseal only

    def test_validation_reports_no_label_distribution_for_the_sealed_split(self):
        summary = validate_dataset(self.root)
        self.assertNotIn("actions", summary["test"])
        self.assertIn("actions", summary["dev"])

    def test_officers_split_assignments_and_spoof_uses_the_unassigned_officer(self):
        entities = split_ids()["dev"]
        groups = officer_groups(entities)
        self.assertEqual(sorted(groups["a"] + groups["b"]), sorted(entities))
        self.assertFalse(set(groups["a"]) & set(groups["b"]))
        identities = json.loads((self.root / "dev/evaluator/identities.json").read_text())
        for case in read_jsonl(self.root / "dev/evaluator/cases.jsonl"):
            if case["family"] == "target_spoof":
                self.assertNotIn(case["target_id"], identities[case["requester_id"]]["assigned_targets"])

    def test_attacker_view_contains_no_private_values(self):
        for split in PLANNED_SPLITS:
            text = (self.root / split / "attacker/controlled_view.json").read_text()
            self.assertNotIn("salary_band\"", text)
            self.assertNotIn("CANARY_", text)
            self.assertNotIn("1234", text)

    def test_training_records_match_a_pilot_made_with_the_same_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            pilot = Path(temporary) / "pilot"
            generate_pilot(pilot, employees=4, record_seed=1234)
            for fixture in ("compositional", "controlled"):
                for silo in ("hr", "training", "finance"):
                    pilot_rows = {r["entity_id"]: r for r in read_jsonl(pilot / f"silos/{fixture}/{silo}.jsonl")}
                    full_rows = {r["entity_id"]: r for r in read_jsonl(self.root / f"train/silos/{fixture}/{silo}.jsonl")}
                    for entity, row in pilot_rows.items():
                        self.assertEqual(full_rows[entity], row)

    def test_router_and_release_match_gold_on_dev(self):
        results = evaluate(self.root / "dev")
        self.assertEqual([r for r in results if not r.passed], [])
        families = {r.family for r in results}
        self.assertTrue(set(FAMILIES) <= families)

    def test_semantic_label_corruption_is_detected_even_with_fixed_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "full"
            generate_dataset(root, record_seed=99)
            gold_path = root / "dev/evaluator/gold.jsonl"
            labels = read_jsonl(gold_path)
            target = next(row for row in labels if row["action"] == "answer" and type(row["answer"]) is bool)
            target["answer"] = not target["answer"]
            write_jsonl(gold_path, labels)
            manifest_path = root / "dev/evaluator/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["sha256"]["evaluator/gold.jsonl"] = checksum(gold_path)
            write_json(manifest_path, manifest)
            top = json.loads((root / "manifest.json").read_text())
            top["split_manifest_sha256"]["dev"] = checksum(manifest_path)
            write_json(root / "manifest.json", top)
            with self.assertRaisesRegex(ValueError, "Independent gold mismatch"):
                validate_dataset(root)

    def test_removing_the_seal_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "full"
            generate_dataset(root, record_seed=7)
            (root / "test" / SEAL_FILE).unlink()
            with self.assertRaises(ValueError):
                validate_dataset(root)

    def test_refuses_to_overwrite(self):
        with self.assertRaises(FileExistsError):
            generate_dataset(self.root, record_seed=1)


if __name__ == "__main__":
    unittest.main()
