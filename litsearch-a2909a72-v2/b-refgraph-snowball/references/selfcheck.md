# Pre-submission selfcheck — refgraph-snowball

Run through this list before finalizing any case. Every item is verifiable
from files, not memory.

## Contract

- [ ] `result.json` exists under `/app/output` and passes
      `make_result.py --validate` with zero errors.
- [ ] `case_id` in `result.json` equals the one in `/input/case.json`.
- [ ] Every field named by `output_contract` is present and points to a real
      file (or holds real content).
- [ ] `status=success` only when `uncertainty` is empty; otherwise `partial`
      with concrete notes (unmatched seeds, unresolved-reference counts,
      zero-density graph, missing tools).

## Graph integrity

- [ ] `seed_origin` in the digest is what you expect: explicit seeds were
      actually matched (`seeds_matched` non-empty, `seeds_unmatched` empty),
      or derived seeds are acknowledged in `uncertainty`.
- [ ] Every edge in `graph.json` was spot-checked against the source
      snapshot's reference list for at least the seed's own edges.
- [ ] Every non-seed candidate in `candidates.md` shows hop and direction;
      its `score_breakdown` components sum to its total.
- [ ] `unresolved_references.md` reason counts were read; material counts are
      copied into `uncertainty`.

## Authenticity

- [ ] No candidate, edge, or ledger entry was edited by hand; every change
      came from an engine re-run after fixing inputs (seeds, corpus files).
- [ ] `evidence/evidence_index.json` covers every file that was under
      `/input` and `/app/work/corpus`.
- [ ] Agent-fetched responses (if any) were saved raw and unmodified under
      `/app/work/corpus`.

## Retrieval quality

- [ ] The question shown in `search_report.md` is the actual research
      question (not a contract heading).
- [ ] Top-5 of `candidates.md` were eyeballed and are plausible neighbours of
      the seed set.
- [ ] If a seed shows zero resolvable references, that is stated as a gap —
      not smoothed over.

## Honesty

- [ ] No live-coverage, novelty or "latest publication" claim unless a search
      tool actually ran in this session and its raw response is in the corpus.
- [ ] Missing metadata is `null` in JSON, "—" in Markdown; nothing was guessed.
