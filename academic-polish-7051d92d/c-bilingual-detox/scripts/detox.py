#!/usr/bin/env python3
"""detox.py -- Chinglish (literal-translation) pattern lint for C2E academic drafts.

Python 3 standard library only. Deterministic: same input -> byte-identical output.

Subcommands:
  lint       --text <file> --out <file|->    Scan text for the built-in Chinglish
                                             pattern library (>=25 patterns, each with
                                             category + fix suggestion). Emits JSON.
  export-md  --report <json> --out <file|->  Render a lint report JSON as Markdown.

Categories: redundant-nominalization / literal-calque / connector-abuse /
            vague-subject / cliche / word-order

Boundary: patterns are surface heuristics. A hit means "a human/LLM should look",
not "this is wrong"; zero hits does not prove idiomatic English.
"""
import argparse
import json
import re
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Sentence splitting for mixed Chinese/English text.
# Terminal punctuation: 。！？!? and hard newlines. Closing quotes/brackets that
# follow a terminal mark are absorbed into the sentence.
# NOTE: this same splitter is duplicated in align.py (bundles must be
# self-contained; keep the two copies identical).
# ---------------------------------------------------------------------------
TERMINALS = set("。！？!?")
CLOSERS = set("”’\"')）)]》〉」』】")


def _dot_is_terminal(text, i):
    """'.' ends a sentence only if the next sentence plausibly starts after it
    (protects decimals '3.14' and abbreviations 'et al. reported')."""
    n = len(text)
    j = i + 1
    if j >= n:
        return True
    if text[j] == "\n":
        return True
    if text[j] != " ":
        return False  # glued: decimal, URL, abbreviation like 'al.x'
    k = j
    while k < n and text[k] == " ":
        k += 1
    if k >= n:
        return True
    c = text[k]
    return c.isupper() or c.isdigit() or ord(c) > 127 or c in "([\"'“‘"


def split_sentences(text):
    """Split mixed zh/en text into sentences with stable ids and char offsets.
    Terminals: 。！？!? , sentence-final '.', and hard newlines."""
    out = []
    n = len(text)

    def emit(a, b):
        seg = text[a:b]
        stripped = seg.strip()
        if stripped:
            lead = len(seg) - len(seg.lstrip())
            s = a + lead
            out.append({
                "id": "s%04d" % (len(out) + 1),
                "start": s,
                "end": s + len(stripped),
                "text": stripped,
            })

    seg_start = 0
    i = 0
    while i < n:
        ch = text[i]
        terminal = ch in TERMINALS or (ch == "." and _dot_is_terminal(text, i))
        if ch == "\n" or terminal:
            j = i + 1
            if terminal:
                while j < n and text[j] in CLOSERS:
                    j += 1
            emit(seg_start, j)
            i = j
            seg_start = j
        else:
            i += 1
    emit(seg_start, n)
    return out


