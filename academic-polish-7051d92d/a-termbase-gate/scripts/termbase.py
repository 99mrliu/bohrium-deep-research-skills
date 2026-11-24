#!/usr/bin/env python3
"""termbase.py - termbase extraction, locking, and full-text terminology lint.

Subcommands
-----------
extract   Mine candidate terms from a draft: "Full Name (ABBR)" definition
          pairs, ALL-CAPS tokens, and frequent multiword noun phrases.
          Emits a candidate JSON the agent must review and confirm.
lock      Merge a case glossary (optional) with agent-confirmed candidates
          into a locked termbase. Conflicts (e.g. one abbreviation mapped to
          two full names) are reported in a "conflicts" list and cause a
          non-zero exit; they are never silently reconciled.
lint      Re-scan a full text against a locked termbase: banned variants,
          unregistered spelling/case/hyphen variants, abbreviations used
          before their definition or never defined, and cross-section drift
          (sections split on Markdown / LaTeX headings). Any error-level
          finding produces a non-zero exit and per-location JSON records.

Python 3 standard library only. No network. Deterministic output.
"""
import argparse
import json
import re
import sys

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*")
CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}s?\b")
PAIR_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9.\-]*(?:[ \t][A-Za-z0-9.\-]+){0,5})"
    r"\s*\(([A-Z][A-Za-z0-9]{1,10}s?)\)"
)
PHRASE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")

CAPS_STOP = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI"}
PHRASE_STOP = set(
    "the a an of and or to in on for with by from at as is are was were be been "
    "being we our this that these those it its their between within into over "
    "under via using used use show shows showed demonstrate demonstrates remain "
    "remains became become has have had than then thus hence also such may can "
    "could should would will not no yes more most less least very much many".split()
)


def norm(s):
    """Normalized comparison form: lowercase, strip spaces and hyphens."""
    return re.sub(r"[\s\-]+", "", (s or "").lower())


def atoms(s):
    """Split a surface string into lowercase matching atoms (words, hyphens)."""
    out = []
    for w in re.split(r"\s+", s.strip()):
        if not w:
            continue
        out.extend([p.lower() for p in w.split("-") if p])
    return tuple(out)


def locate(text, offset):
    line = text.count("\n", 0, offset) + 1
    last = text.rfind("\n", 0, offset)
    col = offset - last
    return line, col


def context_of(text, offset, width=100):
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    ctx = text[line_start:line_end].strip()
    return ctx[:width]


def is_subsequence(needle, haystack):
    it = iter(haystack)
    return all(ch in it for ch in needle)


def clean_full_name(raw, abbrev):
    """Heuristic: pick the trailing words whose initials cover the abbreviation."""
    raw = re.split(r"[.!?:;\n]", raw)[-1].strip()
    words = raw.split()
    if not words:
        return raw
    if any(ch.isdigit() for ch in words[-1]):
        return words[-1]
    letters = "".join(ch for ch in abbrev if ch.isalpha()).lower()
    for k in range(1, len(words) + 1):
        cand = words[-k:]
        initials = "".join(w[0] for w in cand if w).lower()
        if letters and is_subsequence(letters, initials):
            return " ".join(cand)
    return " ".join(words[-3:]) if len(words) > 3 else " ".join(words)


# ---------------------------------------------------------------- extract ----

