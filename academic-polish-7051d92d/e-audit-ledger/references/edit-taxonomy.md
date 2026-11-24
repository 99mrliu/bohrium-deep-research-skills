# Edit taxonomy — 14 types (audit-trail-polish)

Every ledger entry carries `types` from this vocabulary (one or more). The
vocabulary is enforced by `scripts/ledger.py`; unknown types are rejected.

## The 14 types

| # | type | definition | typical signal |
|---|------|-----------|----------------|
| 1 | `grammar` | morphological or inflectional error not covered by a narrower type | wrong verb form, wrong plural |
| 2 | `syntax` | phrase/clause structure: dangling or misplaced modifiers, broken parallelism, faulty coordination | "Using X, the results were…" |
| 3 | `tense-voice` | tense inconsistent with section convention; unjustified voice switch | present tense in Methods |
| 4 | `agreement` | subject–verb or pronoun–antecedent disagreement | "data was", "cultures was" |
| 5 | `article-preposition` | missing/wrong article or preposition | "at wavelength of", "in the other hand" |
| 6 | `punctuation` | comma/semicolon/colon/hyphen misuse or omission | missing comma before "then" |
| 7 | `terminology` | term deviates from termbase or field convention; inconsistent term choice | "KF" vs "Kalman filter" drift |
| 8 | `register` | colloquial, promotional or otherwise off-genre wording | "a bunch of", "amazing results" |
| 9 | `conciseness` | wordy phrases, redundancy, needless nominalization | "due to the fact that" |
| 10 | `hedging` | claim strength mismatched to evidence (over- or under-claim) | "prove", "perfect for all" |
| 11 | `consistency` | spelling/capitalization/hyphenation/number-format drift across the text | "modeling" vs "modelling" |
| 12 | `structure` | sentence split/merge at clause level, reordering inside a sentence for information flow | long run-on re-cut |
| 13 | `translation` | residue of source-language idiom in translated text | Chinglish calques |
| 14 | `other` | anything real that fits no type above — reason must say why | — |

## Decision order (pick the narrowest applicable type first)

1. Is a protected token involved? → fix the token handling first; the edit type
   still describes the language change.
2. `agreement` / `article-preposition` / `tense-voice` / `punctuation` beat
   generic `grammar` — always prefer the narrow type.
3. `hedging` applies only when claim **strength** changes; a pure rewording of
   equal strength is `register` or `conciseness`.
4. `structure` only for within-sentence re-cutting; **sentence-level merges
   across sids are forbidden** (see below).
5. `other` is a last resort and its reason must justify why no type fits.

## Minimal-edit threshold

An edit is worth a ledger entry only if it fixes at least one of:

- a real error (types 1–6, 13);
- a convention violation with a cited basis (types 3, 7, 8, 10, 11);
- a readability defect whose revised version is measurably shorter or clearer
  (types 9, 12) **without** changing meaning, strength, or scope.

If you cannot name the defect, do not make the edit. "It sounds better" is not
a defect (see the vacuous-reason blacklist in `ledger.py`).

## Forbidden operations

- Merging two frozen sentences into one, splitting one sid into two outputs, or
  reordering sids (breaks C01; the exporter will refuse).
- Edits whose `original` does not equal the frozen sentence (breaks C02 anchor).
- Losing, altering or inventing a protected token (C03): numbers+units,
  percentages, p-values/CIs, `[12]`, `(Author, Year)`, `Fig. 2b`, `Eq. (3)`,
  URLs/DOIs/emails.
- Vacuous or sub-threshold reasons (C07): "improve fluency", "优化表达",
  "polish the sentence", reason shorter than 12 characters.
- Rewriting whole paragraphs wholesale and logging them as one `other` edit —
  batch edits per sentence so each change stays reviewable.
