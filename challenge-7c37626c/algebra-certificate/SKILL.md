---
name: algebra-certificate
description: Machine-check explicit local algebraic derivation transitions with SymPy, enforce domain and side-condition licenses, find assumption-respecting counterexamples, separate paper statements from reader reconstruction, and fail closed into an exact runtime output contract.
---

# Algebra Certificate

Use this skill to audit **what permits each transition** in a derivation. It does not assess citation graphs, bibliometrics, or an answer produced only by substituting numbers into a formula. A final numerical answer never licenses an unverified intermediate transition.

## Runtime and isolation

The runtime provides `/input` (including source paper files), `/input/task.md`, `/app/work`, and `/app/output`. Keep intermediate authoring in `/app/work` and deliverables in `/app/output`. This bundle is standalone: its scripts import only the Python standard library and the declared `sympy` dependency; they never import another bundle or shared helper.

1. **Start fail-closed.** Immediately run:

   ```bash
   python scripts/algebra_certificate.py init-result \
     --task /input/task.md --input-dir /input --output /app/output/result.json
   ```

   This writes `case_id`, every field currently named by dynamic `output_contract.required_fields`, values conforming to `field_types`, and a partial status drawn from `status_enum`. Re-read the task before finalization because its contract may change.

2. **Read the paper before checking anything.** Inspect the complete supplied source, not merely an abstract or table. Record formula source locators (MathML node/XML path/equation number and local context). Distinguish the paper's wording from the reader's explanatory derivation.
   - **C01 and C03:** extract transitions from the supplied C01/C03 **MathML sources**, preserving expressions and locators. Do not replace a difficult expression with a visually similar invented one.
   - **C02:** when the supplied paper/source contains no formulas, do not reverse-engineer equations from prose, plots, numerical tables, or expected answers. Author an honest `derivation_report.json` with `status: "insufficient_evidence"` and source inspection notes. Its `derivation.json` still must exist, with empty `steps` and top-level `status: "insufficient_evidence"`; finalization remains non-success.
   - Never fabricate a formula, source locator, mathematical premise, or certificate to fill a schema.

3. **Author the derivation yourself.** Write `/app/work/derivation.json` as an actual mathematical audit object; the checker does not write it for the agent. Each step needs:

   ```json
   {
     "id": "S1",
     "lhs": "(x + 1)**2",
     "rhs": "x**2 + 2*x + 1",
     "operation": "expand",
     "justification": "Distribute the square and collect equal terms.",
     "source_locator": "MathML equation 3, mrow[2]",
     "assumptions": ["x real"],
     "domain": [],
     "dependencies": [],
     "origin": "paper_explicit",
     "required": true
   }
   ```

   `rhs`/`lhs` may also be named `target`/`source`. Use `origin: "paper_explicit"` only for a transition actually present in the paper; otherwise use `reader_reconstruction`. A reader reconstruction is not attributable to the paper. Dependencies are prior step IDs only. See `references/certificate-semantics.md` and `references/assumption-vocabulary.md`.

4. **Run the independent checker.** Install only the declared dependency when necessary (`python -m pip install -r requirements.txt`), then run:

   ```bash
   python scripts/algebra_certificate.py check \
     --derivation /app/work/derivation.json \
     --certificate /app/output/certificate.json \
     --derivation-md /app/output/derivation.md
   ```

   SymPy performs safe AST parsing and symbolic difference simplification. Division/cancellation requires nonzero denominators/cancelled factors. Real square roots, logarithms, and applicable powers require their domain declarations. Inconclusive symbolic checks trigger deterministic, assumption-respecting concrete sampling for **counterexamples only**; numeric agreement is never proof. `False` from a SymPy Boolean is not silently treated as mathematical falsity: unknown/unimplemented truth values remain undetermined and are explained. Domain errors cannot pass.

5. **Interpret results conservatively.** Step verdicts are `symbolic_equal`, `falsified`, `undetermined`, `invalid_operation`, or `missing_license`. `missing_license` means a side condition was not established; it does not mean the identity is true. Any required step not equal blocks success. In particular, falsified, undetermined, unavailable, invalid, and missing-license results all fail closed. Optional steps are reported but only `required: true` steps gate success. Empty/insufficient-evidence derivations are undetermined, never vacuously valid.

6. **Author answers and finalize.** Write `/app/work/answers.json` with the task-facing fields, including an evidence-qualified answer for C02 if needed. Then run:

   ```bash
   python scripts/algebra_certificate.py finalize \
     --task /input/task.md --input-dir /input \
     --answers /app/work/answers.json \
     --certificate /app/output/certificate.json \
     --derivation-md /app/output/derivation.md \
     --output /app/output/result.json
   ```

   The finalizer maps agent-authored values and certificate results into exactly `case_id` plus the current required output-contract fields, coerces only when safe, and selects success only when every required transition is certified. It deliberately does not invent missing agent answers. Preserve `/app/output/certificate.json`, `/app/output/derivation.md`, and `/app/output/result.json`.

## Required reading and self-check

Read `references/certificate-semantics.md` for verdict precedence, proof limits, dependency checks, graceful unavailability, and finalization behavior. Read `references/assumption-vocabulary.md` for accepted declarations. Before finishing, confirm:

- The paper was read and C01/C03 expressions came from their MathML sources; C02 has no invented derivation.
- Paper-explicit and reader-reconstructed steps are visibly separated in `derivation.json`, `certificate.json`, and `derivation.md`.
- Every required step has both expressions, operation, justification, locator, assumptions/domain, dependencies, and origin.
- A local identity is not certified solely by samples, and cancellation/log/root/power licenses are explicit.
- `result.json` contains `case_id` and all dynamically required fields with correct types and an allowed status; missing evidence cannot become success.
- Dependency errors, parser failures, and unavailable SymPy are visible rather than hidden.

## Executable synthetic example

From this bundle directory run:

```bash
bash examples/synthetic/run.sh
```

The example is entirely synthetic and is not formal/platform evaluation data. It uses pre-authored valid expansion plus deliberately invalid cancellation-at-zero and real-log-domain transitions. It writes a real certificate, Markdown derivation, and failed/partial `result.json` under `examples/synthetic/output/`. It also runs a pure graceful-unavailability test using `--simulate-no-sympy`; this is a test hook and never produces a pass.
