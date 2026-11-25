# Pre-submission selfcheck — snapshot-trust-gate

Run through this list before finalizing any case. Every item is verifiable from
files, not memory.

## Contract

- [ ] `result.json` exists under `/app/output` and passes
      `make_result.py --validate` with zero errors.
- [ ] `case_id` in `result.json` equals the one in `/input/case.json`.
- [ ] Every field named by `output_contract` is present and points to a real
      file (or holds real content).
- [ ] `status=success` only when `uncertainty` is empty; otherwise `partial`
      with concrete notes (quarantines, zero-hit terms, missing tools).

## Authenticity

- [ ] `quarantine_report.md` lists every excluded file with a reason code; you
      have read each one and either re-saved (agent files, once) or ledgered it
      (organizer files) in `uncertainty`.
- [ ] No candidate in `candidates.*` was edited by hand; every change came from
      an engine re-run.
- [ ] `evidence/evidence_index.json` covers every `.json`/`.xml` file that was
      under `/input` and `/app/work/corpus`.

## Retrieval quality

- [ ] The question shown in `search_report.md` is the actual research question
      (not a contract heading). If not, fix question extraction at the source.
- [ ] `zero_hit_terms` were copied into `uncertainty` when material.
- [ ] Top-5 of `candidates.md` were eyeballed and are on-topic.

## Honesty

- [ ] No live-coverage, novelty or "latest publication" claim unless a search
      tool actually ran in this session and its raw response is in the corpus.
- [ ] Missing metadata is `null` in JSON, "—" in Markdown; nothing was guessed.
