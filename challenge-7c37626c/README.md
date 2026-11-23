# 公式解析与数学推理（challenge-7c37626c）— five independent skills

Five mutually independent skill bundles for the "formula parsing and
mathematical reasoning" reading challenge. Each has a different engineering
center of gravity; they share no code or files. Each bundle contains its own
`SKILL.md` (valid YAML frontmatter), `scripts/`, `references/`, and a
synthetic end-to-end example under `examples/` (run
`examples/run_synthetic_example.sh`; all fixtures are synthetic, not platform
cases).

| bundle | center of gravity | what it delivers |
|-|-|-|
| [mml-forensics](mml-forensics/) | 上游数据真实性 (upstream source authenticity) | forensic verification of publisher XML / MathML / PDF layers: hashes, well-formedness, fragment salvage, structural-signature cross-checks, verified formula inventory |
| [quantity-audit](quantity-audit/) | 数值物理 (numerical physics) | recomputation audit of every checkable published number: exact SI dimensional engine, dimensionless-exponent enforcement, residuals vs reported values, PASS/MISMATCH/DIM_MISMATCH/BLOCKED ledger |
| [derivation-cartography](derivation-cartography/) | 推理结构 (reasoning structure) | formula dependency graph from citation + symbol-flow edges, assumption/approximation radar, fail-closed completeness gate for derivation step skeletons, Mermaid + PNG map |
| [render-review-studio](render-review-studio/) | 下游渲染工程 (downstream rendering) | strict mathtext PNG rendering of transcriptions, side-by-side sheets against source pages, variable-table rendering, fail-closed review pack |
| [contract-gatekeeper](contract-gatekeeper/) | 过程质量控制 (process quality control) | input triage with early honest-partial banking, output_contract linter with null-reason rule, fail-closed finalize gate, audit trail; missing-evidence branches as first-class outcomes |

All bundles follow the Harbor runtime contract: read `/input/case.json` +
`task.md`, work in `/app/work`, deliver `/app/output/result.json` with the
original `case_id` and every `output_contract` field, and report
`partial` / `insufficient_evidence` honestly with named limits. Each
`GITHUB_URL.txt` points at its directory in this repository.
