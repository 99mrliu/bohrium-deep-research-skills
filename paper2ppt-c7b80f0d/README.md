# paper2ppt-c7b80f0d — 论文转学术 PPT (three independent Skill bundles)

Works for the Bohrium Playground challenge **论文转学术 PPT** (`ppt-c7b80f0d`,
https://play.bohrium.com/challenge/ppt-c7b80f0d). The task: an Agent-callable
Skill that turns a research paper (PDF) into an editable, template-conformant,
evidence-traceable academic slide deck under the official DeepSeek Harness
(64 model requests, 900 s, `/input/case.json` → `/app/output/result.json`).

Three deliberately **independent and uncoupled** directions, each a
self-contained Skill bundle (own `SKILL.md`, scripts, references, examples):

| Directory | Skill | Direction |
|-|-|-|
| `a-safe-harbor-delivery/` | `ppt-safe-harbor-delivery` | **Budget-aware always-valid delivery protocol.** Scaffold a complete, openable, honestly-partial deliverable set in the first minutes, then upgrade slide-by-slide under explicit time/request checkpoints (P0–P4), keeping the checkpoint invariant that `/app/output` is always a valid submission, and finish with a mandatory render-verify pass. |
| `b-evidence-fidelity-gate/` | `ppt-evidence-fidelity-gate` | **Quote-gated, machine-audited evidence fidelity.** Every slide statement carrying a number, unit, method name, or conclusion must be backed by a verbatim quote from the extracted paper text; a deterministic auditor extracts all deck text and checks numbers/units/figure-table references/quotes against the paper fact pool, blocking delivery until every finding is fixed or dispositioned. |
| `c-declarative-spec-compiler/` | `ppt-spec-compiler` | **Declarative slide-spec compiler.** The agent hand-writes exactly one artifact, `deck.spec.json` (one claim per slide, evidence locators, notes); a deterministic zero-dependency compiler performs all mechanical work — schema validation, bullet caps, overflow-to-backup, text-fit estimation, evidence footers, aspect-preserving images, notes, template/master inheritance (or a disclosed stdlib backend), PDF/PNG previews — and records every decision in `compile_report.json`. |

Each bundle was smoke-tested locally end-to-end (mock paper PDF via
matplotlib, deck validity verified with python-pptx, graceful degradation
paths exercised). No prepared answers or official case outputs are included;
the platform runs the Skills on its own fixed cases.

Authoring session: 2026-11, SciMaster harness.
