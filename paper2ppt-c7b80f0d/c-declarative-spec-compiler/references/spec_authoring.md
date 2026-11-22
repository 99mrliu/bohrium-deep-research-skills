# Authoring `deck.spec.json`: distilling a paper into one-claim-per-slide specs

This is the only intellectual artifact you write; the compiler does everything
else. Budget guidance: paper extraction + spec authoring should take most of
your model requests; mechanics should take almost none.

## 1. Find the mainline (not the paragraph order)

A paper is a continuous narrative; a talk is a discrete claim sequence. Read
abstract + intro last paragraph + section headings + all figure/table captions
+ conclusion, then state the mainline in this order:

1. **Problem** — what question, why it matters (1 slide).
2. **Gap** — what prior work misses; the paper's entry point (≤1 slide).
3. **Method** — the core idea at the level a smart colleague needs; one slide
   per genuinely distinct component, not per subsection (1–3 slides).
4. **Evidence groups** — group results by the claim they support, not by the
   order they appear. Each group becomes one figure/table/content slide whose
   claim the figure/table proves (2–6 slides). This is where decks most often
   go wrong: do not copy the abstract's sentence order.
5. **Limitations** — what the authors themselves concede (1 slide; audiences
   trust decks that include it).
6. **Conclusion** — the one thing to remember + what next (1 slide).

Slide-count check: if the case gives a limit, spend slides on evidence groups
first, compress method second, never drop limitations silently — if you must,
say so in the notes of the conclusion slide.

## 2. One claim per slide, claim as banner

- `claim` is exactly ONE sentence, ≤ ~30 words, stating what the slide proves
  or argues — not a topic label. "Results" is a topic; "The model cuts error
  by 40% on the hardest split" is a claim.
- The claim doubles as the slide's display title when `title` is omitted, so
  write it to be readable as a banner. Use `title` only when you want a short
  label plus the claim shown as a sub-banner.
- If a slide needs two claims, it needs two slides (or a `two-column` kind
  with left/right bullets supporting one shared claim).

## 3. Bullets: short, speakable, verbatim numbers

- Phrases, not paragraphs: ≤ ~12 words each, parallel structure.
- **Numbers, units, method names, dataset names, and figure numbers are copied
  verbatim from the paper text.** Never rescale (0.42 → 42%), never round,
  never invent a confidence interval. If the paper says "accuracy 83.2 ± 0.4
  on GLUE", the bullet says exactly that.
- Keep within `meta.max_bullets` (default 6). If you exceed it deliberately,
  the compiler demotes surplus bullets into the notes with a
  `[DEMOTED:bullet-cap]` marker — so put the *least* important bullets last.

## 4. Evidence locator discipline

Every content/figure/table slide carries `evidence`: `[{"ref": "Fig. 2",
"page": 5, "quote": "..."}]`.

- `ref` uses the paper's own label exactly: "Fig. 2", "Table 1", "Sec. 3.2",
  "Eq. (4)". Never renumber. If two figures support the claim, list both.
- `page` is the PDF page (1-based) where the item appears — verify against the
  rendered page, not the printed page number, when they differ.
- `quote` (optional but powerful for correctness review): a short verbatim
  sentence from the paper backing the claim. If you cannot find a sentence
  that backs the claim, the claim is wrong — fix the claim, not the quote.
- Never present a schematic as experimental data: if a figure is an
  illustration, say "schematic" in the caption and notes.
- The compiler stamps these locators as the slide footer
  ("Source: Fig. 2 (p. 5)"), so the spec IS the page-level evidence map that
  reviewers check.

## 5. Notes that earn their place

`notes` are required on every slide and must NOT repeat the bullets. Write:

- **Transition**: one sentence bridging from the previous slide ("So the
  method is cheap; the obvious question is whether it is accurate — next
  slide").
- **Emphasis**: what to point at on the figure, what number to say out loud.
- **Q&A backup**: the anticipated question and where the answer lives in the
  paper ("If asked about significance: Table 3 row 4, p. 8").
- The compiler appends any demoted bullets/rows here automatically.

## 6. Audience adaptation

- **Thesis defense**: more method rigor, limitations prominent, backup slides
  for every expected committee question (use `kind: "backup"`; they never
  count against `slide_limit`).
- **Group meeting**: assume field knowledge; compress problem/gap, expand
  method detail and negative results.
- **Conference short talk**: hard slide limit; one evidence group per slide,
  boldest claim as title slide subtitle; push extra results to backup.
- Language: match the case requirement; `meta.language` is informational, the
  spec text itself carries the language. CJK decks fit the same estimator
  (CJK chars count double width).

## 7. Illustrative mini-spec (ILLUSTRATIVE EXAMPLE — not a real case)

```json
{
  "meta": {"case_id": "demo-000", "title": "Shrinking Transformers via Layer Sharing",
           "audience": "group meeting", "language": "en",
           "slide_limit": 8, "max_bullets": 6, "footer_prefix": "Source: "},
  "slides": [
    {"id": "s1", "kind": "title", "title": "Shrinking Transformers via Layer Sharing",
     "claim": "Layer sharing cuts parameters 4x with <1 pt accuracy loss.",
     "notes": "Open with the deployment motivation; 30 seconds."},
    {"id": "s2", "kind": "content", "claim": "Prior compression trades accuracy for size; we target both.",
     "bullets": ["Distillation: needs full teacher at train time",
                 "Pruning: unstructured sparsity hard to serve"],
     "evidence": [{"ref": "Sec. 1", "page": 1}],
     "notes": "Transition: our entry point is sharing, not removing."},
    {"id": "s3", "kind": "figure", "claim": "Sharing every 2 layers loses only 0.7 BLEU.",
     "bullets": ["Baseline 28.4 BLEU vs shared 27.7 BLEU",
                 "Parameters: 213M -> 61M"],
     "image": {"path": "fig2.png", "caption": "Fig. 2 (data figure): BLEU vs sharing factor"},
     "evidence": [{"ref": "Fig. 2", "page": 5, "quote": "sharing every two layers costs 0.7 BLEU"}],
     "notes": "Point at the k=2 bar. Q&A: Fig. 3 has latency."},
    {"id": "s4", "kind": "conclusion", "claim": "Layer sharing is a free 4x compression for deployment.",
     "bullets": ["<1 pt loss at 4x fewer parameters", "Limitation: only tested on MT"],
     "evidence": [{"ref": "Sec. 6", "page": 9}],
     "notes": "End on deployment; acknowledge MT-only limitation honestly."}
  ]
}
```

Notice: one claim each; numbers verbatim; every content slide located in the
paper; notes add transitions and Q&A backup rather than repeating bullets.