def cmd_extract(args):
    text = open(args.source, "r", encoding="utf-8").read()
    candidates = []

    # 1) "Full Name (ABBR)" definition pairs
    for m in PAIR_RE.finditer(text):
        full_raw, abbr = m.group(1), m.group(2)
        full = clean_full_name(full_raw, abbr)
        line, col = locate(text, m.start())
        candidates.append({
            "kind": "abbrev_pair",
            "canonical_guess": full,
            "abbrev": abbr,
            "count": len(re.findall(r"\b" + re.escape(abbr) + r"\b", text)),
            "occurrences": [{"line": line, "column": col,
                             "context": context_of(text, m.start())}],
        })

    # 2) ALL-CAPS tokens
    caps = {}
    for m in CAPS_RE.finditer(text):
        tok = m.group(0)
        if tok in CAPS_STOP:
            continue
        line, col = locate(text, m.start())
        e = caps.setdefault(tok, {"kind": "acronym", "canonical_guess": None,
                                  "abbrev": tok, "count": 0, "occurrences": []})
        e["count"] += 1
        if len(e["occurrences"]) < 10:
            e["occurrences"].append({"line": line, "column": col,
                                     "context": context_of(text, m.start())})
    candidates.extend(caps.values())

    # 3) Frequent multiword noun phrases (bigrams / trigrams, stopword filtered)
    words = [w.lower() for w in PHRASE_WORD_RE.findall(text)]
    phrases = {}
    for n in (2, 3):
        for i in range(0, len(words) - n + 1):
            win = words[i:i + n]
            if any(w in PHRASE_STOP for w in win):
                continue
            ph = " ".join(win)
            phrases[ph] = phrases.get(ph, 0) + 1
    phrase_items = sorted(phrases.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    for ph, cnt in phrase_items:
        if cnt < 2:
            continue
        occ = []
        for m in re.finditer(r"\b" + re.escape(ph) + r"\b", text, re.IGNORECASE):
            line, col = locate(text, m.start())
            occ.append({"line": line, "column": col,
                        "context": context_of(text, m.start())})
            if len(occ) >= 5:
                break
        candidates.append({"kind": "multiword", "canonical_guess": ph,
                           "abbrev": None, "count": cnt, "occurrences": occ})

    kind_rank = {"abbrev_pair": 0, "acronym": 1, "multiword": 2}
    candidates.sort(key=lambda c: (kind_rank.get(c["kind"], 9),
                                   -c["count"],
                                   (c["abbrev"] or c["canonical_guess"] or "").lower()))
    for i, c in enumerate(candidates, 1):
        c_sorted = {"candidate_id": "c%04d" % i}
        c_sorted.update(c)
        c_sorted["status"] = "candidate"
        candidates[i - 1] = c_sorted

    out = {
        "tool": "termbase.py extract",
        "source": args.source,
        "note": "Review each candidate, set canonical/variants/banned, and keep "
                "only confirmed entries in the file passed to `lock`.",
        "candidates": candidates,
        "summary": {"candidate_count": len(candidates)},
    }
    write_json(args.out, out)
    print("extract: %d candidates -> %s" % (len(candidates), args.out))
    return 0


# ------------------------------------------------------------------- lock ----

def normalize_entry(raw, origin):
    e = {
        "canonical": (raw.get("canonical") or "").strip(),
        "abbrev": (raw.get("abbrev") or None),
        "variants": list(raw.get("variants") or []),
        "banned": list(raw.get("banned") or []),
        "first_use_policy": raw.get("first_use_policy")
            or ("define_at_first_use" if raw.get("abbrev") else "none"),
        "origin": origin,
        "note": raw.get("note", ""),
    }
    if e["abbrev"]:
        e["abbrev"] = e["abbrev"].strip()
    return e


def merge_unique(dst, src):
    have = {norm(x) for x in dst}
    for x in src:
        if norm(x) not in have:
            dst.append(x)
            have.add(norm(x))


def cmd_lock(args):
    entries, conflicts = [], []

    if args.glossary:
        gdoc = json.load(open(args.glossary, "r", encoding="utf-8"))
        glist = gdoc.get("entries", gdoc if isinstance(gdoc, list) else [])
        for raw in glist:
            e = normalize_entry(raw, "glossary")
            e["id"] = "t%04d" % (len(entries) + 1)
            entries.append(e)

    cdoc = json.load(open(args.candidates, "r", encoding="utf-8"))
    clist = cdoc.get("confirmed") or [
        c for c in cdoc.get("candidates", []) if c.get("status") == "confirmed"]
    for raw in clist:
        cand = normalize_entry(raw, "confirmed")
        if not cand["canonical"] and not cand["abbrev"]:
            continue
        hit = None
        for e in entries:
            if cand["abbrev"] and e["abbrev"] and cand["abbrev"] == e["abbrev"]:
                hit = e
                break
        if hit is None and cand["canonical"]:
            for e in entries:
                if e["canonical"] and norm(e["canonical"]) == norm(cand["canonical"]):
                    hit = e
                    break
        if hit is not None:
            if (cand["abbrev"] and hit["abbrev"] and cand["abbrev"] == hit["abbrev"]
                    and cand["canonical"] and hit["canonical"]
                    and norm(cand["canonical"]) != norm(hit["canonical"])):
                conflicts.append({
                    "type": "same_abbrev_two_full_names",
                    "abbrev": cand["abbrev"],
                    "forms": [hit["canonical"], cand["canonical"]],
                    "detail": "abbreviation %r is mapped to two different full "
                              "names; resolve with the case owner before editing"
                              % cand["abbrev"],
                })
                continue
            if (cand["canonical"] and hit["canonical"]
                    and norm(cand["canonical"]) == norm(hit["canonical"])
                    and cand["abbrev"] and hit["abbrev"]
                    and cand["abbrev"] != hit["abbrev"]):
                conflicts.append({
                    "type": "same_full_name_two_abbrevs",
                    "canonical": hit["canonical"],
                    "abbrevs": [hit["abbrev"], cand["abbrev"]],
                    "detail": "full name %r carries two abbreviations; resolve "
                              "before editing" % hit["canonical"],
                })
                continue
            merge_unique(hit["variants"], cand["variants"])
            merge_unique(hit["banned"], cand["banned"])
            if "confirmed" not in hit["origin"]:
                hit["origin"] = hit["origin"] + "+confirmed"
        else:
            cand["id"] = "t%04d" % (len(entries) + 1)
            entries.append(cand)

    out = {
        "tool": "termbase.py lock",
        "version": 1,
        "entries": entries,
        "conflicts": conflicts,
        "summary": {"entry_count": len(entries), "conflict_count": len(conflicts)},
    }
    write_json(args.out, out)
    if conflicts:
        print("lock: %d entries, %d CONFLICTS -> %s (see conflicts list; "
              "termbase NOT safe to use)" % (len(entries), len(conflicts), args.out),
              file=sys.stderr)
        return 1
    print("lock: %d entries, 0 conflicts -> %s" % (len(entries), args.out))
    return 0


# ------------------------------------------------------------------- lint ----

MD_HEAD = re.compile(r"^#{1,6}\s+(.*)")
TEX_HEAD = re.compile(r"^\\(?:sub)*section\*?\{(.*)\}")


def section_map(text):
    """line number (1-based) -> current section title."""
    m = {}
    cur = "(prelude)"
    for i, line in enumerate(text.split("\n"), 1):
        h = MD_HEAD.match(line) or TEX_HEAD.match(line)
        if h:
            cur = h.group(1).strip()
        m[i] = cur
    return m


def build_atom_stream(text):
    """Flatten text into lowercase atoms with absolute offsets."""
    stream = []
    for m in TOKEN_RE.finditer(text):
        tok, s = m.group(0), m.start()
        idx = 0
        for sub in tok.split("-"):
            if not sub:
                continue
            j = tok.index(sub, idx)
            stream.append((sub.lower(), s + j, s + j + len(sub)))
            idx = j + len(sub)
    return stream


def sentence_initial(text, start):
    prefix = text[:start].rstrip()
    if not prefix:
        return True
    if prefix[-1] in ".!?":
        return True
    # start of a Markdown heading line
    if prefix.endswith("#"):
        return True
    return False


def cmd_lint(args):
    text = open(args.source, "r", encoding="utf-8").read()
    tb = json.load(open(args.termbase, "r", encoding="utf-8"))
    sections = section_map(text)
    stream = build_atom_stream(text)
    findings = []

    def add(severity, ftype, term_id, surface, expected, message, pos):
        line, col = locate(text, pos)
        findings.append({
            "severity": severity,
            "type": ftype,
            "term_id": term_id,
            "surface": surface,
            "expected": expected,
            "message": message,
            "locations": [{
                "line": line, "column": col,
                "section": sections.get(line, "(prelude)"),
                "context": context_of(text, pos),
            }],
        })

    for entry in tb.get("entries", []):
        tid = entry.get("id", "?")
        canonical = entry.get("canonical") or ""
        abbrev = entry.get("abbrev") or None
        variants = list(entry.get("variants") or [])
        banned = list(entry.get("banned") or [])
        policy = entry.get("first_use_policy") or "none"

        allowed_exact = set()
        for s in [canonical] + variants:
            if s:
                allowed_exact.add(s)
        if abbrev:
            allowed_exact.add(abbrev)
            allowed_exact.add(abbrev + "s")
        banned_exact = set(banned)
        banned_norm = {norm(b) for b in banned}

        # full forms = canonical + variants that are not the abbreviation itself
        full_forms = [canonical] + [
            v for v in variants
            if abbrev is None or norm(v) not in (norm(abbrev), norm(abbrev + "s"))]
        full_forms = [f for f in full_forms if f]

        # allowed patterns (longest first), each tagged with its reference surface
        allowed_surfaces = [canonical] + variants
        if abbrev:
            allowed_surfaces += [abbrev, abbrev + "s"]
        pats = []
        for s in allowed_surfaces:
            if s:
                pats.append((atoms(s), s, "allowed"))
        for b in banned:
            ba = atoms(b)
            if ba and all(ba != atoms(s) for s in allowed_surfaces if s):
                pats.append((ba, b, "banned"))
        pats.sort(key=lambda p: -len(p[0]))

        consumed = [False] * len(stream)
        matches = []  # (start, surface_text, kind, ref)
        for pa, ref, kind in pats:
            L = len(pa)
            if L == 0:
                continue
            for a in range(0, len(stream) - L + 1):
                if any(consumed[a:a + L]):
                    continue
                if tuple(x[0] for x in stream[a:a + L]) == pa:
                    start = stream[a][1]
                    end = stream[a + L - 1][2]
                    surface = text[start:end]
                    for k in range(a, a + L):
                        consumed[k] = True
                    matches.append((start, surface, kind, ref))

        matches.sort(key=lambda x: x[0])
        entry_errors = []     # section titles with error findings
        full_sections = set() # sections where an allowed full form appears
        abbrev_positions = [] # positions of abbreviation usage
        n_entry_errors = 0

        for start, surface, kind, ref in matches:
            line, _ = locate(text, start)
            sec = sections.get(line, "(prelude)")
            is_abbrev_surface = abbrev is not None and norm(surface) in (
                norm(abbrev), norm(abbrev + "s"))
            if is_abbrev_surface:
                abbrev_positions.append(start)
            if kind == "banned" or norm(surface) in banned_norm and surface not in allowed_exact:
                n_entry_errors += 1
                entry_errors.append(sec)
                add("error", "banned_variant", tid, surface, canonical,
                    "banned variant %r of %r must not appear; use %r"
                    % (surface, canonical, canonical), start)
                continue
            # allowed-pattern match: verify the exact registered surface
            if surface in allowed_exact:
                if not is_abbrev_surface:
                    full_sections.add(sec)
                continue
            # tolerate sentence-initial capitalization of the first letter only
            ok = False
            for form in allowed_exact:
                if (len(surface) == len(form)
                        and surface[1:] == form[1:]
                        and surface[0].lower() == form[0].lower()
                        and sentence_initial(text, start)):
                    ok = True
                    break
            # tolerate title-case inside Markdown/LaTeX heading lines
            if not ok:
                line_start = text.rfind("\n", 0, start) + 1
                if text[line_start:start].lstrip().startswith("#") or \
                        re.match(r"^\\(?:sub)*section", text[line_start:start + 20] or "") or \
                        text[line_start:line_start + 1] == "#" or \
                        re.match(r"^\\(?:sub)*section", text[line_start:line_start + 20] or ""):
                    for form in allowed_exact:
                        if surface.lower() == form.lower():
                            ok = True
                            break
            if ok:
                if not is_abbrev_surface:
                    full_sections.add(sec)
                continue
            n_entry_errors += 1
            entry_errors.append(sec)
            add("error", "spelling_inconsistency", tid, surface, canonical,
                "unregistered spelling/case/hyphen variant %r of %r; use the "
                "registered form %r" % (surface, canonical, ref), start)

        # abbreviation first-use policy
        if abbrev and policy == "define_at_first_use" and abbrev_positions:
            form_res = [r"\s+".join(re.escape(p) for p in f.split())
                        for f in full_forms]
            def_re = None
            if form_res:
                def_re = re.compile(
                    r"(?i)(?:" + "|".join(form_res) + r")\s*\(\s*"
                    + re.escape(abbrev) + r"s?\s*\)")
            defs = list(def_re.finditer(text)) if def_re else []
            # definition patterns that use a BANNED full form, e.g.
            # "Lithium-ion batteries (LIBs)": a definition exists but violates
            # the glossary, so the abbreviation still counts as not properly
            # defined -- reported with its own finding type.
            ban_forms = [b for b in banned
                         if norm(b) not in (norm(abbrev), norm(abbrev + "s"))]
            ban_def_re = None
            if ban_forms:
                ban_res = [r"\s+".join(re.escape(p) for p in f.split())
                           for f in ban_forms]
                ban_def_re = re.compile(
                    r"(?i)(?:" + "|".join(ban_res) + r")\s*\(\s*"
                    + re.escape(abbrev) + r"s?\s*\)")
            ban_defs = list(ban_def_re.finditer(text)) if ban_def_re else []
            first = abbrev_positions[0]
            defined_at_first = any(d.start() <= first < d.end() for d in defs)
            if not defined_at_first:
                if any(d.start() <= first < d.end() for d in ban_defs):
                    n_entry_errors += 1
                    line, _ = locate(text, first)
                    entry_errors.append(sections.get(line, "(prelude)"))
                    add("error", "definition_uses_banned_variant", tid, abbrev,
                        canonical,
                        "abbreviation %r is defined through a banned full-form "
                        "variant; rewrite the definition as \"%s (%s)\""
                        % (abbrev, canonical, abbrev), first)
                elif defs or full_forms_in_text(text, full_forms, stream):
                    n_entry_errors += 1
                    line, _ = locate(text, first)
                    entry_errors.append(sections.get(line, "(prelude)"))
                    add("error", "late_definition", tid, abbrev, canonical,
                        "abbreviation %r is used before its definition; define "
                        "it as \"%s (%s)\" at first use"
                        % (abbrev, canonical, abbrev), first)
                else:
                    n_entry_errors += 1
                    line, _ = locate(text, first)
                    entry_errors.append(sections.get(line, "(prelude)"))
                    add("error", "never_defined", tid, abbrev, canonical,
                        "abbreviation %r is used but never defined in the text"
                        % abbrev, first)
            else:
                # warning: abbreviation defined but never used outside the definition
                used_outside = any(
                    not any(d.start() <= p < d.end() for d in defs)
                    for p in abbrev_positions)
                if not used_outside:
                    add("warning", "abbrev_defined_but_unused", tid, abbrev, canonical,
                        "abbreviation %r is defined but never used afterwards; "
                        "consider dropping the abbreviation" % abbrev,
                        abbrev_positions[0])

        # cross-section drift summary
        err_secs = sorted(set(entry_errors))
        if err_secs and (len(err_secs) >= 2
                         or (full_sections and not set(err_secs) <= full_sections)):
            first_pos = next((m[0] for m in matches), 0)
            add("error", "cross_section_drift", tid, canonical, canonical,
                "term %r drifts across sections %s (registered full form appears "
                "in %s)" % (canonical, ", ".join(err_secs),
                            ", ".join(sorted(full_sections)) or "no section"),
                first_pos)

    findings.sort(key=lambda f: (f["locations"][0]["line"],
                                 f["locations"][0]["column"],
                                 f["term_id"], f["type"]))
    for i, f in enumerate(findings, 1):
        f2 = {"id": "f%04d" % i}
        f2.update(f)
        findings[i - 1] = f2

    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warning")
    out = {
        "tool": "termbase.py lint",
        "source": args.source,
        "termbase": args.termbase,
        "findings": findings,
        "summary": {
            "errors": n_err,
            "warnings": n_warn,
            "entries_checked": len(tb.get("entries", [])),
            "gate": "PASS" if n_err == 0 else "FAIL",
        },
    }
    write_json(args.out, out)
    print("lint: %d errors, %d warnings -> %s (gate %s)"
          % (n_err, n_warn, args.out, out["summary"]["gate"]))
    return 1 if n_err else 0


def full_forms_in_text(text, full_forms, stream):
    stream_atoms = tuple(x[0] for x in stream)
    for f in full_forms:
        fa = atoms(f)
        L = len(fa)
        if L == 0:
            continue
        for a in range(0, len(stream) - L + 1):
            if stream_atoms[a:a + L] == fa:
                return True
    return False


# ------------------------------------------------------------------ utils ----

def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="termbase.py",
        description="Termbase extraction, locking and full-text lint gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="mine candidate terms from a draft")
    p.add_argument("--source", required=True, help="draft text file (UTF-8)")
    p.add_argument("--out", required=True, help="candidate JSON output path")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("lock", help="merge glossary + confirmed candidates")
    p.add_argument("--candidates", required=True,
                   help="agent-reviewed candidates JSON (with 'confirmed' list)")
    p.add_argument("--glossary", default=None,
                   help="optional case-provided glossary JSON ('entries' list)")
    p.add_argument("--out", required=True, help="locked termbase output path")
    p.set_defaults(fn=cmd_lock)

    p = sub.add_parser("lint", help="full-text terminology re-scan gate")
    p.add_argument("--source", required=True, help="text to re-scan (UTF-8)")
    p.add_argument("--termbase", required=True, help="locked termbase JSON")
    p.add_argument("--out", required=True, help="lint findings JSON output path")
    p.set_defaults(fn=cmd_lint)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
