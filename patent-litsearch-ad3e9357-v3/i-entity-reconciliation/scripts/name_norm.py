#!/usr/bin/env python3
"""name_norm.py — 确定性名称规范化流水线,带完整规则审计轨迹。

每条规则实现为一个独立小函数(R1..R5)。凡规则真正改变了字符串,
即在 applied_rules 中记录 {"rule", "raw", "normalized"}(该规则作用前的
raw 与作用后的 normalized),不做静默转换。

输出每条目字段:
  raw / normalized / applied_rules[] / kind (org|person|unknown) / basis /
  tokens / core_tokens / core / canonical_suffix / cjk

退出码:0 正常;1 数据违规(输入非法);2 用法错误(文件缺失、参数错误)。
仅使用 Python 标准库。
"""
import argparse
import json
import sys
import unicodedata
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2

ORG_KEYWORDS = {
    "research", "lab", "labs", "laboratory", "laboratories", "university",
    "univ", "institute", "institut", "institution", "technologies",
    "technology", "systems", "solutions", "group", "holdings", "partners",
    "associates", "foundation", "center", "centre", "college", "school",
    "dept", "department", "division", "consortium",
}


def has_cjk(s):
    """True if s contains CJK ideographs, Japanese kana, or Korean hangul."""
    for ch in s:
        if ("一" <= ch <= "鿿") or ("㐀" <= ch <= "䶿"):
            return True
        if ("぀" <= ch <= "ヿ") or ("가" <= ch <= "힣"):
            return True
    return False


def _strip_punct(s):
    t = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
    return " ".join(t.split())


def rule_R1(s, applied):
    """R1: Unicode NFC normalization + whitespace collapse/trim."""
    t = unicodedata.normalize("NFC", s)
    t = " ".join(t.split())
    if t != s:
        applied.append({"rule": "R1", "raw": s, "normalized": t})
    return t


def rule_R2(s, applied):
    """R2: case folding (Unicode casefold; CJK unaffected)."""
    t = s.casefold()
    if t != s:
        applied.append({"rule": "R2", "raw": s, "normalized": t})
    return t


def rule_R3(s, applied):
    """R3: punctuation stripping (non-alphanumeric chars become spaces)."""
    t = _strip_punct(s)
    if t != s:
        applied.append({"rule": "R3", "raw": s, "normalized": t})
    return t


def load_suffix_forms(path):
    """Load legal_suffix_table.json -> (forms_sorted, canonical_set).

    forms_sorted: list of (form_token_tuple, canonical), longest form first.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: suffix table not found: {path}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"error: suffix table is not valid UTF-8 JSON: {e}", file=sys.stderr)
        sys.exit(EXIT_VIOLATION)
    forms = []
    canonicals = set()
    for entry in data.get("canonical_suffixes", []):
        canon = entry.get("canonical")
        if not canon:
            continue
        canonicals.add(canon)
        for form in entry.get("forms", []):
            ft = tuple(_strip_punct(form.casefold()).split())
            if ft:
                forms.append((ft, canon))
    forms.sort(key=lambda x: (-len(x[0]), x[0]))
    return forms, canonicals


def rule_R4(tokens, forms, applied):
    """R4: legal-suffix canonicalization via references/legal_suffix_table.json.

    Longest form first; one replacement per form entry; a form is never
    matched when it would consume the whole name; a span already equal to
    the canonical token is left untouched (no no-op audit entries).
    """
    canon = None
    for ft, canonical in forms:
        n = len(ft)
        if len(tokens) <= n:
            continue
        i = 0
        while i <= len(tokens) - n:
            if tuple(tokens[i:i + n]) == ft and tokens[i:i + n] != [canonical]:
                before = " ".join(tokens)
                tokens = tokens[:i] + [canonical] + tokens[i + n:]
                applied.append({"rule": "R4", "raw": before,
                                "normalized": " ".join(tokens)})
                canon = canonical
                break  # next form entry
            i += 1
    return tokens, canon


def rule_R5(tokens, canon, cjk):
    """R5: kind classification (org | person | unknown) with explicit basis."""
    if canon is not None:
        return "org", f"legal suffix canonical '{canon}' present"
    for t in tokens:
        if t in ORG_KEYWORDS:
            return "org", f"organizational keyword '{t}' present"
    if cjk and 2 <= len(tokens) <= 4:
        return "person", f"CJK personal-name pattern ({len(tokens)} tokens)"
    if 2 <= len(tokens) <= 3 and all(t.isalpha() for t in tokens):
        return "person", f"{len(tokens)}-token alphabetic personal-name pattern"
    return "unknown", "no org marker; token pattern not person-like"


def normalize_name(raw, forms, canonicals):
    applied = []
    s = rule_R1(raw, applied)
    s = rule_R2(s, applied)
    s = rule_R3(s, applied)
    tokens = s.split()
    tokens, canon = rule_R4(tokens, forms, applied)
    if canon is None:
        canon = next((t for t in tokens if t in canonicals), None)
    cjk = has_cjk(raw)
    kind, basis = rule_R5(tokens, canon, cjk)
    core_tokens = [t for t in tokens if t not in canonicals]
    return {
        "raw": raw,
        "normalized": " ".join(tokens),
        "applied_rules": applied,
        "kind": kind,
        "basis": basis,
        "tokens": tokens,
        "core_tokens": core_tokens,
        "core": " ".join(core_tokens),
        "canonical_suffix": canon,
        "cjk": cjk,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Deterministic name normalization with rule audit trail.")
    ap.add_argument("--input", required=True,
                    help="JSON list of raw name strings or objects with a 'raw' field")
    ap.add_argument("--output", required=True, help="output JSON path")
    ap.add_argument("--suffix-table", required=True,
                    help="references/legal_suffix_table.json")
    args = ap.parse_args(argv)

    forms, canonicals = load_suffix_forms(args.suffix_table)

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return EXIT_USAGE
    try:
        data = json.loads(in_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"error: input is not valid UTF-8 JSON: {e}", file=sys.stderr)
        return EXIT_VIOLATION
    if not isinstance(data, list):
        print("error: input must be a JSON list", file=sys.stderr)
        return EXIT_VIOLATION

    out_entries = []
    for idx, item in enumerate(data):
        if isinstance(item, str):
            entry, raw = {}, item
        elif isinstance(item, dict) and isinstance(item.get("raw"), str):
            entry, raw = dict(item), item["raw"]
        else:
            print(f"error: entry {idx} is neither a string nor an object "
                  f"with a string 'raw' field", file=sys.stderr)
            return EXIT_VIOLATION
        entry.update(normalize_name(raw, forms, canonicals))
        out_entries.append(entry)

    if not out_entries:
        print("warning: empty entity list; writing empty result", file=sys.stderr)

    result = {"count": len(out_entries), "names": out_entries}
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"normalized {len(out_entries)} name(s) -> {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
