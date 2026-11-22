# OOXML / python-pptx recipes for template-native building

## 1. Placeholder model (why inheritance is real only inside the template)

A slide inherits from exactly one layout, a layout from one master, a master
from the theme. python-pptx' `Presentation(template_path)` keeps those parts;
`slides.add_slide(layout)` clones the layout's placeholders into the slide.
A deck built from a blank `Presentation()` inherits the *default Office*
theme instead — that is the "template not really applied" failure.

- Placeholders are matched by `idx` (title is idx 0; body/object typically
  1+; date 10, footer 11, slide number 12). Coordinates are NOT identifiers.
- A placeholder with no `<a:xfrm>` on the slide inherits geometry from the
  layout. `shape.left/top/width/height` then read as `None` in python-pptx;
  resolve the effective value from the layout placeholder of the same idx
  (the builder's `eff_geo` does this).
- Writing a partial xfrm (e.g. only `width`) materializes an xfrm whose
  other members are zero — the box collapses or jumps. Always write all four
  (the builder's `set_geo` does this).

## 2. Instantiating footer / slide-number placeholders

`add_slide` does not clone date/footer/slide-number placeholders. To get real
placeholder inheritance (so theme position and font apply, and auditors see
`ph idx=11/12`), deep-copy the layout's `<p:sp>` into the slide's `spTree`
and clear its text runs (see `clone_layout_ph` in build_deck.py). The footer
text can then be set per slide; the slide-number field renders automatically
at export. Do not fake these with floating text boxes — they break batch
consistency the moment the template is edited.

## 3. LibreOffice headless export (reliable form)

```
soffice --headless --norestore --nolockcheck \
  -env:UserInstallation=file:///app/work/lo_profile \
  --convert-to pdf --outdir /app/output deck.pptx
```

- A bare first run on a fresh machine commonly dies with
  `DeploymentException`; a private `UserInstallation` profile fixes it.
  Retry once with a freshly deleted profile before giving up.
- Output name is `<deck basename>.pdf` in `--outdir`.
- Export uses the *environment's* fonts, not the author's: check the PDF font
  list against the theme fonts and record substitutions.

## 4. Emergency route when python-pptx is unavailable

Last resort only (prefer `pip install python-pptx`): copy the template file,
unzip, duplicate an existing `ppt/slides/slideN.xml`, update
`[Content_Types].xml`, `ppt/_rels/presentation.xml.rels`,
`ppt/presentation.xml` (sldIdLst), and the slide's `.rels`; edit text runs
inside the duplicated XML. Keep every other byte of the package untouched so
master/layout/theme relationships survive. Zip back with stored mimetype
ordering irrelevant for pptx (zip64 fine). Validate by opening in the
renderer. Record this substitution in the change log and mark the result
`partial` unless it passes the same audits.

## 5. Font-size ladder and spacing (explainable defaults)

- Body ladder: 18 → 16 → 14 → 12 pt floor; level-2 bullets 2 pt below their
  parent; captions and source anchors 12 pt; never below 12.
- Line-height allowance for fitting: 1.3 × font size per line.
- Average glyph width for estimation: latin ≈ 0.52 em, CJK ≈ 1.0 em.
- Title: keep to one line, at most two; shorten the wording rather than the
  font when it wraps past two lines.
- Figures: scale = min(box_w/native_w, box_h/native_h); allow up to 1.5×
  upscale; require effective dpi ≥ 96 (warn below).
