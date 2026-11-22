# Template forensics and layout mapping

`scripts/inspect_deck.py` turns a PPTX into a JSON report. Read it before touching the file; every build decision should cite this report.

## What the report contains

```json
{
  "file": "target-template.pptx",
  "slide_size_emu": [12192000, 6858000],
  "slide_count": 3,
  "masters": [
    {"name": "Office Theme", "layouts": [
      {"name": "Title Slide", "index": 0,
       "placeholders": [{"idx": 0, "type": "TITLE", "left": 685800, "top": 1600200, "width": 10515600, "height": 1325563}]}
    ]}
  ],
  "theme_fonts": {"major": "...", "minor": "..."},
  "slides": [{"index": 1, "layout": "Title Slide", "shapes": 4, "texts_preview": ["..."]}]
}
```

## Reading it

- **Slide size** decides figure crop aspect: a 16:9 content region cropped from a 4:3 source page needs deliberate margins, not a stretch.
- **Layouts and placeholders** are the only legitimate slots. Map each planned slide to a layout by *role* (title, section header, title+content, two-content, blank), not by name similarity. Two layouts with the same name on different masters are different objects — record master name with the layout.
- **Theme fonts/colors** are the house style. Any free text box you add must set these explicitly, or the renderer's defaults will drift from the template.
- **Existing slides** in a template are samples unless the work order says otherwise; in a starting deck they are content with preservation rules.

## Layout mapping table (`/app/work/layout_map.json`)

```json
{
  "mode": "create",
  "mappings": [
    {"slide": 1, "role": "title", "layout": "Title Slide", "master": "Office Theme",
     "slots": {"headline": "placeholder idx 0", "subtitle": "placeholder idx 1"}},
    {"slide": 6, "role": "key result", "layout": "Title and Content", "master": "Office Theme",
     "slots": {"headline": "title", "figure": "content placeholder (picture)", "takeaway_line": "text box, bottom 15%"}
    }
  ],
  "fallbacks": [{"slide": 6, "reason": "no picture placeholder in layout; used theme-styled text box for caption"}],
  "conflicts": []
}
```

Rules:

- Every slide gets a mapping row before it is built; every free-text fallback gets a reason.
- A mandated layout/master name from the work order that is absent from the report is a `conflicts` entry raised in phase 1, with the proposed substitute — never a silent substitution discovered at delivery.
- In edit mode, the map additionally records `source_slide` for each touched slide and the list of slides guaranteed untouched.

## Common structural traps

- `add_slide()` with a layout from a *different* Presentation object: the relationship is wrong even when it looks right — always use layouts of the open presentation.
- Deleting slides leaves orphaned layout parts; harmless but record removals in the changelog.
- Placeholders copied between slides carry their `idx`; duplicate `idx` on one slide corrupts inheritance — set text on existing placeholders instead of cloning them.
- Notes exist per slide (`slide.notes_slide`); removing a slide removes its notes — in edit mode, confirm preserved slides kept their notes after save.
