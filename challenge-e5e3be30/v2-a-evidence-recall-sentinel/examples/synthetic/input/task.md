# SYNTHETIC / 合成示例

Verify the two **questions** in `claims-to-verify.json` against the supplied synthetic paper. This is an executable recall demonstration, not an official answer and not clinical evidence.

The first narrow exact-phrase family intentionally misses an adverse-event table that uses different terminology. A later synonym/table family must recover it. The second question concerns an end point and subgroup that the paper genuinely does not report; the desired result is `insufficient_evidence` with an auditable no-evidence certificate, not `contradicted`.

`run_example.sh` performs source extraction, retrieval, a fixed simulated Agent review, final contract validation, and SVG generation. It also executes a genuinely invalid one-family plan and requires the finalizer to exit 1.
