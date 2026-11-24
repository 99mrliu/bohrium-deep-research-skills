# Change Log -- MINIMAL-AUDIT-001

Synthetic example / 合成示例. Every entry below is a ledger record that a third party can re-check against the frozen source.

## Gates

| Gate | Status | Detail |
|---|---|---|
| C01_sentence_integrity | PASS | 9 frozen sentences, order preserved, refill verified |
| C02_anchor_and_schema | PASS | every applied edit's 'original' equals its frozen sentence |
| C03_protected_tokens | PASS | 9 protected tokens verified across 8 applied edits |
| C04_mandatory_review | PASS | every applied edit carries an accept review; unreviewed edits were rolled back |
| C07_reason_quality | PASS | all applied edits have concrete reasons (>= 12 chars, blacklist-screened) |

## Summary

- sentences: 9
- edits received: 10
- accepted at intake: 9
- applied: 8
- rolled back: 1
- rejected at intake: 1

## Applied edits (8)

### s0001 -- agreement, grammar

- status: `applied` -- reviewed and applied
- original: Cell cultures was maintained at 37 °C in a humidified incubator with 5% CO2 [12].
- revised: Cell cultures were maintained at 37 °C in a humidified incubator with 5% CO2 [12].
- reason: Subject 'cultures' is plural, so the verb must be 'were', not 'was'.
- basis: Subject-verb agreement rule: a plural subject takes a plural verb form.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0002 -- tense-voice

- status: `applied` -- reviewed and applied
- original: The medium is replaced every 48 h and cells were passaged at 80% confluence.
- revised: The medium was replaced every 48 h and cells were passaged at 80% confluence.
- reason: Methods describe completed procedures; present 'is' is shifted to past 'was' for tense consistency with the rest of the sentence.
- basis: Methods-section tense convention: completed experimental steps in past tense.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0003 -- article-preposition

- status: `applied` -- reviewed and applied
- original: The absorbance was measured at wavelength of 450 nm using a microplate reader.
- revised: The absorbance was measured at a wavelength of 450 nm using a microplate reader.
- reason: The singular countable noun 'wavelength' requires the indefinite article 'a' in this context.
- basis: Article usage rule: singular countable nouns take an article when not pluralized or possessive.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0004 -- syntax

- status: `applied` -- reviewed and applied
- original: Using ImageJ software, the images were analyzed to quantify colony formation.
- revised: Using ImageJ software, we analyzed the images to quantify colony formation.
- reason: The introductory phrase 'Using ImageJ software' dangles: its implied agent cannot be 'the images'. Naming the agent 'we' resolves it.
- basis: Dangling-modifier rule: an introductory participial phrase must modify the subject that follows it.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0005 -- register

- status: `applied` -- reviewed and applied
- original: We did a bunch of tests to check whether the treatment worked.
- revised: We performed a series of assays to determine whether the treatment was effective.
- reason: 'did a bunch of tests' and 'worked' are colloquial; they are replaced with formal academic equivalents.
- basis: Academic register guideline: avoid colloquial quantifiers ('a bunch of') and vague verbs ('worked').
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0006 -- hedging

- status: `applied` -- reviewed and applied
- original: These results prove that the new protocol is perfect for all cell types.
- revised: These results suggest that the new protocol is effective for the cell types tested.
- reason: 'prove' and 'perfect for all cell types' claim more than the data support; the claim is hedged to match the evidence scope.
- basis: Hedging guideline: claim strength must match the strength and scope of the evidence.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0007 -- conciseness

- status: `applied` -- reviewed and applied
- original: Due to the fact that the signal was weak at this point in time, the exposure time was increased to 30 s.
- revised: Because the signal was weak, the exposure time was increased to 30 s.
- reason: 'Due to the fact that' and 'at this point in time' are redundant wordy phrases replaced by concise equivalents without meaning change.
- basis: Conciseness rule: replace multi-word connectives with single-word equivalents when meaning is unchanged.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

### s0008 -- punctuation

- status: `applied` -- reviewed and applied
- original: The samples were heated to 95 °C for 10 min then cooled on ice.
- revised: The samples were heated to 95 °C for 10 min, then cooled on ice.
- reason: A comma is required before 'then' when it links two sequential actions in one sentence.
- basis: Comma rule: use a comma before the conjunctive adverb 'then' joining sequential clauses.
- review: **accept** -- Re-read against the frozen sentence: the fix is correct, minimal, and every protected token is preserved.

## Rolled back (rollback is mandatory, not skippable) (1)

### s0009 -- punctuation

- status: `rolled_back_unreviewed` -- no review record for this edit; mandatory review gate rolls it back
- original: Statistical significance was set at p < 0.05, and representative images are shown in Fig. 2.
- revised: Statistical significance was set at p < 0.05; representative images are shown in Fig. 2.
- reason: A semicolon tightens the link between two closely related independent clauses here.
- basis: Semicolon rule: a semicolon may join two closely related independent clauses without a conjunction.
- review: none

## Rejected at intake (1)

### s0009 -- other

- status: `rejected_intake` -- vacuous reason blacklisted: 'improve fluency'
- original: Statistical significance was set at p < 0.05, and representative images are shown in Fig. 2.
- revised: Statistical significance was set at p < 0.05, with representative images in Fig. 2.
- reason: improve fluency
- basis: none given
- review: none

