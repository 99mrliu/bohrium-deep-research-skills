#!/usr/bin/env python3
"""validate_spec.py -- validate a deck.spec.json against the ppt-spec-compiler schema.

Pure Python 3 stdlib. Hand-rolled checks mirror spec_schema.json (no jsonschema
dependency in the runtime). Prints itemized, human-readable errors and warnings.

Exit code: 0 = valid (warnings allowed), 1 = at least one error, 2 = spec unreadable.

Severity policy (documented in spec_schema.json and references/text_fit.md):
  ERROR   -- the compiler cannot or must not build: missing/empty `claim` on a
             claim-bearing slide, missing evidence locator on a content/figure/table
             slide, missing notes, unknown fields, wrong types, absurd sizes
             (> HARD_MAX_SLIDES slides, > HARD_MAX_BULLETS bullets).
  WARNING -- the compiler handles it deterministically at build time and records a
             decision: bullets over meta.max_bullets (demoted to notes), slide count
             over meta.slide_limit (overflow moved to a backup section), missing
             image files (placeholded), first slide not a title slide, long claim.
"""
import argparse
import json
import os
import sys

SLIDE_KINDS = {"title", "section", "content", "figure", "table",
               "two-column", "conclusion", "backup"}
CLAIM_KINDS = {"content", "figure", "table", "two-column", "conclusion"}
EVIDENCE_KINDS = {"content", "figure", "table"}  # evidence locators mandatory
META_FIELDS = {"case_id", "title", "audience", "language", "slide_limit",
               "max_bullets", "footer_prefix", "time_limit"}
SLIDE_FIELDS = {"id", "kind", "claim", "title", "bullets", "evidence",
                "image", "table", "notes"}
EVIDENCE_FIELDS = {"ref", "page", "quote"}
IMAGE_FIELDS = {"path", "caption"}
TABLE_FIELDS = {"columns", "rows"}
TOP_FIELDS = {"meta", "slides"}

HARD_MAX_SLIDES = 40      # schema-level sanity cap; meta.slide_limit is the talk cap
HARD_MAX_BULLETS = 15     # schema-level sanity cap; meta.max_bullets is the slide cap
CLAIM_WARN_CHARS = 220


def _is_str(x):
    return isinstance(x, str)


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


