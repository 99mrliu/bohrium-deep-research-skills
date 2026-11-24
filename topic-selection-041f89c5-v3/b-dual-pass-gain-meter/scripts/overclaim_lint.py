#!/usr/bin/env python3
"""overclaim_lint.py — 越界断言扫描器。

扫描 result.json / Markdown / 文本文件中的"越界断言"：无边界限定的新颖性
或空白声称（如"尚无人研究""国际首创""first ever"）。命中后检查其 ±60 字符
窗口内是否有边界限定词（"文献集/检索范围/截至/within/as of"等）；无限定
者判为违规。

用法：
  python3 overclaim_lint.py FILE [FILE ...]
退出码：0 无违规；1 存在至少一处无边界越界断言；2 文件读取失败。
仅依赖 Python 3 标准库。
"""
import json
import re
import sys
from pathlib import Path

# 越界断言模式（中英文；按短语匹配，不做词形展开）
OVERCLAIM_PATTERNS = [
    r"尚无人研究", r"尚未有人研究", r"尚无人涉足", r"无人问津",
    r"未见.{0,6}报道", r"未见.{0,6}研究",
    r"国内外首创", r"国际首创", r"世界首创", r"国内首创", r"全球首创",
    r"首次提出", r"首次报道", r"首次实现", r"首次发现",
    r"填补.{0,8}空白", r"前所未有",
    r"\bfirst\s+ever\b", r"\bfirst\s+to\b", r"\bno\s+prior\s+work\b",
    r"\bno\s+existing\s+work\b", r"\bunprecedented\b",
]
# 边界限定词：出现在命中窗口内即可为该断言"解绑"
SCOPE_WORDS = [
    "边界", "范围", "文献集", "输入材料", "检索式", "检索到", "截至",
    "在本", "本次检索", "所给", "给定", "覆盖",
    "within", "scope", "bounded", "as of", "among the provided",
    "in the provided",
]
WINDOW = 60


def iter_text_units(path):
    """产出 (位置描述, 文本) 序列。JSON 逐字段路径展开，其余按行。"""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        for i, line in enumerate(raw.splitlines(), 1):
            yield f"line {i}", line
        return

    def walk(node, trail):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, trail + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, trail + [f"[{i}]"])
        elif isinstance(node, str):
            yield ".".join(trail) or "<root>", node

    yield from walk(data, [])


def scan(path):
    findings = []
    try:
        units = list(iter_text_units(path))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"READ_ERROR {path}: {exc}")
        sys.exit(2)
    for where, text in units:
        for pat in OVERCLAIM_PATTERNS:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                lo = max(0, m.start() - WINDOW)
                hi = min(len(text), m.end() + WINDOW)
                window = text[lo:hi]
                bounded = any(w.lower() in window.lower()
                              for w in SCOPE_WORDS)
                findings.append({
                    "file": str(path), "where": where,
                    "pattern": pat, "hit": m.group(0),
                    "context": window.replace("\n", " "),
                    "bounded": bounded,
                })
    return findings


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    all_findings = []
    for path in sys.argv[1:]:
        all_findings.extend(scan(path))
    violations = [f for f in all_findings if not f["bounded"]]
    print(json.dumps({
        "files": sys.argv[1:],
        "total_hits": len(all_findings),
        "bounded_hits": len(all_findings) - len(violations),
        "violations": violations,
    }, ensure_ascii=False, indent=2))
    if violations:
        print(f"\nOVERCLAIM_LINT: {len(violations)} 处无边界越界断言", file=sys.stderr)
        sys.exit(1)
    print("\nOVERCLAIM_LINT: clean", file=sys.stderr)


if __name__ == "__main__":
    main()
