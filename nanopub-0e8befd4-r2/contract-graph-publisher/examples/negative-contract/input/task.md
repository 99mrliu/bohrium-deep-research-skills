# SYNTHETIC negative EXACT-key test

This synthetic case intentionally declares `debug_status` in `manifest.output_fields` even though the original `output_contract.fields` does not allow it. The publisher must reject the case, leave no final `result.json` or RDF artifacts, and record an honest error in work. The extra key must never be added to a final result.
