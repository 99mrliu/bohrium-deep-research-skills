#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_estimands import run  # noqa: E402
from estimand_core import (  # noqa: E402
    OperationBlocked, SchemaError, apply_transforms, ensure_operations_allowed, evaluate_all,
    evaluate_operation, load_all_corpus_documents, load_json, stratum_key,
    validate_operation_requests, validate_records,
)
from result_contract import render_result  # noqa: E402


class EstimandGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input_root = ROOT / "example" / "input"
        cls.case = load_json(cls.input_root / "case.json")
        cls.workorder = load_json(cls.input_root / "comparison-workorder.json")
        cls.envelope = load_json(ROOT / "example" / "work" / "estimands.json")
        cls.documents = load_all_corpus_documents(cls.input_root, cls.case["corpus_documents"])
        cls.task_text = (cls.input_root / "task.md").read_text(encoding="utf-8")
        cls.indexed = validate_records(cls.envelope["records"], cls.documents, cls.case["case_id"],
                                       cls.workorder["task_id"], cls.task_text)
        cls.requests = validate_operation_requests(cls.workorder["operation_requests"], cls.indexed)
        cls.results = {item["operation_id"]: item for item in evaluate_all(cls.requests, cls.indexed)}

    def request(self, operation_id: str) -> dict:
        return next(item for item in self.requests if item["operation_id"] == operation_id)

    def test_same_percent_does_not_override_metric_or_pollutant(self) -> None:
        describe = self.results["describe-all"]
        rank = self.results["rank-a-b"]
        pool = self.results["pool-a-b"]
        self.assertTrue(describe["allowed"])
        self.assertEqual(describe["comparability"], "noncomparable")
        self.assertFalse(rank["allowed"])
        self.assertFalse(pool["allowed"])
        self.assertIn("metric", rank["mismatches_after_requested_transforms"])
        self.assertIn("pollutant", rank["mismatches_after_requested_transforms"])

    def test_unknown_budget_blocks_rank_but_not_description(self) -> None:
        reasons = self.results["rank-a-b"]["blocking_reasons"]
        self.assertTrue(any("UNKNOWN:b-adsorption:budget" in reason for reason in reasons))
        self.assertTrue(self.results["describe-all"]["allowed"])
        self.assertEqual(self.indexed["b-adsorption"]["budget"]["value"], "not_reported")

    def test_direction_requires_caveats_and_is_not_ranking(self) -> None:
        self.assertTrue(self.results["direction-a-b"]["allowed"])
        request = copy.deepcopy(self.request("direction-a-b"))
        request.pop("caveats")
        self.assertFalse(evaluate_operation(request, self.indexed)["allowed"])

    def test_exact_min_to_h_transform_and_compatible_stratum(self) -> None:
        transformed, audit = apply_transforms(
            self.indexed, ["a-decolorization", "c-decolorization-hours"],
            self.request("transform-a-c")["transforms"],
        )
        self.assertEqual(len(audit), 2)
        self.assertEqual(transformed["a-decolorization"]["time"]["value"], 1.5)
        self.assertEqual(transformed["a-decolorization"]["budget"]["value"], 1.5)
        self.assertEqual(stratum_key(transformed["a-decolorization"]),
                         stratum_key(transformed["c-decolorization-hours"]))
        self.assertTrue(self.results["rank-a-c-after-transform"]["allowed"])

    def test_unapproved_conversion_fails_closed(self) -> None:
        request = copy.deepcopy(self.request("transform-a-c"))
        request["transforms"][0]["conversion"] = "percent_to_fold_change"
        outcome = evaluate_operation(request, self.indexed)
        self.assertFalse(outcome["allowed"])
        self.assertTrue(any(reason.startswith("TRANSFORM_INVALID") for reason in outcome["blocking_reasons"]))

    def test_negative_fake_pooling_fails_strict_mode(self) -> None:
        pool = self.results["pool-a-b"]
        self.assertFalse(pool["allowed"])
        self.assertIn("POOL_EXCHANGEABILITY_NOT_JUSTIFIED", pool["blocking_reasons"])
        with self.assertRaises(OperationBlocked):
            ensure_operations_allowed([pool])
        with self.assertRaises(OperationBlocked):
            run(self.input_root, ROOT / "example" / "work", ROOT / "example" / "output",
                strict_operations=True)

    def test_success_despite_noncomparability(self) -> None:
        output = run(self.input_root, ROOT / "example" / "work", ROOT / "example" / "output")
        self.assertEqual(output["status"], "success")
        self.assertEqual(output["case_id"], "synthetic-estimand-case-001")
        self.assertFalse(next(item for item in output["operation_results"]
                              if item["operation_id"] == "pool-a-b")["allowed"])

    def test_result_has_exact_case_and_all_contract_fields(self) -> None:
        result = json.loads((ROOT / "example" / "output" / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(set(result), set(self.case["output_contract"]) | {"case_id"})
        self.assertIsInstance(result["sources"], list)
        self.assertIsInstance(result["strata"], dict)
        self.assertEqual(len(result["sources"]), 3)
        self.assertEqual({item["source_document_id"] for item in result["sources"]},
                         {"paper-a", "paper-b", "paper-c"})

    def test_dynamic_contract_preserves_list_and_dict(self) -> None:
        context = {
            "matrix_path": "m.md", "operations_path": "o.md", "status": "success",
            "sources": [{"source_document_id": "s"}], "uncertainty": [], "change_records": [],
            "operation_results": [{"allowed": False}], "strata": {"abc": {"estimand_ids": []}},
            "estimands": [{"estimand_id": "e"}],
        }
        contract = {"comparison_matrix": {}, "sources": {}, "uncertainty": [],
                    "operation_results": {}, "custom_list": [], "custom_dict": {"nested": []}}
        result = render_result("x", contract, context)
        self.assertIsInstance(result["comparison_matrix"], dict)
        self.assertIsInstance(result["sources"], dict)
        self.assertIsInstance(result["sources"]["items"], list)
        self.assertIsInstance(result["uncertainty"], list)
        self.assertIsInstance(result["operation_results"], dict)
        self.assertEqual(result["custom_list"], [])
        self.assertEqual(result["custom_dict"], {"nested": []})
        self.assertEqual(set(result), set(contract) | {"case_id"})

    def test_source_quote_must_be_exact(self) -> None:
        records = copy.deepcopy(self.envelope["records"])
        records[0]["evidence"][0]["quote"] = "An invented quotation"
        with self.assertRaises(SchemaError):
            validate_records(records, self.documents, self.case["case_id"],
                             self.workorder["task_id"], self.task_text)


if __name__ == "__main__":
    unittest.main()
