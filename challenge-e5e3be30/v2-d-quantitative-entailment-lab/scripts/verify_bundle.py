#!/usr/bin/env python3
"""Check bundle delivery constraints: UTF-8 text, size, count, paths, frontmatter."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 50
MAX_SINGLE = 500 * 1024
MAX_TOTAL = 2 * 1024 * 1024
EXPECTED_GITHUB = "https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/challenge-e5e3be30/v2-d-quantitative-entailment-lab"


def main():
    errors, files, total = [], [], 0
    for path in sorted(ROOT.rglob("*")):
        if path.is_symlink():
            errors.append("symlink forbidden: " + str(path.relative_to(ROOT)))
            continue
        if not path.is_file():
            continue
        relative = str(path.relative_to(ROOT))
        files.append(relative)
        size = path.stat().st_size
        total += size
        if size > MAX_SINGLE:
            errors.append("file exceeds 500KB: " + relative)
        if path.name.lower().startswith("readme"):
            errors.append("README forbidden: " + relative)
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            errors.append("binary/cache forbidden: " + relative)
        data = path.read_bytes()
        if b"\0" in data:
            errors.append("binary/NUL content forbidden: " + relative)
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("non-UTF8 file: " + relative)
            continue
        local_roots = ("/" + "Users/", "/" + "home/", "/" + "root/")
        if any(root in text for root in local_roots) or re.search(r"[A-Za-z]:\\\\", text):
            errors.append("machine-specific absolute path: " + relative)
    if len(files) > MAX_FILES:
        errors.append("more than 50 files")
    if total > MAX_TOTAL:
        errors.append("total size exceeds 2MB")
    github = ROOT / "GITHUB_URL.txt"
    if not github.is_file() or github.read_text(encoding="utf-8").splitlines()[0] != EXPECTED_GITHUB:
        errors.append("GITHUB_URL.txt first line differs or file missing")
    skill = ROOT / "SKILL.md"
    if not skill.is_file():
        errors.append("SKILL.md missing")
    else:
        text = skill.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            errors.append("SKILL.md frontmatter missing")
        else:
            lines = text.splitlines()
            try:
                end = lines[1:].index("---") + 1
                keys = [line.split(":", 1)[0] for line in lines[1:end] if line and not line.startswith(" ")]
                if sorted(keys) != ["description", "name"]:
                    errors.append("SKILL.md frontmatter must contain only name and description")
                values = dict(line.split(":", 1) for line in lines[1:end] if ":" in line)
                if values.get("name", "").strip() != "quantitative-entailment-lab":
                    errors.append("wrong skill name")
            except ValueError:
                errors.append("SKILL.md frontmatter not closed")
    report = {"status": "pass" if not errors else "fail", "root": "quantitative-entailment-lab",
              "file_count": len(files), "total_bytes": total, "single_file_limit": MAX_SINGLE,
              "total_limit": MAX_TOTAL, "errors": errors, "files": files}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
