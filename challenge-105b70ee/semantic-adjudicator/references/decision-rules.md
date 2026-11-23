# Decision rules — accept / reject / status tree

## The accept test (all five must hold before `reported`)

1. **Subject.** The sentence is about the entity the field asks for
   (this paper's sample, not a literature citation, not an industry
   benchmark, not a different material/condition).
2. **Condition.** The value's experimental condition (sample, setting,
   time point, temperature, rate) matches the condition the field
   specifies. If the field names a condition and the sentence names a
   different one → reject this candidate, keep searching.
3. **Unit.** Copied exactly as printed (`mAh g⁻¹`, `%`, `mg cm⁻²`). Never
   converted, never normalized into a different notation.
4. **Statistic.** If the paper prints an error bar, deviation, CI, or
   p-value with the value, it goes into `statistic` verbatim (`± 2`,
   `p < 0.05`, `n = 5`). Absence of a printed statistic → `statistic: null`,
   never invented.
5. **Comparator.** Comparative language (`over`, `than`, `vs`, `相比`,
   `优于`) requires the comparator object in `comparator`
   (`"bare electrode baseline"`). The tooling rejects a comparative quote
   without it.

## Status decision tree

```
searched: field keywords + synonyms + unit strings + Chinese terms
├─ no candidate anywhere (text + tables + captions + SI)
│    → not_reported   notes: terms searched
├─ candidate location found but unreadable (garbled cell, scanned page,
│    broken extraction)
│    → extraction_failed   notes: location + what to check manually
├─ cell explicitly says n.d. / not determined / not reported / "–"
│    → not_reported   notes: quote the cell text
└─ readable candidate(s):
     ├─ one reading passes the accept test
     │    → reported
     ├─ several readings, different conditions
     │    → reported with the condition-matching reading;
     │      other readings listed in notes (they are not a conflict)
     └─ several readings, same quantity + same condition, irreconcilable
          → source_conflict   quote one reading in quote,
            list all readings + locations in notes
```

## Numeric forms — copy, never compute

| Form in paper | `scalar` | Forbidden |
|-|-|-|
| `152 mAh g⁻¹` | `152` | rounding, unit conversion |
| `92–95 %` | `92–95` | taking the midpoint |
| `> 90 %` | `> 90` | dropping the `>` |
| `91.2 ± 0.4 %` | scalar `91.2`, statistic `± 0.4` | merging into one string |
| `p < 0.05` | statistic `p < 0.05` | rewriting as `p = 0.05` |
| `n.d.` in a cell | (none — status not_reported) | inventing a value |

Absent is not zero. A field the paper does not give is `not_reported`,
never `0` and never a "reasonable" value.

## Common traps (reject these candidates)

- **Citation values**: numbers inside a sentence that summarizes other
  work (`Previous studies reported 160 mAh g⁻¹ [12]`).
- **Benchmark/target lines**: `Retention above 90% is a common target` —
  a target, not a result.
- **Wrong condition**: value measured at 1 C when the field asks 0.5 C;
  value after 50 cycles when the field asks 100.
- **Wrong subject**: bare-electrode row when the field asks composite.
- **Cross-page table rows**: a continued-table row read against the wrong
  column header; verify row label + column header in the same quote.

## Claims layering

| kind | test | examples of cues |
|-|-|-|
| `conclusion` | author states it as their result | we demonstrate, our results show, 本文表明 |
| `limitation` | author states a boundary | limited to, remains unreported, 局限 |
| `speculation` | hedged possibility | may, might, suggests, possibly, 可能, 提示, 有望 |

A hedged sentence keeps its hedge words in `text` and is `speculation` —
never promoted to `conclusion`. The checker warns on hedge words inside a
`conclusion` claim.
