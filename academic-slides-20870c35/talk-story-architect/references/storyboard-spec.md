# Storyboard specification and quality gates

`/app/work/storyboard.json` is the binding plan for the deck. Validate it with `scripts/storyboard_check.py` before building slides and after every revision; copy the final version to `/app/output/storyboard.json`.

## Schema

```json
{
  "case_id": "copied from contract",
  "spine": "progress | defense | conference | review | pitch | hybrid:<note>",
  "duration_sec": 600,
  "slides": [
    {
      "index": 1,
      "role": "title | hook | context | gap | idea | method | validation | result | limitation | takeaway | framing | backup",
      "headline": "One full sentence: the slide's only message, evidence-qualified.",
      "support": [{"kind": "figure|table|quote|number|none", "locator": "file p.PAGE Fig.X / Sec.Y"}],
      "time_sec": 60,
      "transition": "spoken sentence linking from the previous slide",
      "notes_hint": "what the notes must explain beyond the bullets",
      "source_slide": null
    }
  ],
  "backups": [],
  "objection_map": [{"question": "...", "slide": 4}]
}
```

## Gates (all enforced by storyboard_check.py)

1. **Count** — number of non-backup slides equals the work order's mandated count (or inside its range).
2. **Time** — `sum(time_sec)` within ±10% of the allotted speaking time (duration minus reserved Q&A); every slide within 20–240 s; no slide over 20% of the total unless flagged `key_result: true`.
3. **Single message** — `headline` is one sentence (no semicolon-chained claims), ≥6 words, not a bare topic label (matches a stoplist: "Method", "Results", "Conclusion", "Background", "相关工作", "实验结果", …).
4. **Headline test** — roles form a coherent order: exactly one title/opening beat first, takeaway last among content slides, no result before any method/context beat exists, every `result`/`validation` headline contains a qualifier or exact value consistent with its support strength.
5. **Support closure** — every non-framing slide has ≥1 support locator, and every locator string matches a locator recorded in `material.json` (checked textually when `--material` is passed).
6. **Objection closure** — every objection in `audience.json` appears in `objection_map` pointing at a real slide or backup.
7. **Edit-mode closure** — with `--edit`, every `source_slide` is an integer within the starting deck's slide count, and preserved slides are listed with `role: preserved`.

## Writing headlines

- A headline states a finding or a point: "Twice the throughput at half the labeled data", not "Throughput experiments".
- Keep the evidence's strength word: established → "shows/demonstrates"; preliminary → "suggests"; contextual → "is consistent with". Never upgrade strength between material and headline.
- Numbers on headlines are transcribed exactly as in the source, with units and conditions.

## Transitions and notes

- `transition` is spoken language, one sentence, referencing what the audience just heard — it is the connective tissue the headline test cannot see.
- `notes_hint` records what the speaker notes must add (interpretation, caveat, timing), so notes never degenerate into a copy of the bullets.
