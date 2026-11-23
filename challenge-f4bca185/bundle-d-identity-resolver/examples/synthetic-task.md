# Synthetic task (DEMONSTRATION ONLY, not an official case)

Clean and standardize the attached synthetic literature-extraction records.

Requirements:

1. Canonicalize material/metric names (aliases like TiO2 / titanium dioxide / titania).
2. Identify repeated extractions (same row extracted twice) versus independent repeated experiments; never merge the latter.
3. Never merge across different sources, samples, phases, dopants or experimental contexts.
4. Never average conflicting measured values; keep both and queue them for review.
5. Convert units where the unit is known; keep original raw values; leave missing/unknown units null and flag them.
6. Produce cleaned records, a duplicate report, a review queue, a rule-coded change log, an audit and result.json honoring the output_contract in the case file.
