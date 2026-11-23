# Defect taxonomy and repair moves (Bundle C)

`svg_inspect.py` emits these codes. Blockers prevent `status: complete`.

## D-OVERFLOW (blocker)

Text wider than its declared `data-max-w`, or — for foreign SVGs without the
attribute — longer than the canvas width remaining at its anchor (heuristic,
reported as such).

Repair: shorten the string first; then enlarge the container; font size is
the LAST lever and never below the floor. If the text is a number+unit,
check whether the unit belongs in an axis/legend instead of the label.

## D-FONTMIN (blocker)

`font-size` below the floor (default 7.5 px ≈ 5.6 pt at 96 px/in).

Repair: raise to ≥ 8 px; if it no longer fits, the element is overloaded —
split it or demote it to a caption/legend entry.

## D-CLIP (blocker)

Text anchor outside the viewBox — the label will be cropped on export.

Repair: move the element inside; if the viewBox is wrong for the content,
fix the viewBox (and re-run the export preview).

## D-VIEWBOX (blocker)

Missing or unparseable `viewBox`; the SVG cannot be exported
resolution-independently.

Repair: add `viewBox="0 0 W H"` matching width/height.

## D-NOLAYER (warning)

Fewer than two named groups. The file is technically SVG but not "layered,
editable source" in any useful sense.

Repair: group elements by role (title / entities / edges / legend) with
`id` or `inkscape:label`. If the figure came from a converter that emits a
flat soup, say so in `exceptions` and keep the groups you can add.

## D-RASTER (warning)

Embedded `<image>` inside a figure that must stay editable.

Repair: acceptable only for a genuine photographic asset (micrograph) —
record it in `exceptions` with the asset's source; never for text or charts.

## D-EMPTYTXT (warning)

Empty `<text>` elements (editing debris).

Repair: delete them, or fill them if they were meant to hold a label.

## Standing repair-loop rule

One repair per finding, then re-run the inspector. Do not batch-fix ten
things blind: a repair that moves geometry can create a new overflow, and
the loop is cheap. The repair history belongs in `result.json.change_record`
(via `finalize_result.py` phases) so a reviewer can replay it.