class SpecValidator:
    def __init__(self, spec_path):
        self.spec_path = spec_path
        self.spec_dir = os.path.dirname(os.path.abspath(spec_path)) or "."
        self.errors = []
        self.warnings = []

    def error(self, where, msg):
        self.errors.append(f"ERROR [{where}] {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"WARN  [{where}] {msg}")

    # ------------------------------------------------------------------ meta
    def check_meta(self, meta):
        where = "meta"
        if not isinstance(meta, dict):
            self.error(where, f"`meta` must be an object, got {type(meta).__name__}")
            return {}
        for k in sorted(set(meta) - META_FIELDS):
            self.error(where, f"unknown meta field `{k}` (allowed: {sorted(META_FIELDS)})")
        title = meta.get("title")
        if not _is_str(title) or not title.strip():
            self.error(where, "`title` is required and must be a non-empty string")
        if "case_id" not in meta:
            self.warn(where, "`case_id` missing; make_result.py will take it from case.json")
        for k in ("slide_limit", "max_bullets"):
            if k in meta:
                v = meta[k]
                if not _is_int(v) or v < 1:
                    self.error(where, f"`{k}` must be a positive integer, got {v!r}")
        sl = meta.get("slide_limit", 20)
        if _is_int(sl) and sl > HARD_MAX_SLIDES:
            self.error(where, f"slide_limit {sl} exceeds hard cap {HARD_MAX_SLIDES}")
        mb = meta.get("max_bullets", 6)
        if _is_int(mb) and mb > HARD_MAX_BULLETS:
            self.error(where, f"max_bullets {mb} exceeds hard cap {HARD_MAX_BULLETS}")
        for k in ("audience", "language", "footer_prefix", "time_limit", "case_id"):
            if k in meta and not _is_str(meta[k]):
                self.error(where, f"`{k}` must be a string, got {type(meta[k]).__name__}")
        return meta

    # --------------------------------------------------------------- slides
    def check_slide(self, s, i, max_bullets):
        where = f"slides[{i}]"
        if not isinstance(s, dict):
            self.error(where, f"slide must be an object, got {type(s).__name__}")
            return
        sid = s.get("id", f"#{i}")
        where = f"slides[{i}] id={sid!r}"
        for k in sorted(set(s) - SLIDE_FIELDS):
            self.error(where, f"unknown slide field `{k}` (allowed: {sorted(SLIDE_FIELDS)})")

        kind = s.get("kind")
        if kind not in SLIDE_KINDS:
            self.error(where, f"`kind` must be one of {sorted(SLIDE_KINDS)}, got {kind!r}")
            kind = None

        # --- claim: exactly one string on claim-bearing kinds ----------------
        claim = s.get("claim")
        if kind in CLAIM_KINDS:
            if not _is_str(claim) or not claim.strip():
                self.error(where, f"kind={kind}: exactly one non-empty `claim` string is required")
            elif isinstance(claim, (list, dict)):
                self.error(where, "`claim` must be a single string, not a list/dict")
        if _is_str(claim) and len(claim) > CLAIM_WARN_CHARS:
            self.warn(where, f"claim is {len(claim)} chars (>{CLAIM_WARN_CHARS}); "
                             "a slide claim should be one speakable sentence")

        if "title" in s and not _is_str(s["title"]):
            self.error(where, f"`title` must be a string, got {type(s['title']).__name__}")

        # --- bullets ---------------------------------------------------------
        bullets = s.get("bullets", [])
        if not isinstance(bullets, list) or not all(_is_str(b) for b in bullets):
            self.error(where, "`bullets` must be a list of strings")
            bullets = []
        if len(bullets) > HARD_MAX_BULLETS:
            self.error(where, f"{len(bullets)} bullets exceeds hard cap {HARD_MAX_BULLETS}")
        elif len(bullets) > max_bullets:
            self.warn(where, f"{len(bullets)} bullets > meta.max_bullets={max_bullets}; "
                             "compiler will demote surplus bullets into speaker notes")

        # --- evidence locators ------------------------------------------------
        ev = s.get("evidence", [])
        if kind in EVIDENCE_KINDS:
            if not isinstance(ev, list) or not ev:
                self.error(where, f"kind={kind}: at least one evidence locator "
                                  '(`evidence`: [{"ref": ..., "page": ...}]) is required')
                ev = []
        if "evidence" in s and not isinstance(s.get("evidence"), list):
            self.error(where, "`evidence` must be a list of objects")
            ev = []
        for j, e in enumerate(ev):
            ew = f"{where} evidence[{j}]"
            if not isinstance(e, dict):
                self.error(ew, f"evidence item must be an object, got {type(e).__name__}")
                continue
            for k in sorted(set(e) - EVIDENCE_FIELDS):
                self.error(ew, f"unknown evidence field `{k}` (allowed: {sorted(EVIDENCE_FIELDS)})")
            if not _is_str(e.get("ref")) or not e.get("ref", "").strip():
                self.error(ew, "`ref` (e.g. \"Fig. 2\", \"Table 1\", \"Sec. 3.2\") is required")
            if "page" in e and not _is_int(e["page"]):
                self.error(ew, f"`page` must be an integer, got {e['page']!r}")
            if "quote" in e and not _is_str(e["quote"]):
                self.error(ew, "`quote` must be a string")

        # --- image -------------------------------------------------------------
        img = s.get("image")
        if img is not None:
            if not isinstance(img, dict):
                self.error(where, "`image` must be an object {path, caption?}")
            else:
                for k in sorted(set(img) - IMAGE_FIELDS):
                    self.error(where, f"unknown image field `{k}` (allowed: {sorted(IMAGE_FIELDS)})")
                p = img.get("path")
                if not _is_str(p) or not p.strip():
                    self.error(where, "image.path is required and must be a non-empty string")
                else:
                    full = p if os.path.isabs(p) else os.path.join(self.spec_dir, p)
                    if not os.path.isfile(full):
                        self.warn(where, f"image file not found: {p} "
                                         "(compiler will draw a labelled placeholder box)")
        if kind == "figure" and img is None:
            self.warn(where, "kind=figure but no `image` given; slide will render as text-only")

        # --- table ---------------------------------------------------------------
        tb = s.get("table")
        if tb is not None:
            if not isinstance(tb, dict):
                self.error(where, "`table` must be an object {columns, rows}")
            else:
                for k in sorted(set(tb) - TABLE_FIELDS):
                    self.error(where, f"unknown table field `{k}` (allowed: {sorted(TABLE_FIELDS)})")
                cols = tb.get("columns")
                rows = tb.get("rows")
                if not isinstance(cols, list) or not cols or not all(_is_str(c) for c in cols):
                    self.error(where, "table.columns must be a non-empty list of strings")
                    cols = []
                if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
                    self.error(where, "table.rows must be a list of row lists")
                    rows = []
                for j, r in enumerate(rows):
                    if cols and len(r) != len(cols):
                        self.error(where, f"table.rows[{j}] has {len(r)} cells, expected {len(cols)}")
        if kind == "table" and tb is None:
            self.warn(where, "kind=table but no `table` given; slide will render as text-only")

        # --- notes ---------------------------------------------------------------
        notes = s.get("notes")
        if not _is_str(notes) or not notes.strip():
            self.error(where, "`notes` (speaker notes) is required and must be non-empty "
                              "on every slide; do not just repeat the bullets")

    def validate(self):
        try:
            with open(self.spec_path, "r", encoding="utf-8") as f:
                spec = json.load(f)
        except FileNotFoundError:
            self.error("spec", f"file not found: {self.spec_path}")
            return None
        except json.JSONDecodeError as e:
            self.error("spec", f"invalid JSON: {e}")
            return None
        if not isinstance(spec, dict):
            self.error("spec", f"top level must be an object, got {type(spec).__name__}")
            return None
        for k in sorted(set(spec) - TOP_FIELDS):
            self.error("spec", f"unknown top-level field `{k}` (allowed: meta, slides)")
        if "slides" not in spec:
            self.error("spec", "`slides` is required")
        meta = self.check_meta(spec.get("meta", {}))
        slides = spec.get("slides", [])
        if not isinstance(slides, list):
            self.error("slides", f"`slides` must be a list, got {type(slides).__name__}")
            return spec
        if not slides:
            self.error("slides", "`slides` must contain at least one slide")
        if len(slides) > HARD_MAX_SLIDES:
            self.error("slides", f"{len(slides)} slides exceeds hard cap {HARD_MAX_SLIDES}")
        limit = meta.get("slide_limit", 20)
        main = [s for s in slides if isinstance(s, dict) and s.get("kind") != "backup"]
        if _is_int(limit) and len(main) > limit:
            self.warn("slides", f"{len(main)} non-backup slides > meta.slide_limit={limit}; "
                                "compiler will move overflow slides into a labelled backup section")
        if slides and isinstance(slides[0], dict) and slides[0].get("kind") != "title":
            self.warn("slides[0]", "first slide is not kind=title; academic decks should open with a title slide")
        ids = [s.get("id") for s in slides if isinstance(s, dict) and "id" in s]
        if len(ids) != len(set(ids)):
            self.error("slides", f"duplicate slide ids: {sorted({x for x in ids if ids.count(x) > 1})}")
        max_bullets = meta.get("max_bullets", 6)
        if not _is_int(max_bullets):
            max_bullets = 6
        for i, s in enumerate(slides):
            self.check_slide(s, i, max_bullets)
        return spec


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate deck.spec.json for ppt-spec-compiler.")
    ap.add_argument("--spec", default="deck.spec.json", help="path to deck.spec.json")
    ap.add_argument("--quiet", action="store_true", help="only print errors, not warnings")
    args = ap.parse_args(argv)

    v = SpecValidator(args.spec)
    spec = v.validate()
    for w in v.warnings:
        if not args.quiet:
            print(w)
    for e in v.errors:
        print(e)
    if spec is None or v.errors:
        print(f"\nvalidate_spec: FAILED ({len(v.errors)} error(s), {len(v.warnings)} warning(s))")
        return 1
    print(f"\nvalidate_spec: OK ({len(v.warnings)} warning(s)); "
          f"{len(spec.get('slides', []))} slide(s) in {os.path.abspath(args.spec)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