# ---------------------------------------------------------------------------
# Pattern library. Each pattern: id, category, name, regex, suggestion.
# Full prose documentation with wrong/right example pairs lives in
# references/chinglish-patterns.md (ids match).
# ---------------------------------------------------------------------------
PATTERNS = [
    # --- literal-calque (直译腔: structure copied from Chinese word order) ---
    {"id": "LC01", "category": "literal-calque", "name": "with-the-development-of",
     "regex": r"\bwith the (rapid |continuous |sustained |steady )?(development|progress|advancement|growth) of\b",
     "suggestion": "'随着……的发展' calque. Make the concrete change the subject, e.g. 'Advances in X have ...' or start from what actually changed."},
    {"id": "LC02", "category": "literal-calque", "name": "with-increasingly",
     "regex": r"\bwith the (increasingly|growing|gradually)\b",
     "suggestion": "'随着日益……' calque. Front the real driver, e.g. 'Stricter emission standards have ...'."},
    {"id": "LC03", "category": "literal-calque", "name": "through-the-combination-of",
     "regex": r"\bthrough the combination of\b",
     "suggestion": "'通过……相结合' calque. Use 'by combining A with B'."},
    {"id": "LC04", "category": "literal-calque", "name": "in-the-previous-research",
     "regex": r"\bin the previous (research|work|study|studies)\b",
     "suggestion": "'在前期研究中' calque. Use 'In preliminary work', 'Previously', or 'In our earlier study'."},
    {"id": "LC05", "category": "literal-calque", "name": "is-easy-to-be",
     "regex": r"\b(is|are|was|were) easy to be\b",
     "suggestion": "'易……' calque ('is easy to be deactivated'). Use 'deactivates readily', 'is prone to deactivation'."},
    {"id": "LC06", "category": "literal-calque", "name": "reached-more-than",
     "regex": r"\b(reached|reaches|reaching|achieved|achieves|achieving) (more than|over|above)\b",
     "suggestion": "'达到……以上' calque. Use 'exceeded X'."},
    {"id": "LC07", "category": "literal-calque", "name": "temperature-window-of",
     "regex": r"\btemperature window of\b",
     "suggestion": "'在……温度窗口内' calque. Use 'across 150-250 °C' or 'between 150 and 250 °C'."},
    {"id": "LC08", "category": "literal-calque", "name": "with-x-structure",
     "regex": r"\bwith (a |an )?[\w-]+ structure\b",
     "suggestion": "'具有……结构' calque ('a catalyst with core-shell structure'). Use a compound modifier: 'a core-shell catalyst'."},
    {"id": "LC09", "category": "literal-calque", "name": "as-we-all-know",
     "regex": r"\b(as we all know|as is known to all|it is well known that)\b",
     "suggestion": "'众所周知' calque. Delete it; if the fact needs support, cite it."},
    {"id": "LC10", "category": "literal-calque", "name": "based-on-the-above",
     "regex": r"\bbased on the above\b",
     "suggestion": "'综上所述' calque. Use 'Taken together', 'These results suggest', or delete."},
    {"id": "LC11", "category": "literal-calque", "name": "the-mechanism-of",
     "regex": r"\bthe ([\w-]+ )?mechanism of\b",
     "suggestion": "'……的调控机制' nominal calque. Prefer a verb clause: 'how A regulates B'."},
    {"id": "LC12", "category": "literal-calque", "name": "our-country",
     "regex": r"\b(our country|our nation's)\b",
     "suggestion": "'我国' calque. Write 'China' (or 'Chinese ...')."},
    {"id": "LC13", "category": "literal-calque", "name": "promote-the-development",
     "regex": r"\bpromote the (development|progress) of\b",
     "suggestion": "'促进……的发展' calque. State what improves, e.g. 'advance X'."},
    {"id": "LC14", "category": "literal-calque", "name": "degrees-celsius-spelled-out",
     "regex": r"\bdegrees (Celsius|centigrade)\b",
     "suggestion": "Word-by-word rendering of 摄氏度. Use the unit symbol: '250 °C'."},

    # --- cliche (套话/宣传腔) ---
    {"id": "CL01", "category": "cliche", "name": "play-important-role",
     "regex": r"\bplays? an? (important|key|crucial|vital|significant) role in\b",
     "suggestion": "'发挥重要作用' boilerplate. Name the actual function: 'X limits/controls/enables Y'."},
    {"id": "CL02", "category": "cliche", "name": "has-important-significance",
     "regex": r"\b(has|have|is of|possess(?:es)?) (important|great|significant|profound) (scientific )?(significance|meaning|value)\b",
     "suggestion": "'具有重要的科学意义' boilerplate. Show the significance instead: say who can now do what."},
    {"id": "CL03", "category": "cliche", "name": "significance-and-prospects",
     "regex": r"\bscientific significance and (broad |wide |good )?(application |practical )?prospects?\b",
     "suggestion": "'科学意义和应用前景' stacked boilerplate. Replace with one concrete expected consequence."},
    {"id": "CL04", "category": "cliche", "name": "research-hotspot",
     "regex": r"\b(research )?hot ?spots?\b",
     "suggestion": "'研究热点' boilerplate. Say why the problem matters now, not that it is popular."},
    {"id": "CL05", "category": "cliche", "name": "attracted-attention",
     "regex": r"\b(attracted|attracting|attract|drawn|draws?|received|receiving) (more and more |increasing |growing |wide |extensive )?(attention|concern)\b",
     "suggestion": "'受到广泛关注' boilerplate. Replace with a fact (who uses it, what remains unsolved)."},
    {"id": "CL06", "category": "cliche", "name": "in-the-field-of",
     "regex": r"\bin the field of\b",
     "suggestion": "'在……领域' padding. Usually deletable: 'a priority in air pollution control' not 'in the field of'."},
    {"id": "CL07", "category": "cliche", "name": "provide-theoretical-basis",
     "regex": r"\bprovide(?:s|d)? (a )?(theoretical basis|technical support|theoretical guidance|solid foundation)\b",
     "suggestion": "'提供理论依据与技术支撑' boilerplate. State the concrete deliverable instead."},
    {"id": "CL08", "category": "cliche", "name": "application-prospects",
     "regex": r"\b(broad |wide |good )?(application |practical )?prospects?\b",
     "suggestion": "'应用前景' boilerplate. Replace with the actual use case and user."},
    {"id": "CL09", "category": "cliche", "name": "more-and-more",
     "regex": r"\bmore and more\b",
     "suggestion": "'越来越' filler. Quantify the trend or delete."},
    {"id": "CL10", "category": "cliche", "name": "it-is-obvious",
     "regex": r"\b(it is obvious that|obviously|it goes without saying that)\b",
     "suggestion": "'显然' filler. If it must be said, give the evidence."},
    {"id": "CL11", "category": "cliche", "name": "last-but-not-least",
     "regex": r"\blast but not least\b",
     "suggestion": "Speech cliche; delete in academic prose."},
    {"id": "CL12", "category": "cliche", "name": "a-series-of",
     "regex": r"\ba series of\b",
     "suggestion": "'一系列' vague quantifier. Give the number or the range."},

    # --- redundant-nominalization (冗余名词化) ---
    {"id": "RN01", "category": "redundant-nominalization", "name": "the-nominalization-of",
     "regex": r"\bthe (development|improvement|preparation|application|investigation|analysis|establishment|realization|utilization|optimization|modification|construction|exploration) of\b",
     "suggestion": "Nominalization where a verb exists ('the development of X' -> 'developing X' / 'X development' only if technical term). Prefer the verb."},
    {"id": "RN02", "category": "redundant-nominalization", "name": "carry-out-nominal",
     "regex": r"\b(carry out|carried out|carrying out|conduct(?:ed|ing)?|perform(?:ed|ing)?) (an? |the )?(experiment|analysis|investigation|study|measurement|characterization)s?\b",
     "suggestion": "Light verb + nominalization. Use the verb directly: 'we analyzed', not 'we carried out an analysis of'."},
    {"id": "RN03", "category": "redundant-nominalization", "name": "make-improvement",
     "regex": r"\bmake (an )?(improvement|contribution|progress|effort|adjustment)s?\b",
     "suggestion": "Use the verb: 'improve', 'contribute', 'adjust'."},
    {"id": "RN04", "category": "redundant-nominalization", "name": "x-rate",
     "regex": r"\b(conversion|adsorption|removal|degradation|recovery|survival|response) rate\b",
     "suggestion": "'转化率' nominalization. Often better as a verb: 'converted 92% of NOx' beats 'the NOx conversion rate reached 92%'."},
    {"id": "RN05", "category": "redundant-nominalization", "name": "by-means-of",
     "regex": r"\bby (means of|the use of|virtue of)\b|\busing the method of\b",
     "suggestion": "Use 'by' + gerund or 'with': 'by combining', 'with X'."},

    # --- connector-abuse (连接词滥用/堆砌) ---
    {"id": "CA01", "category": "connector-abuse", "name": "due-to-the-fact-that",
     "regex": r"\bdue to the fact that\b",
     "suggestion": "Wordy connector. Use 'because'."},
    {"id": "CA02", "category": "connector-abuse", "name": "in-order-to",
     "regex": r"\bin order to\b",
     "suggestion": "Use plain 'to' unless ambiguity forces 'in order to'."},
    {"id": "CA03", "category": "connector-abuse", "name": "sentence-initial-fanboys",
     "regex": r"^(And|But|So)\b",
     "suggestion": "Sentence-initial And/But/So copied from Chinese flow. Merge with the previous sentence or use a precise connective."},
    {"id": "CA04", "category": "connector-abuse", "name": "sentence-initial-additive",
     "regex": r"^(Moreover|Furthermore|Besides|In addition|What's more|Additionally)\b",
     "suggestion": "Stacked additive connectors ('此外/而且') flatten the argument. Keep only where the logic is genuinely additive; vary or cut."},
    {"id": "CA05", "category": "connector-abuse", "name": "firstly-secondly",
     "regex": r"\b(Firstly|Secondly|Thirdly)\b",
     "suggestion": "Use 'First', 'Second' (no -ly), and only for real enumerations."},
    {"id": "CA06", "category": "connector-abuse", "name": "not-only-but-also",
     "regex": r"\bnot only\b[^.]{0,80}?\bbut also\b",
     "suggestion": "'不仅……而且……' scaffolding is usually heavier than needed. Often 'and' suffices."},
    {"id": "CA07", "category": "connector-abuse", "name": "comma-so",
     "regex": r",\s*so\s+(this|the|we|it|these|those)\b",
     "suggestion": "Chinese '所以' joins clauses freely; English prefers a full stop, a semicolon, or a 'because'-inversion. Split or restructure."},

    # --- vague-subject (主语悬空/无主句硬译) ---
    {"id": "VS01", "category": "vague-subject", "name": "this-project-intends",
     "regex": r"\b(this|the) (project|paper|article|thesis|study) (intends? to|aims? to|plans? to|attempts? to|tries? to|proposes? to|is going to)\b",
     "suggestion": "Projects/papers cannot intend ('本项目拟'). Grant: 'We will / We aim to'. Paper: 'This study investigates X' (verb, not intention) or 'we'."},
    {"id": "VS02", "category": "vague-subject", "name": "will-be-elucidated",
     "regex": r"\bwill be (elucidated|investigated|studied|explored|discussed|analyzed|examined|clarified)\b",
     "suggestion": "Agent-less future passive hides who does the work ('将被阐明'). Grant: 'we will elucidate'; or reorder to make the phenomenon the subject."},
    {"id": "VS03", "category": "vague-subject", "name": "there-is-are",
     "regex": r"^(There is|There are|There exists?|There remain[s]?)\b",
     "suggestion": "Existential there-be as sentence opener usually hides the real subject. Find it and front it."},
    {"id": "VS04", "category": "vague-subject", "name": "it-is-important-to",
     "regex": r"^It is (important|necessary|essential|crucial|vital) (to|that)\b",
     "suggestion": "'……是很重要的' with dummy it. Name the actor: 'Researchers must ...' or state why directly."},

    # --- word-order (语序/信息重心照搬中文) ---
    {"id": "WO01", "category": "word-order", "name": "cleft-it-is-that",
     "regex": r"^It (is|was)\b[^.]{0,60}?\bthat\b",
     "suggestion": "Cleft copied from Chinese emphasis. Usually lead with the real subject instead of 'It is ... that ...'."},
    {"id": "WO02", "category": "word-order", "name": "long-preposed-adverbial",
     "regex": r"^(With|Through|By|For|Under|In|On|At)\b[^,.]{50,},",
     "suggestion": "Chinese stacks long adverbials before the subject; English wants the subject early. Front the subject, move the adverbial later or split."},
    {"id": "WO03", "category": "word-order", "name": "vague-which-clause",
     "regex": r",\s*which (has|have|is|are|was|were|can|could|will)\b",
     "suggestion": "Sentence-final ', which ...' often dangles over a whole clause (中文流水句尾巴). Make the antecedent explicit ('This finding ...') or split."},
]

