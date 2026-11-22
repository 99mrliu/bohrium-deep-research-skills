# Evidence strength rubric and wording rules

The grade describes the evidence behind a claim **as the source presents it**; the wording on the slide must not exceed the grade. Grade down whenever in doubt, and record the reason in the card's `notes`.

## Grades

| Grade | Use when | Allowed verbs on slides (EN) | 中文措辞 |
|-|-|-|-|
| `established` | Direct measurement/derivation in this work, adequate controls, stated in results | shows, demonstrates, measures, confirms | 表明、证实、测得 |
| `preliminary` | Limited n, single dataset/condition, ablation-level, or authors hedge | suggests, indicates, we observe | 初步表明、提示 |
| `contextual` | Consistency checks, citations of prior work, background facts | is consistent with, prior work reports | 与……一致、已有研究报道 |
| `speculative` | Hypotheses, future-work claims, mechanistic guesses | may, one hypothesis is | 可能、一种解释是 |

Downgrade triggers: no control/baseline for a comparative claim; single run where variance matters; authors state the limitation themselves; metric computed on a subset; the number comes from a figure you read off a plot (flag `read_from_figure`).

## Forbidden transforms (slide text vs source)

1. **No rounding** — "32.7%" stays "32.7%"; "about one-third" only if the slide cannot fit and the notes keep the exact value.
2. **No causality upgrade** — association or ablation results do not become "X causes Y" unless the design supports it.
3. **No scope widening** — a result on dataset A under condition B is not "the method works"; the slide keeps dataset, condition, split.
4. **No strength upgrade** — `preliminary` evidence never takes "demonstrates".
5. **No attribution blur** — prior work stays attributed ("Smith et al. report"); presenter synthesis is labeled ("our reading of Fig. 2 is …").
6. **No silent omission of conditions** — sample size, threshold, dataset split or uncertainty that changes interpretation stays on the slide or, at minimum, in the notes with a pointer on the slide.
7. **No invented references** — citation numbers/keys on slides must exist in the source's reference list or the case materials.

## Comparative claims need their comparator

"Better", "faster", "state of the art" on a slide require the comparator and the conditions on the same slide: "12% lower error than <baseline> on <dataset> <split>". The audit's number gate checks both numbers.

## Uncertainty display

Error bars, CIs, p-values reported in the source travel with the number when the figure/table shows them; if the source reports none, the slide must not imply precision it does not have (no extra decimals, no "significant").
