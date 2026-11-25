#!/usr/bin/env python3
"""audience_brief.py — deterministic editing brief for a refit work order.

Reads the slide work order (audience switch, language switch, target slide
count) and the locked terminology table, and emits a Markdown brief that the
agent follows when hand-writing refit_ops.json.  This script NEVER
auto-paraphrases scientific content — it only fixes the editorial policy.

Usage:
  audience_brief.py --workorder work/workorder.json --terms work/terms.json \
      --out work/refit_brief.md
"""

import argparse
import json
import os

PROFILES = {
    "advisor": {
        "zh": "导师",
        "focus": "progress, problems, next steps",
        "rules": [
            "Lead with what is DONE (completed milestones, validated numbers).",
            "State problems/blockers explicitly and ask for decisions.",
            "End every content slide with a concrete next step and a date/owner.",
            "Background shrinks to one sentence; motivation becomes 'why now'.",
        ],
    },
    "reviewer": {
        "zh": "评审",
        "focus": "novelty, validation, threats to validity",
        "rules": [
            "Foreground the novelty claim and how it differs from prior art.",
            "Keep validation numbers prominent; name the baselines they beat.",
            "Add threats to validity and ablations; never hide limitations.",
            "Method detail stays; remove tutorial-level background.",
        ],
    },
    "peer": {
        "zh": "同行",
        "focus": "method detail, reproducibility",
        "rules": [
            "Maximise method detail: architecture, objective, hyperparameters.",
            "Keep enough information to re-implement without the paper.",
            "Reproducibility checklist: data, seeds, runtime, code availability.",
        ],
    },
}

LANG_NAMES = {"zh": "Chinese", "en": "English", "keep-en": "keep English",
              "keep-zh": "keep Chinese"}


def _audience(a):
    return PROFILES.get(a, PROFILES["peer"])


def build_brief(workorder, terms):
    mode = workorder.get("mode", "adapt")
    a_from = workorder.get("audience_from", "peer")
    a_to = workorder.get("audience_to", "advisor")
    lang = workorder.get("language", "keep-en")
    target = workorder.get("target_slides")
    current = workorder.get("current_slides")

    p_from, p_to = _audience(a_from), _audience(a_to)
    lines = []
    lines.append("# Refit Brief — audience-refit-studio")
    lines.append("")
    lines.append("Mode: `%s` | audience: `%s` (%s) -> `%s` (%s) | language: `%s` (%s)"
                 % (mode, a_from, p_from["zh"], a_to, p_to["zh"], lang,
                    LANG_NAMES.get(lang, lang)))
    if current and target:
        lines.append("Slide count: %d -> %d" % (current, target))
    lines.append("")
    lines.append("## 1. Target audience profile: %s (%s)" % (a_to, p_to["zh"]))
    lines.append("Editorial focus: **%s**." % p_to["focus"])
    for r in p_to["rules"]:
        lines.append("- %s" % r)
    if a_from != a_to:
        lines.append("")
        lines.append("## 2. Voice change (%s -> %s)" % (a_from, a_to))
        lines.append("Shift emphasis from **%s** to **%s**. "
                     "Rewrite sentences; do not bolt a new title onto old bullets."
                     % (p_from["focus"], p_to["focus"]))
    lines.append("")
    lines.append("## 3. Language rules: `%s`" % lang)
    if lang in ("keep-en", "keep-zh"):
        lines.append("- Keep the deck's current language. No translation pass.")
    else:
        tgt = "English" if lang == "en" else "Chinese"
        lines.append("- Translate ALL body/title/notes text into %s." % tgt)
        lines.append("- Locked terms stay in their ORIGINAL surface form "
                     "(see terms.json `do_not_translate`); never translate them.")
        lines.append("- On first use after the switch, add a short gloss in the "
                     "target language in parentheses, e.g. `SynGraph (SG, our "
                     "proposed graph kernel)`; afterwards use the locked surface.")
    lines.append("")
    lines.append("## 4. Locked terminology (byte-identical survival required)")
    locked = terms.get("locked", [])
    if locked:
        lines.append("| term | kind | first page |")
        lines.append("|---|---|---|")
        for e in locked:
            lines.append("| `%s` | %s | %s |" % (e["surface"], e["kind"],
                                                 e.get("first_page", "?")))
        lines.append("")
        lines.append("Do-not-translate surfaces: %s"
                     % ", ".join("`%s`" % s for s in terms.get("do_not_translate", [])))
    else:
        lines.append("**WARNING: empty terminology table.** "
                     "Run term_table.py first; never guess terms.")
    lines.append("")
    lines.append("## 5. Compression / expansion plan")
    if target and current:
        if target < current:
            drop = current - target
            lines.append("- Need to remove %d slide(s). Merge order:" % drop)
            lines.append("  1. `background` + `gap` merge FIRST (one 'Background & "
                         "Motivation' slide).")
            lines.append("  2. Fold method detail into backup slides.")
            lines.append("  3. Only then consider dropping related-work slides.")
            lines.append("- Evidence slides NEVER lose their numbers; if the slide "
                         "goes, its numbers must be re-homed or declared dropped "
                         "in the op's `dropped_numbers`.")
            lines.append("- A `backup` role slide absorbs detail before any "
                         "numbered-result slide is touched.")
        elif target > current:
            lines.append("- Need %d new slide(s). Clone an existing slide as layout "
                         "donor (`add_slide` op) — never invent a blank layout."
                         % (target - current))
        else:
            lines.append("- Slide count already matches the target; keep the "
                         "deck's skeleton intact.")
    else:
        lines.append("- No target slide count in work order; keep count unchanged.")
    lines.append("")
    lines.append("## 6. Hard constraints for refit_ops.json")
    lines.append("- Every op carries a non-empty `reason` (the consent form).")
    lines.append("- Numbers are conserved quantities: any NEW number must already "
                 "exist verbatim in the paper text or be declared in the op's "
                 "`introduced_numbers` with a reason. Dropped numbers go in "
                 "`dropped_numbers` or the whole slide must be deleted.")
    lines.append("- Only slides named by an op may change text; everything else "
                 "stays byte-identical.")
    lines.append("- op `slide` indices are 0-based positions in the CURRENT deck "
                 "state at the moment the op is applied (ops apply in order).")
    lines.append("")
    lines.append("> The agent (not this script) writes the actual new slide text "
                 "in refit_ops.json. Facts and wording of scientific claims are "
                 "the agent's responsibility; this brief fixes only the policy.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="deterministic refit brief generator")
    ap.add_argument("--workorder", required=True)
    ap.add_argument("--terms", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.workorder, encoding="utf-8") as f:
        workorder = json.load(f)
    with open(args.terms, encoding="utf-8") as f:
        terms = json.load(f)

    brief = build_brief(workorder, terms)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(brief)
    print("wrote %s (%d lines)" % (args.out, brief.count("\n") + 1))


if __name__ == "__main__":
    main()