CATEGORY_ORDER = [
    "literal-calque", "cliche", "redundant-nominalization",
    "connector-abuse", "vague-subject", "word-order",
]

_COMPILED = [(p, re.compile(p["regex"], re.IGNORECASE)) for p in PATTERNS]


def lint_text(text, input_name):
    sentences = split_sentences(text)
    hits = []
    for sent in sentences:
        for pat, rx in _COMPILED:
            for m in rx.finditer(sent["text"]):
                hits.append({
                    "sentence_id": sent["id"],
                    "start": sent["start"] + m.start(),
                    "end": sent["start"] + m.end(),
                    "matched": m.group(0),
                    "pattern_id": pat["id"],
                    "pattern_name": pat["name"],
                    "category": pat["category"],
                    "suggestion": pat["suggestion"],
                    "sentence": sent["text"],
                })
    hits.sort(key=lambda h: (h["sentence_id"], h["start"], h["pattern_id"]))
    by_category = {c: 0 for c in CATEGORY_ORDER}
    for h in hits:
        by_category[h["category"]] += 1
    return {
        "tool": "detox.py",
        "version": VERSION,
        "command": "lint",
        "input_file": input_name,
        "pattern_library_size": len(PATTERNS),
        "sentence_count": len(sentences),
        "hit_count": len(hits),
        "by_category": by_category,
        "sentences": sentences,
        "hits": hits,
        "caveat": ("Pattern hits are heuristic flags for review, not proven errors; "
                   "zero hits does not prove idiomatic English."),
    }


