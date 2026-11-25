# Tests

All test fixtures use the bundled SYNTHETIC graph; none represents an official answer or biological result.

- `scripts/test_negative.py` performs two complete invalid builds. It passes only when both builds return nonzero: inhibition retyped as material flow and catalysis given an unsupported measurement→chart endpoint.
- `scripts/test_semantics.py` checks unmarked and explicitly marked cycles, acyclic feedback rejection, generic activation marker rejection, disconnected required chart, exact branch/join declarations, phase cycles, and nonexistent CSV headers.
- `scripts/patch_svg.py` is tested with `verification/semantic-reaction-network/edit-instruction.json`: one exact text fragment changes under `node-enzyme`, with no SVG rebuild and all unmodified IDs/styles preserved.

Run commands and outcomes are recorded in `../verification/semantic-reaction-network/test-report.md`. Use `PYTHONDONTWRITEBYTECODE=1` to keep the text-only distribution free of bytecode caches.
