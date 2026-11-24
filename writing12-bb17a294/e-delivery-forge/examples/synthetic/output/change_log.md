# Change Log — 合成示例 / synthetic example (synthetic-delivery-0001)

| Stage | Gate | Result |
|---|---|---|
| render  | `render_bilingual.py`  | bilingual.html + bilingual.pdf + bilingual_page1.png generated; font + preview status logged in `render_qa_log.json` |
| census  | `census_coverage.py`   | PASS — 7/7 inventory items covered (`coverage_report.json`) |
| contract| `validate_contract.py` | PASS — all 7 explicit contract fields present, referenced files exist (`contract_check.json`) |

Note: `bilingual.pdf` and `bilingual_page1.png` were generated during this run
but are excluded from the shipped bundle as binary runtime artifacts (see
`examples/synthetic/README.md`).
