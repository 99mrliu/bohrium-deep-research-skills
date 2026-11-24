#!/usr/bin/env python3
"""pipeline.py - freeze / apply-gated-edits / export for strength-conserving-polish.

Commands:
  prepare      Freeze the source text into sentence units (u0001, u0002, ...)
               with stable IDs and store the working state.
  apply-edits  Apply one batch of anchored edits. Gates (NONE skippable):
                 * review-gate   : every edit must carry a review record with
                                   non-empty `decision` and `reason`;
                                   unreviewed edits are reverted.
                 * strength-gate : any strength drift (see strength.py) without
                                   an explicit `strength_change` authorization
                                   (authorized_by: task|user + explanation)
                                   is reverted and recorded.
                 * no-op / malformed / unknown-unit guards.
               Minimal-edit metric: per-unit token similarity and token change
               rate; similarity below the threshold raises a `heavy_rewrite`
               warning (recorded, still applied if gates pass).
  export       Write polished.md, changes.json, strength-audit.json and
               conservation-report.md.

Python 3 standard library only. Deterministic: no randomness, no timestamps.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strength  # noqa: E402

STATE_FILE = "state.json"
HEAVY_REWRITE_THRESHOLD = 0.50
AUTHORIZED_BY = ("task", "user")

EDIT_TYPES = [
    "grammar", "agreement", "tense", "article", "punctuation", "spelling",
    "word-choice", "concision", "terminology-consistency",
    "clarity-restructure", "register", "other",
]

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))
        fh.write("\n")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _state_path(work):
    return os.path.join(work, STATE_FILE)


def _load_state(work):
    return _load_json(_state_path(work))


def _save_state(work, state):
    _dump_json(state, _state_path(work))


def _tokenize(text):
    return TOKEN_RE.findall(text)


def _similarity(orig, rev):
    """Token-sequence similarity in [0,1] and token change rate."""
    a, b = _tokenize(orig), _tokenize(rev)
    if not a and not b:
        return 1.0, 0.0
    ratio = difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()
    return round(ratio, 4), round(1.0 - ratio, 4)


def _unit_map(state):
    return {u["id"]: u for u in state["units"]}


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def cmd_prepare(args):
    with open(args.source, "r", encoding="utf-8") as fh:
        raw = fh.read()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    paragraphs = [p for p in re.split(r"\n\s*\n", raw) if p.strip()]
    units = []
    para_ids = []
    counter = 0
    for p_idx, para in enumerate(paragraphs):
        ids = []
        for sent in strength.split_sentences(para):
            counter += 1
            uid = "u%04d" % counter
            units.append({
                "id": uid,
                "paragraph": p_idx,
                "index": counter,
                "original": sent,
                "text": sent,
                "original_profile": strength.profile_sentence(sent),
            })
            ids.append(uid)
        para_ids.append(ids)
    state = {
        "source_file": os.path.basename(args.source),
        "source_sha256": digest,
        "paragraphs": para_ids,
        "units": units,
        "applied": [],
        "reverted": [],
        "rejected": [],
    }
    os.makedirs(args.work, exist_ok=True)
    _save_state(args.work, state)
    lines = ["%s\t%s" % (u["id"], u["text"]) for u in units]
    with open(os.path.join(args.work, "units.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("prepared %d units from %s -> %s" % (len(units), args.source, args.work))
    return 0


# ---------------------------------------------------------------------------
# apply-edits
# ---------------------------------------------------------------------------

def _review_ok(review):
    return (isinstance(review, dict)
            and review.get("decision") in ("accept", "reject")
            and isinstance(review.get("reason"), str)
            and bool(review.get("reason", "").strip()))


def _auth_ok(auth):
    return (isinstance(auth, dict)
            and auth.get("authorized_by") in AUTHORIZED_BY
            and isinstance(auth.get("explanation"), str)
            and bool(auth.get("explanation", "").strip()))


def cmd_apply_edits(args):
    state = _load_state(args.work)
    payload = _load_json(args.edits)
    batch = payload.get("batch", os.path.basename(args.edits))
    edits = payload.get("edits", [])
    units = _unit_map(state)

    n_applied = n_reverted = n_rejected = 0
    for seq, edit in enumerate(edits, start=1):
        uid = edit.get("unit", "")
        record = {
            "batch": batch,
            "seq": seq,
            "unit": uid,
            "type": edit.get("type"),
            "reason": edit.get("reason"),
            "review": edit.get("review"),
            "attempted": edit.get("revised"),
        }

        unit = units.get(uid)
        if unit is None:
            record["gate"] = "unknown-unit"
            record["detail"] = "no such frozen unit"
            state["reverted"].append(record)
            n_reverted += 1
            continue

        record["orig"] = unit["text"]

        # ---- malformed guard -------------------------------------------
        revised = edit.get("revised")
        if (not isinstance(revised, str) or not revised.strip()
                or not edit.get("type") or not edit.get("reason")):
            record["gate"] = "malformed"
            record["detail"] = "edit must carry non-empty unit/revised/type/reason"
            state["reverted"].append(record)
            n_reverted += 1
            continue

        # ---- review gate (NOT skippable) --------------------------------
        review = edit.get("review")
        if not _review_ok(review):
            record["gate"] = "review-gate"
            record["detail"] = ("missing or incomplete review record "
                                "(decision + reason required); edit reverted")
            state["reverted"].append(record)
            n_reverted += 1
            continue
        if review["decision"] == "reject":
            record["detail"] = "reviewer rejected the edit"
            state["rejected"].append(record)
            n_rejected += 1
            continue

        # ---- no-op guard -------------------------------------------------
        if strength.normalize(revised) == strength.normalize(unit["text"]):
            record["gate"] = "no-op"
            record["detail"] = "revised text identical to current text"
            state["reverted"].append(record)
            n_reverted += 1
            continue

        # ---- strength gate (NOT skippable) -------------------------------
        cmp_res = strength.compare_sentences(unit["text"], revised)
        record["drift"] = {"verdict": cmp_res["verdict"],
                           "drifts": cmp_res["drifts"]}
        auth = edit.get("strength_change")
        if cmp_res["verdict"] != "none":
            if _auth_ok(auth):
                record["authorized_drift"] = True
                record["strength_change"] = auth
            else:
                record["gate"] = "strength-gate"
                record["detail"] = ("strength drift '%s' without authorization "
                                    "(strength_change.authorized_by task|user + "
                                    "explanation); edit reverted"
                                    % cmp_res["verdict"])
                state["reverted"].append(record)
                n_reverted += 1
                continue
        else:
            record["authorized_drift"] = False

        # ---- minimal-edit metric ----------------------------------------
        sim, change_rate = _similarity(unit["text"], revised)
        record["similarity"] = sim
        record["token_change_rate"] = change_rate
        warnings = []
        if sim < HEAVY_REWRITE_THRESHOLD:
            warnings.append("heavy_rewrite")
        if edit.get("type") not in EDIT_TYPES:
            warnings.append("unknown_edit_type")
        record["warnings"] = warnings

        # ---- apply --------------------------------------------------------
        record["applied_text"] = revised
        unit["text"] = revised
        state["applied"].append(record)
        n_applied += 1

    _save_state(args.work, state)
    print("batch '%s': %d applied, %d reverted, %d rejected"
          % (batch, n_applied, n_reverted, n_rejected))
    return 0


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def _polished_text(state):
    units = _unit_map(state)
    paras = []
    for ids in state["paragraphs"]:
        paras.append(" ".join(units[i]["text"] for i in ids))
    return "\n\n".join(paras) + "\n"


def _audit(state):
    entries = []
    counts = {"none": 0}
    for bucket, status in (("applied", "applied"), ("reverted", "reverted")):
        for rec in state[bucket]:
            drift = rec.get("drift") or {"verdict": None, "drifts": []}
            verdict = drift["verdict"] or rec.get("gate", "unknown")
            counts[verdict] = counts.get(verdict, 0) + 1
            entries.append({
                "unit": rec["unit"],
                "batch": rec["batch"],
                "status": status,
                "gate": rec.get("gate"),
                "verdict": drift["verdict"],
                "drifts": drift["drifts"],
                "authorized_drift": rec.get("authorized_drift", False),
                "strength_change": rec.get("strength_change"),
                "orig": rec.get("orig"),
                "rev": rec.get("applied_text") or rec.get("attempted"),
            })
    entries.sort(key=lambda e: (e["unit"], e["batch"], e["status"]))
    return {
        "tool": "strength.py (heuristic cue lexicons; a 'none' verdict does "
                "not prove semantic equivalence)",
        "entries": entries,
        "summary": {
            "n_edits_audited": len(entries),
            "verdict_counts": counts,
            "authorized_drifts": sum(1 for e in entries if e["authorized_drift"]),
        },
    }


def _report(state):
    applied, reverted = state["applied"], state["reverted"]
    lines = []
    lines.append("# Conservation Report")
    lines.append("")
    lines.append("Source: `%s` (sha256 %s)" % (state["source_file"],
                                                state["source_sha256"][:16]))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("- frozen units: %d" % len(state["units"]))
    lines.append("- edits applied: %d" % len(applied))
    lines.append("- edits reverted by gates: %d" % len(reverted))
    lines.append("- edits rejected in review: %d" % len(state["rejected"]))
    lines.append("- authorized strength changes: %d"
                 % sum(1 for r in applied if r.get("authorized_drift")))
    lines.append("- heavy-rewrite warnings: %d"
                 % sum(1 for r in applied if "heavy_rewrite" in r.get("warnings", [])))
    lines.append("")
    lines.append("## Applied edits (what changed)")
    lines.append("")
    if applied:
        for r in applied:
            flag = ""
            if r.get("authorized_drift"):
                flag = " [AUTHORIZED strength change: %s]" % (
                    r["strength_change"]["explanation"])
            warn = (" [warning: %s]" % ",".join(r["warnings"])) if r.get("warnings") else ""
            lines.append("- `%s` (%s, batch %s, sim %.2f, drift %s)%s%s"
                         % (r["unit"], r["type"], r["batch"],
                            r["similarity"], r["drift"]["verdict"], flag, warn))
            lines.append("  - orig: %s" % r["orig"])
            lines.append("  - rev : %s" % r["applied_text"])
            lines.append("  - reason: %s" % r["reason"])
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Reverted by gates (what was refused)")
    lines.append("")
    if reverted:
        for r in reverted:
            lines.append("- `%s` gate=%s (batch %s)" % (r["unit"], r["gate"], r["batch"]))
            lines.append("  - attempted: %s" % r.get("attempted"))
            lines.append("  - detail: %s" % r["detail"])
            for d in (r.get("drift") or {}).get("drifts", []):
                lines.append("  - evidence: %s (%s) orig=%s rev=%s"
                             % (d["kind"], d["direction"],
                                json.dumps(d["evidence"].get("orig"), ensure_ascii=False),
                                json.dumps(d["evidence"].get("rev"), ensure_ascii=False)))
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Conserved hedges (what was protected)")
    lines.append("")
    conserved = []
    for u in state["units"]:
        prof = u["original_profile"]
        has_cues = bool(prof["level_hits"] or prof["quantifiers"]
                        or prof["negations"] or prof["scopers"]
                        or prof["causality"]["classes"])
        if not has_cues:
            continue
        now = strength.profile_sentence(u["text"])
        same = (now["level"] == prof["level"]
                and now["quantifiers"] == prof["quantifiers"]
                and set(now["negations"]) == set(prof["negations"])
                and set(now["scopers"]) == set(prof["scopers"])
                and set(now["causality"]["classes"]) == set(prof["causality"]["classes"]))
        if same:
            conserved.append((u, now))
    if conserved:
        for u, now in conserved:
            prof = u["original_profile"]
            cues = (sorted(now["level_hits"]) + sorted(now["quantifiers"])
                    + sorted(now["negations"]) + sorted(now["scopers"]))
            note = ""
            if sorted(now["level_hits"]) != sorted(prof["level_hits"]):
                note = " (hedge reworded at same level: %s -> %s)" % (
                    ", ".join(sorted(prof["level_hits"])) or "-",
                    ", ".join(sorted(now["level_hits"])) or "-")
            lines.append("- `%s` kept level-%d (%s); cues: %s%s"
                         % (u["id"], now["level"], now["level_name"],
                            ", ".join(cues) if cues else "-", note))
    else:
        lines.append("- (no hedged units)")
    lines.append("")
    lines.append("## Honesty boundary")
    lines.append("")
    lines.append("Strength cues are heuristic word/phrase matches. This report")
    lines.append("shows which edits tripped the gates and which hedges survived;")
    lines.append("it does NOT prove that the polished text is semantically")
    lines.append("equivalent to the source. Read the final pass yourself.")
    lines.append("")
    return "\n".join(lines)


def cmd_export(args):
    state = _load_state(args.work)
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "polished.md"), "w", encoding="utf-8") as fh:
        fh.write(_polished_text(state))
    _dump_json({"applied": state["applied"],
                "reverted": state["reverted"],
                "rejected": state["rejected"]},
               os.path.join(args.outdir, "changes.json"))
    _dump_json(_audit(state), os.path.join(args.outdir, "strength-audit.json"))
    with open(os.path.join(args.outdir, "conservation-report.md"), "w",
              encoding="utf-8") as fh:
        fh.write(_report(state))
    print("exported polished.md, changes.json, strength-audit.json, "
          "conservation-report.md -> %s" % args.outdir)
    return 0


# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Edit pipeline with mandatory review + strength gates.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prep = sub.add_parser("prepare", help="Freeze source into sentence units.")
    p_prep.add_argument("--source", required=True)
    p_prep.add_argument("--work", required=True, help="Working directory for state.")
    p_prep.set_defaults(func=cmd_prepare)

    p_app = sub.add_parser("apply-edits", help="Apply one gated batch of edits.")
    p_app.add_argument("--work", required=True)
    p_app.add_argument("--edits", required=True,
                       help='JSON: {"batch": name, "edits": [...]}.')
    p_app.set_defaults(func=cmd_apply_edits)

    p_exp = sub.add_parser("export", help="Write polished text + audit artifacts.")
    p_exp.add_argument("--work", required=True)
    p_exp.add_argument("--outdir", required=True)
    p_exp.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
