#!/usr/bin/env python3
"""Verify the text-only Skill bundle delivery constraints without creating bytecode."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

EXPECTED_GITHUB = "https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/challenge-e5e3be30/v2-b-counterfactual-verdict-lab"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=Path(__file__).resolve().parent.parent, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.bundle_root.resolve()
    errors: list[str] = []
    files: list[Path] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            errors.append(f"symlink is forbidden: {path.relative_to(root)}")
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            errors.append(f"non-file entry is forbidden: {path.relative_to(root)}")
            continue
        files.append(path)
        size = path.stat().st_size
        total += size
        relative = path.relative_to(root)
        if size > 500 * 1024:
            errors.append(f"file exceeds 500KB: {relative}")
        if path.name.lower().startswith("readme"):
            errors.append(f"README-like file is forbidden: {relative}")
        try:
            content = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"not UTF-8 text: {relative}: {exc}")
            continue
        if "\x00" in content:
            errors.append(f"NUL/binary content is forbidden: {relative}")
        local_user_marker = "/" + "Users/"
        local_file_marker = "file" + "://"
        if local_user_marker in content or local_file_marker in content:
            errors.append(f"local machine path is forbidden: {relative}")
        if path.suffix == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON: {relative}: {exc}")
        if path.suffix == ".py":
            try:
                compile(content, str(relative), "exec")
            except SyntaxError as exc:
                errors.append(f"Python syntax error: {relative}: {exc}")
    if len(files) > 50:
        errors.append(f"file count {len(files)} exceeds 50")
    if total > 2 * 1024 * 1024:
        errors.append(f"total bytes {total} exceed 2MB")

    skill = root / "SKILL.md"
    if not skill.is_file():
        errors.append("SKILL.md missing")
    else:
        lines = skill.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "---":
            errors.append("SKILL.md frontmatter must start at line 1")
        else:
            try:
                closing = lines[1:].index("---") + 1
            except ValueError:
                closing = -1
                errors.append("SKILL.md frontmatter is unclosed")
            if closing > 0:
                keys = [line.split(":", 1)[0].strip() for line in lines[1:closing] if line and not line.startswith(" ")]
                if keys != ["name", "description"]:
                    errors.append(f"frontmatter keys must be only name/description in order; got {keys}")
                if not lines[1].startswith("name: counterfactual-verdict-lab"):
                    errors.append("frontmatter name is not counterfactual-verdict-lab")
    github = root / "GITHUB_URL.txt"
    if not github.is_file() or github.read_text(encoding="utf-8").splitlines()[0] != EXPECTED_GITHUB:
        errors.append("GITHUB_URL.txt first line is incorrect")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {len(files)} UTF-8 text files, {total} bytes, <=50 files, each <=500KB, total <=2MB")
    print("PASS: no symlink/binary/README/local machine path; JSON and Python syntax valid")
    print("PASS: frontmatter contains only name/description; GITHUB_URL.txt first line matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