def render_markdown(report):
    lines = []
    lines.append("# Detox report (Chinglish pattern lint)")
    lines.append("")
    lines.append("> Synthetic minimal example output of `detox.py lint` (c2e-detox-polish).")
    lines.append("")
    lines.append("- Input: `%s`" % report["input_file"])
    lines.append("- Sentences scanned: %d" % report["sentence_count"])
    lines.append("- Pattern library size: %d" % report["pattern_library_size"])
    lines.append("- Total hits: %d" % report["hit_count"])
    lines.append("")
    lines.append("## Hits by category")
    lines.append("")
    lines.append("| Category | Hits |")
    lines.append("|---|---|")
    for cat in CATEGORY_ORDER:
        lines.append("| %s | %d |" % (cat, report["by_category"].get(cat, 0)))
    lines.append("")
    lines.append("## Detailed hits")
    lines.append("")
    if not report["hits"]:
        lines.append("No pattern hits. (This is a floor check only; it does not "
                     "prove idiomatic English.)")
        lines.append("")
    for h in report["hits"]:
        lines.append("### %s @ %s (%s / %s)" % (h["sentence_id"], h["pattern_id"],
                                                h["category"], h["pattern_name"]))
        lines.append("")
        lines.append("- Matched: `%s` (chars %d-%d)" % (h["matched"], h["start"], h["end"]))
        lines.append("- Sentence: %s" % h["sentence"])
        lines.append("- Suggestion: %s" % h["suggestion"])
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Boundary note: %s" % report["caveat"])
    lines.append("")
    return "\n".join(lines)


