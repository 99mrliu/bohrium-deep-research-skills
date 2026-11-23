# SYNTHETIC example task (not a formal test case)

Clean and standardize the extraction records in the case input: normalize field
names, parse numeric literals, convert units to the SI-coherent defaults, flag
duplicates, and report anomalies plus everything that needs human confirmation.
Every converted value must trace back to rule ids and input coordinates.
Missing data must stay missing.

The accompanying `synthetic-case.json` and `synthetic-extra.csv` are fabricated
inputs exercising: ranges, symmetric ±, scientific notation, composite units,
Celsius affine conversion, ppm, a malformed number, an unknown unit, missing
values, duplicate extractions, comma decimals and an ambiguous comma.
