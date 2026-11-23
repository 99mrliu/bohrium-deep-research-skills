# Rendering contract

1. **Every promised preview must exist.** `review_pack.py` walks the render,
   comparison and table reports and fails closed when a PNG is absent or
   below the byte-size floor. An empty render directory is not a successful
   render.
2. **Strict mathtext, no fakes.** The renderer draws exactly the LaTeX it was
   given through matplotlib mathtext. Engine errors go to the `unrenderable`
   list with the engine's own message; the fix is to repair the LaTeX
   upstream, not to draw something approximate.
3. **Source pairing.** A comparison sheet pairs the rendered transcription
   with the source page raster (when a PDF artifact exists) or with the
   formula's `source` reference (when it does not). The sheet title says
   which mode produced it.
4. **Artifact manifest.** `result.json.artifacts.previews` lists every
   preview with its byte size; the runtime contract's PNG/PDF preview
   requirement is satisfied by real files on disk, never by filenames alone.
5. **Font coverage.** mathtext covers Greek letters, scripts, fractions,
   radicals and fences. CJK text inside formulas, TikZ-style macros and
   package-specific commands are out of scope and will be reported
   `unrenderable` — that report is the honest outcome.