def _write_out(text, out_path):
    if out_path == "-":
        sys.stdout.write(text)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Chinglish pattern lint for Chinese-to-English academic drafts.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_lint = sub.add_parser("lint", help="Lint a text file against the pattern library.")
    p_lint.add_argument("--text", required=True, help="UTF-8 text file to scan.")
    p_lint.add_argument("--out", required=True, help="Output JSON path, or '-' for stdout.")

    p_md = sub.add_parser("export-md", help="Render a lint report JSON as Markdown.")
    p_md.add_argument("--report", required=True, help="detox report JSON from `lint`.")
    p_md.add_argument("--out", required=True, help="Output Markdown path, or '-' for stdout.")

    args = ap.parse_args(argv)

    if args.cmd == "lint":
        with open(args.text, "r", encoding="utf-8") as f:
            text = f.read()
        report = lint_text(text, args.text)
        _write_out(json.dumps(report, ensure_ascii=False, indent=2) + "\n", args.out)
        print("detox lint: %d sentences, %d hits -> %s"
              % (report["sentence_count"], report["hit_count"], args.out),
              file=sys.stderr)
    elif args.cmd == "export-md":
        with open(args.report, "r", encoding="utf-8") as f:
            report = json.load(f)
        _write_out(render_markdown(report), args.out)
        print("detox export-md: %d hits rendered -> %s"
              % (report["hit_count"], args.out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
