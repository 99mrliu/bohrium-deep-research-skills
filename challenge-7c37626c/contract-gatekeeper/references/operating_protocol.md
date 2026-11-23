# Operating protocol (read once, then follow mechanically)

1. **Triage before thinking.** The first action on a case is
   `triage_case.py`. It classifies the branch and banks the early partial
   `result.json`. If you did anything analytical before triage, the run is
   already non-compliant — go back and bank the partial.
2. **Plan against capability, not wish.** `workplan.py` phases P2/P3 are
   gated by the triage capability matrix. A `False` capability means the
   case cannot support that analysis; do not spend requests simulating it.
   A `repair_first` capability means fix the input layer before using it.
3. **Checkpoint after every phase.** Rewrite `result.json` at each phase
   boundary, even when it is still partial. The runtime budget is 64 model
   requests / 900 s; an un-checkpointed run wastes both when interrupted.
4. **Null-reason rule.** Any contract field left null must be named in
   `uncertainty` with a reason. The linter enforces this mechanically.
5. **Lint before finalizing.** `contract_lint.py` on the interim result;
   fix what it flags; only then run `finalize_gate.py`.
6. **The gate is fail-closed.** Violations downgrade claimed success to
   partial. You may not argue with the gate; you fix the result or accept
   the degraded status with the violations attached.
7. **Missing evidence is a first-class outcome.** On metrics-only branches,
   `insufficient_evidence` with named missing objects is a *successful
   quality outcome*, superior to any fabricated completeness.
