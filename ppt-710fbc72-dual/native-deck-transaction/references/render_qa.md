# Render QA, commands, and limits

## Rendering

The runner discovers `soffice` on `PATH`, then tries:

```text
/Applications/LibreOffice.app/Contents/MacOS/soffice
```

Equivalent isolated-profile command used by the implementation:

```bash
soffice --headless -env:UserInstallation=file:///app/work/lo-profile \
  --convert-to pdf --outdir /app/work/render /app/output/presentation.pptx
```

The PDF is copied to `/app/output/presentation.pdf`. PNGs are written to `/app/output/previews` using:

```bash
pdftoppm -png -r 110 /app/output/presentation.pdf /app/output/previews/preview
```

If `pdftoppm` is unavailable, PyMuPDF rasterizes each PDF page. Preview names are normalized to `preview-NNN.png`. The actual commands, return logs, renderer availability, PDF path, and preview method appear in `render_report.json`.

## Automated checks

1. **Page/preview count:** PDF pages and PNG previews must equal final PPTX slide count.
2. **Lost/clipped text proxy:** every expected text paragraph from each final slide must occur in normalized text on the corresponding PDF page. Unicode NFKC, whitespace, and bullet normalization reduce renderer formatting noise. A missing string is a warning requiring inspection because it can indicate clipping, lost text, unsupported glyphs, or extraction differences.
3. **OOXML geometry:** shapes outside slide bounds are listed. This does not use page-edge raster ink as overflow evidence; intentional full-bleed decorations are legitimate.
4. **Title/footer intersections:** substantial geometric intersections with native title/footer/date/slide-number placeholders are listed for visual adjudication.
5. **Font policy:** only explicit OOXML font sizes below `meta.minimum_explicit_font_pt` (default 12 pt) are listed. Inherited sizes are not guessed, globally shrunk, or blindly increased.
6. **Image presence:** appended/edit figure counts are compared with actual PPTX picture shapes. PDF image counts are supplementary best-effort evidence, since rendering may flatten or transform images.
7. **Dimensions:** PDF points and PNG pixels are recorded for every page.

Geometry/intersection/font findings are warnings; page-count, expected-text, preview, and expected-PPTX-image checks determine automated render pass. Automated pass is not a substitute for every-page visual inspection.

## Visual correction loop

Open every `preview-NNN.png`, in order, after every finish. Check composition and scientific readability as well as the reported warnings. Correct the authorized plan operation—not the base template or global theme—and rerun finish. Review all pages again because relationship/order/render changes can affect other pages. Record `meta.visual_review.status` as `complete` only after actual inspection, list reviewed pages, and describe corrections. Synthetic automation uses `automated`, which explicitly does not claim human-style visual completeness.

## Font fallback limits

The report collects explicit slide typefaces and renderer font-related log lines. If `fc-list` exists, missing explicit families are marked **potential** fallback. Family aliases, theme font resolution, substitution inside LibreOffice, and glyph-level fallback make this non-conclusive. With neither `fc-list` nor renderer signals, status is `unavailable`; no absence-of-fallback claim is made.

## Honest partial results

No LibreOffice, failed PDF conversion, failed rasterization, unreadable PDF text, native diff failure, or incomplete visual work must remain visible in `result.json`/`render_report.json`. A useful PPTX with incomplete render QA is `partial`; no validated PPTX after transaction rejection is `failed`. Do not create fake PDFs/PNGs or replace a native failure with a screenshot-only deck.
