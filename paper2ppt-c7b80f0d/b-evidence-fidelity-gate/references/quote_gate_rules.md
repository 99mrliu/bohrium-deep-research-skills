# Quote-gate rulebook

These rules decide what may appear on a slide and in speaker notes. They are
enforced mechanically by `scripts/check_plan.py` (plan stage) and
`scripts/audit_deck.py` (deck stage); this document is the human/agent side.

## 1. What requires a verbatim quote

A bullet (or note sentence) requires a `quote` + `locator` if it states any of:

- a **number with a unit** (`92.3%`, `120 ms`, `300 K`, `5 mM`, `200 epochs`);
- a **bare number used as a result** (`1.2 M parameters`, `7 benchmarks`,
  `Top-1 of 88.1`);
- a **method / model / dataset name** presented as fact (`BERT-large`,
  `ImageNet-1k`) — quote the sentence that names it;
- a **conclusion** (`outperforms the state of the art`, `no significant
  difference`) — quote the concluding sentence.

Pure framing text ("Motivation", "We evaluate on three axes", agenda lines)
needs no quote but also must not smuggle in any of the above.

## 2. Verbatim-copy technique

1. Quote source is **`/app/work/paper.txt` only** (the pdftotext output), not
   your memory of the PDF.
2. Copy the exact characters. You may only collapse whitespace/line-wraps —
   `check_plan.py` and `audit_deck.py` compare after whitespace + ligature
   normalization, so anything else fails.
3. Never: retype numbers, change `92.30` to `92.3` inside the quote (the
   *slide text* may shorten, the *quote* may not), translate a quote, merge
   two sentences with `...` unless the ellipsis replaces whole clauses and the
   result is still a contiguous normalized substring — when in doubt, use two
   quotes.
4. Locator = `{"page": N}` at minimum; add `"figure": "2"` / `"table": "1"` /
   `"section": "3.2"` when applicable. Page numbers are 1-based PDF pages
   (matching `paper_pages.json` and `pages/page-N.png`).

## 3. Claim-strength taxonomy

| status | meaning | quote needed |
|---|---|---|
| `established` | paper states it as settled fact / main result | yes |
| `supported` | directly backed by quoted evidence | yes |
| `preliminary` | paper hedges ("we observe", "suggests") | yes, hedged quote |
| `inferred` | your synthesis across ≥2 quotes or obvious reading | no, but say so |
| `unsupported` | needed for narrative but not in the paper | label or remove |

Slide text must not sound stronger than its status: a `preliminary` quote
("suggests") may not become a slide claim ("demonstrates").

## 4. Schematic vs data figures

Classify every figure before citing it (confirm on `pages/page-N.png`):

- **schematic cues**: caption verbs *schematic, illustration, overview,
  pipeline, architecture, framework, workflow*; boxes-and-arrows content.
- **data cues**: caption verbs *measured, plotted, fitted, recorded, accuracy
  of, curves, spectra, histogram*; axes with numeric ticks.

Rules: schematics may appear on method/overview slides only, captioned as
schematics; data figures on results slides. Never relabel a schematic as
"experimental result", never crop a data figure so axis units disappear.

## 5. Others'-results rule

A number/conclusion belongs to prior work if in the paper text it sits next to
a citation marker (`[12]`, `(Smith et al., 2020)`, `et al. reported`) or in a
Related Work section. Such content may appear only in background slides,
explicitly attributed ("Smith et al. report 88% [12]"). Presenting it as this
paper's result is a critical mutation — the auditor cannot always catch it, so
check quotes for nearby citation markers yourself.

## 6. Units and significant figures

- Preserve units exactly: `ms` ≠ `s`, `mM` ≠ `μM`, `keV` ≠ `MeV`. The auditor
  compares normalized units; a unit mutation fails the gate.
- Preserve significant figures in slide text unless you keep the same value:
  `92.30%` → `92.3%` is allowed (same float); `92.3%` → `92%` is a mutation.
- Do not convert units on slides unless the paper itself gives both forms.

## 7. Common mutation failures (before → after)

| failure | before (paper) | after (bad slide) |
|---|---|---|
| digit drift | `accuracy of 92.3%` | `93.2% accuracy` |
| unit drift | `latency 120 ms` | `latency 120 s` |
| sig-fig inflation | `p < 0.05` | `p = 0.043` |
| figure mis-cite | text cites `Fig. 2` | slide says `Figure 3` |
| schematic as data | `Fig. 1: schematic of the pipeline` | "Measured pipeline performance (Fig. 1)" |
| prior art as own | `Smith et al. achieved 88% [12]` | "We achieve 88%" |
| table mix-up | `Table 1: dataset statistics` | slide pairs `Table 1` with results caption |

Every one of these is caught by the gate *if* the paper text says otherwise —
which is why PASS 1 extraction quality matters. When the heuristic index and
your eyes disagree, trust your eyes and fix the plan locators, not the paper.
