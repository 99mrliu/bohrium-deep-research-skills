# Synthetic executable example

Run from any directory:

```bash
bash /path/to/algebra-certificate/examples/synthetic/run.sh
```

Or run `bash examples/synthetic/run.sh` from the bundle root. Use `PYTHON=/path/to/python` to select a Python containing the `sympy` dependency from `requirements.txt`.

This test is **fully synthetic and is not formal/platform data**. Its math was authored as a test fixture, not extracted from C01/C02/C03 or reverse-engineered from any case answer:

1. `E1-valid-expansion` is valid and must be `symbolic_equal`.
2. `C2-invalid-cancellation-at-zero` attempts `x**2/x -> x` with only `x real`. Zero satisfies the declared assumptions; the left side is undefined while the right side is zero, producing a concrete counterexample despite simplification hiding the denominator. The status must be `falsified` and domain errors remain visible.
3. `L3-invalid-real-log-power` attempts `log(x**2) -> 2*log(x)` over all real `x`. A negative real assignment gives unequal values (in the real interpretation, the target is not defined); this is not repaired by a few positive numerical samples.

The example first creates an early typed partial `result-initial.json`, then runs independent checks and finalization. Since required derivations are falsified, final `result.json` is fail-closed with status `failed`, never success.

It then runs a **pure graceful-unavailability test** through `--simulate-no-sympy`. The resulting `certificate-unavailable.json` has overall status `unavailable`; its steps are undetermined, and `result-unavailable.json` is partial. This option invokes the real unavailable-result path without uninstalling SymPy or changing the environment.

Generated files are under `examples/synthetic/output/`:

- `certificate.json`: structured local verdicts, assumptions, domain errors, symbolic attempts, and counterexamples.
- `derivation.md`: human-readable certificate with separate paper-explicit and reader-reconstructed sections (the labels are schema demonstrations; no real paper exists).
- `result.json`: exact synthetic dynamic output contract.
- `result-initial.json`: early partial artifact.
- `certificate-unavailable.json`, `derivation-unavailable.md`, and `result-unavailable.json`: graceful dependency test artifacts.

For an actual C02 no-formula paper, do not copy these equations. Follow SKILL.md: inspect the source, author `derivation.json` with no steps and `status: "insufficient_evidence"`, author a missing-derivation report, and remain non-success.
