#!/usr/bin/env python3
"""Standard-library regressions for visual evidence atlas release policies."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "atlas_tool.py"
SPEC = importlib.util.spec_from_file_location("atlas_tool_under_test", MODULE_PATH)
atlas_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(atlas_tool)


class AtlasReleaseRegressionTests(unittest.TestCase):
    def setUp(self):
        with (ROOT / "examples" / "synthetic" / "atlas.json").open(encoding="utf-8") as handle:
            self.atlas = json.load(handle)
        self.source_text = (ROOT / "examples" / "synthetic" / "source.txt").read_text(encoding="utf-8")

    def audit(self, atlas=None):
        return atlas_tool.validate_atlas(
            self.atlas if atlas is None else atlas,
            self.source_text,
            image_root=None,
        )

    @staticmethod
    def claim(atlas, claim_id):
        return next(item for item in atlas["visual_claims"] if item["claim_id"] == claim_id)

    @staticmethod
    def region(atlas, region_id):
        return next(item for item in atlas["regions"] if item["region_id"] == region_id)

    def make_otherwise_complete(self, atlas):
        atlas["pages"][0]["layout"]["columns"] = 1
        atlas["pages"][0]["layout"]["reading_order"] = "certain"
        self.claim(atlas, "claim-cell-measured-intervention-23")["body_corroboration"] = {
            "state": "corroborated",
            "source_anchor": {"start": 665, "end": 667, "quote": "23"},
        }
        return atlas

    def test_unmodified_example_is_partial_with_reviewed_direct_cell(self):
        audit = self.audit()
        self.assertEqual([], audit["errors"])
        self.assertEqual("partial", audit["status"])
        cell = next(item for item in audit_warnings(audit) if item["code"] == "BODY_CORROBORATION_NOT_REPORTED")
        self.assertEqual("not_reported", cell["state"])
        self.assertFalse(any(item["code"] == "UNRESOLVED_CAPTION_ONLY_CELL" for item in audit["warnings"]))

    def test_impossible_bbox_is_an_error_and_failed(self):
        self.region(self.atlas, "reg-panel-b")["bbox"] = [690, 105, 400, 390]
        audit = self.audit()
        self.assertEqual("failed", audit["status"])
        self.assertTrue(any("impossible/reversed/negative coordinates" in error for error in audit["errors"]))

    def test_missing_corroboration_is_explicit_and_partial(self):
        atlas = self.make_otherwise_complete(self.atlas)
        self.claim(atlas, "claim-panel-b-intervention")["body_corroboration"] = {
            "state": "missing",
            "source_anchor": None,
        }
        audit = self.audit(atlas)
        self.assertEqual("partial", audit["status"])
        self.assertEqual([], audit["errors"])
        self.assertTrue(any(item["code"] == "UNRESOLVED_MISSING" and item["state"] == "missing" for item in audit["unresolved_claims"]))

    def test_every_decisive_bad_subject_region_state_blocks_review_and_complete(self):
        for state in ("missing", "unreadable", "not_reported", "conflict"):
            with self.subTest(state=state):
                atlas = self.make_otherwise_complete(self.atlas)
                self.region(atlas, "reg-panel-b")["evidence_state"] = state
                audit = self.audit(atlas)
                self.assertEqual([], audit["errors"])
                self.assertEqual("partial", audit["status"])
                unresolved = [item for item in audit["unresolved_claims"] if item["claim_ids"] == ["claim-panel-b-intervention"]]
                self.assertEqual(1, len(unresolved))
                self.assertEqual(f"UNRESOLVED_{state.upper()}", unresolved[0]["code"])
                self.assertEqual(state, unresolved[0]["state"])
                self.assertIn("reg-panel-b", unresolved[0]["message"])
                claim = self.claim(atlas, "claim-panel-b-intervention")
                regions = {item["region_id"]: item for item in atlas["regions"]}
                resolution, _ = atlas_tool.resolve_claim(claim, regions)
                self.assertEqual(f"unresolved_{state}", resolution)
                self.assertNotEqual("reviewed_corroborated", resolution)

    def test_unreadable_table_cell_region_blocks_otherwise_direct_cell(self):
        atlas = self.make_otherwise_complete(self.atlas)
        self.region(atlas, "reg-cell-measured-intervention")["evidence_state"] = "unreadable"
        audit = self.audit(atlas)
        self.assertEqual("partial", audit["status"])
        self.assertTrue(any(
            item["code"] == "UNRESOLVED_UNREADABLE"
            and item["claim_ids"] == ["claim-cell-measured-intervention-23"]
            for item in audit["unresolved_claims"]
        ))

    def test_main_and_supplemental_pdfs_may_both_have_page_zero(self):
        supplemental = copy.deepcopy(self.atlas["pages"][0])
        supplemental["page_id"] = "synth-supplement-page-000"
        supplemental["source_file"] = "fictional-other-supplement.pdf"
        supplemental["pdf_page_index"] = 0
        self.atlas["pages"].append(supplemental)
        audit = self.audit()
        self.assertEqual([], audit["errors"])
        self.assertFalse(any("duplicate pdf_page_index" in error for error in audit["errors"]))

    def test_duplicate_zero_is_rejected_for_same_normalized_source(self):
        self.atlas["pages"][0]["source_file"] = "papers/main.pdf"
        duplicate = copy.deepcopy(self.atlas["pages"][0])
        duplicate["page_id"] = "synth-duplicate-main-page-000"
        duplicate["source_file"] = "./papers/main.pdf"
        self.atlas["pages"].append(duplicate)
        audit = self.audit()
        self.assertEqual("failed", audit["status"])
        self.assertTrue(any(
            "duplicate pdf_page_index 0 for normalized source_file: papers/main.pdf" in error
            for error in audit["errors"]
        ))

    def test_inspected_original_cell_with_identity_is_not_caption_only(self):
        regions = {item["region_id"]: item for item in self.atlas["regions"]}
        claim = self.claim(self.atlas, "claim-cell-measured-intervention-23")
        resolution, reason = atlas_tool.resolve_claim(claim, regions)
        self.assertEqual("reviewed_corroborated", resolution)
        self.assertIn("direct inspection", reason)
        audit = self.audit()
        self.assertFalse(any(item["code"] == "UNRESOLVED_CAPTION_ONLY_CELL" for item in audit["unresolved_claims"]))
        self.assertTrue(any(item["code"] == "BODY_CORROBORATION_NOT_REPORTED" for item in audit["warnings"]))

    def test_not_inspected_cell_is_caption_only(self):
        claim = self.claim(self.atlas, "claim-cell-measured-intervention-23")
        claim["inspection"] = {"status": "not_inspected", "change_record_id": None}
        regions = {item["region_id"]: item for item in self.atlas["regions"]}
        resolution, reason = atlas_tool.resolve_claim(claim, regions)
        self.assertEqual("unresolved_caption_only_cell", resolution)
        self.assertIn("not agent-attested inspected", reason)
        audit = self.audit()
        self.assertEqual("partial", audit["status"])
        self.assertTrue(any(item["code"] == "UNRESOLVED_CAPTION_ONLY_CELL" for item in audit["unresolved_claims"]))

    def test_unclear_cell_identity_is_caption_only_even_when_attested(self):
        for row_label, column_label in (("", "Intervention"), ("Measured", " "), ("Control", "Intervention")):
            with self.subTest(row_label=row_label, column_label=column_label):
                atlas = copy.deepcopy(self.atlas)
                cell_region = self.region(atlas, "reg-cell-measured-intervention")
                cell_region["row_label"] = row_label
                cell_region["column_label"] = column_label
                claim = self.claim(atlas, "claim-cell-measured-intervention-23")
                regions = {item["region_id"]: item for item in atlas["regions"]}
                resolution, reason = atlas_tool.resolve_claim(claim, regions)
                self.assertEqual("unresolved_caption_only_cell", resolution)
                self.assertIn("identity is unclear", reason)

    def test_complete_positive_control(self):
        audit = self.audit(self.make_otherwise_complete(self.atlas))
        self.assertEqual([], audit["errors"])
        self.assertEqual([], audit["warnings"])
        self.assertEqual([], audit["unresolved_claims"])
        self.assertEqual("complete", audit["status"])


def audit_warnings(audit):
    return audit["warnings"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
