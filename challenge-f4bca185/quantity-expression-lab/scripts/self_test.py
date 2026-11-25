#!/usr/bin/env python3
"""Stdlib self-tests for the typed compiler. No network, clock or randomness."""
import sys
import unittest
from decimal import Decimal

sys.dont_write_bytecode = True
from quantity_core import (
    NumberConvention, Quantity, QuantityError, RoundingPolicy, UnitFactor,
    convert_quantity, parse_number, parse_quantity,
)
from quantity_expression_lab import contract_fields


class CompilerTests(unittest.TestCase):
    def test_affine_celsius_to_kelvin(self):
        result = convert_quantity(parse_quantity("25 °C"), "K", RoundingPolicy("decimal_places", 2))
        self.assertEqual(result.expression, "298.15 K")
        self.assertEqual(result.trace["source_dimension"], {"temperature": 1})

    def test_reverse_affine_and_affine_uncertainty(self):
        result = convert_quantity(parse_quantity("100 °C"), "°F", RoundingPolicy("decimal_places", 2))
        self.assertEqual(result.expression, "212 °F")
        uncertainty = convert_quantity(parse_quantity("20 ± 0.5 °C"), "K", RoundingPolicy("decimal_places", 2))
        self.assertEqual(uncertainty.expression, "293.15±0.5 K")

    def test_compound_si_prefix_conversion(self):
        result = convert_quantity(parse_quantity("1 mmol L^-1 min^-1"),
                                  "µmol L^-1 s^-1", RoundingPolicy("significant_figures", 6))
        self.assertEqual(result.expression, "16.6667 µmol L^-1 s^-1")
        self.assertEqual(result.quantity.unit.dimension, {"amount": 1, "length": -3, "time": -1})

    def test_molar_and_pressure_prefixes(self):
        result = convert_quantity(parse_quantity("1 mM"), "mol/L", RoundingPolicy("none", 0))
        self.assertEqual(result.expression, "0.001 mol/L")
        pressure = convert_quantity(parse_quantity("1000 mbar"), "bar", RoundingPolicy("none", 0))
        self.assertEqual(pressure.expression, "1 bar")

    def test_interval_affine(self):
        result = convert_quantity(parse_quantity("10–20 °C"), "K", RoundingPolicy("decimal_places", 2))
        self.assertEqual(result.expression, "283.15–293.15 K")

    def test_negative_multiplier_reverses_interval(self):
        quantity = Quantity("synthetic", False, Decimal(2), Decimal(4), None,
                            UnitFactor("negative-test", {"length": 1}, Decimal(-2)))
        result = convert_quantity(quantity, "m", RoundingPolicy("none", 0))
        self.assertEqual(result.values, (Decimal(-8), Decimal(-4)))
        self.assertTrue(result.trace["interval_reversed_for_negative_multiplier"])

    def test_unicode_minus_uncertainty_and_scientific(self):
        result = convert_quantity(parse_quantity("−1.2e3 ± 2 Pa", NumberConvention("en-US")), "kPa")
        self.assertEqual(result.expression, "−1.2±0.002 kPa".replace("−", "-"))

    def test_ambiguous_decimal_rejected(self):
        with self.assertRaises(QuantityError) as caught:
            parse_number("1,234")
        self.assertEqual(caught.exception.code, "ambiguous_decimal")

    def test_region_disambiguates(self):
        self.assertEqual(parse_number("1,234", NumberConvention("en-US")), Decimal("1234"))
        self.assertEqual(parse_number("1,234", NumberConvention("de-DE")), Decimal("1.234"))

    def test_unknown_unit_rejected(self):
        with self.assertRaises(QuantityError) as caught:
            parse_quantity("12 furlong/fortnight")
        self.assertEqual(caught.exception.code, "unknown_unit")

    def test_missing_never_zero(self):
        for value in ("", "NA", "not reported", "—"):
            with self.assertRaises(QuantityError) as caught:
                parse_quantity(value)
            self.assertEqual(caught.exception.code, "missing_value")

    def test_dimension_mismatch_rejected(self):
        with self.assertRaises(QuantityError) as caught:
            convert_quantity(parse_quantity("1 s"), "K")
        self.assertEqual(caught.exception.code, "dimension_mismatch")

    def test_output_contract_shapes(self):
        self.assertEqual(contract_fields(["answer", {"name": "sources"}]), ["answer", "sources"])
        self.assertEqual(contract_fields({"answer": {"type": "string"}}), ["answer"])
        wrapped = {"schema": {"properties": {"answer": {"type": "string"}, "rows": {"type": "array"}}}}
        self.assertEqual(contract_fields(wrapped), ["answer", "rows"])
        self.assertEqual(contract_fields({"fields": ["case_id", "status"]}), ["case_id", "status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
