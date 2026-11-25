#!/usr/bin/env python3
"""Standard-library unit tests for rule_spec_compiler."""
import decimal
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
MODULE_PATH = Path(__file__).with_name("rule_spec_compiler.py")
SPEC = importlib.util.spec_from_file_location("rule_spec_compiler", MODULE_PATH)
compiler = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(compiler)


class CompilerTests(unittest.TestCase):
    def test_explicit_decimal_and_thousands(self):
        rule = {"decimal": ",", "thousands": "."}
        self.assertEqual(compiler.parse_decimal("1.234,50", rule), decimal.Decimal("1234.50"))
        self.assertEqual(compiler.decimal_text(compiler.parse_decimal("1.234,50", rule)), "1234.5")
        with self.assertRaises(ValueError):
            compiler.parse_decimal("1,234", {"decimal": "."})

    def test_percent_requires_declaration(self):
        with self.assertRaises(ValueError):
            compiler.parse_decimal("25%", {})
        self.assertEqual(compiler.parse_decimal("25%", {"allow_percent": True}), decimal.Decimal("0.25"))

    def test_range_is_canonical_and_never_swapped(self):
        self.assertEqual(compiler.normalize_range_value("1.0–2.50", {}), "1..2.5")
        with self.assertRaises(ValueError):
            compiler.normalize_range_value("9..2", {})

    def test_unit_conversion_is_declared_and_dimensional(self):
        self.assertEqual(compiler.conversion_factor("g", "mg"), decimal.Decimal(1000))
        self.assertEqual(compiler.conversion_factor("mmol/l", "umol/l"), decimal.Decimal(1000))
        self.assertEqual(compiler.conversion_factor("mM", "uM"), decimal.Decimal(1000))
        self.assertEqual(compiler.conversion_factor("M", "uM"), decimal.Decimal(1000000))
        self.assertEqual(compiler.split_unit_value("2 mmol/l", {}), (decimal.Decimal(2), "mmol/l"))
        with self.assertRaises(ValueError):
            compiler.conversion_factor("M", "m")
        with self.assertRaises(ValueError):
            compiler.conversion_factor("g", "ml")

    def test_rule_conflicts_hold_every_member(self):
        engine = compiler.RulesEngine()
        specs = [
            ({"type": "parse_number", "field": "x", "decimal": "."}, "case.json", "/rules/0"),
            ({"type": "parse_number", "field": "x", "decimal": ","}, "override.json", "/rules/0"),
        ]
        rules = compiler.expand_directives(specs, engine)
        self.assertEqual(len(rules), 2)
        self.assertTrue(all(not rule["enabled"] for rule in rules))
        self.assertEqual(engine.review[0]["code"], "RULE_CONFLICT")
        self.assertEqual(len(engine.review[0]["rule_ids"]), 2)

    def test_identical_rules_merge_provenance(self):
        engine = compiler.RulesEngine()
        raw = {"type": "trim_whitespace", "field": "x"}
        rules = compiler.expand_directives([(raw, "case.json", "/rules/0"), (raw, "task.md", "#L2")], engine)
        self.assertEqual(len(rules), 1)
        self.assertEqual(len(rules[0]["provenance"]), 2)

    def test_json_patch_and_invalid_operation(self):
        root = {"case": {"x": [1, 2]}, "rules": []}
        patched = compiler.apply_json_patch(root, [{"op": "add", "path": "/case/x/1", "value": 9}])
        self.assertEqual(patched["case"]["x"], [1, 9, 2])
        self.assertEqual(root["case"]["x"], [1, 2])
        with self.assertRaises(ValueError):
            compiler.apply_json_patch(root, [{"op": "test", "path": "/case/x", "value": [1, 2]}])

    def _contracts_all(self):
        direct = {"a": "object", "b": {"required": False}}
        listed = ["a", "b"]
        objects = [{"name": "a"}, {"name": "b", "required": False}]
        wrapped = {"required": ["a"], "fields": {"a": {}, "b": {}}}
        properties = {"required": ["a"], "properties": {"a": {}, "b": {}}}
        return direct, listed, objects, wrapped, properties

    def test_output_contract_shapes(self):
        direct, listed, objects, wrapped, properties = self._contracts_all()
        self.assertEqual(compiler.normalize_contract(direct), compiler.normalize_contract(properties))
        self.assertEqual(compiler.normalize_contract(listed),
                         [{"name": "a", "required": True}, {"name": "b", "required": True}])
        self.assertEqual(compiler.normalize_contract(objects),
                         [{"name": "a", "required": True}, {"name": "b", "required": False}])
        self.assertEqual(compiler.normalize_contract(wrapped),
                         [{"name": "a", "required": True}, {"name": "b", "required": False}])
        object_list_wrapper = {"required": ["a"], "fields": [{"name": "a"}, {"name": "b"}]}
        self.assertEqual(compiler.normalize_contract(object_list_wrapper),
                         [{"name": "a", "required": True}, {"name": "b", "required": False}])

    def test_nonfinite_json_is_rejected(self):
        with self.assertRaises(ValueError):
            json.loads("NaN", parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        self.assertIsNone(compiler.safe_json(float("inf")))

    def test_json_record_wrappers(self):
        for key in compiler.FORMATS:
            self.assertEqual(compiler.load_json_records({key: [{"x": 1}]}), [{"x": 1}])
        with self.assertRaises(ValueError):
            compiler.load_json_records({"unexpected": []})

    def test_plan_digest_is_canonical(self):
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(compiler.digest(left), compiler.digest(right))


if __name__ == "__main__":
    unittest.main(verbosity=2)
