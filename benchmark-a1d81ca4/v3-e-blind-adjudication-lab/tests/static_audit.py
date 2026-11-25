#!/usr/bin/env python3
"""Static bundle audit: task-contract source, local paths, and forbidden tooling."""

import sys
from pathlib import Path


def main():
    bundle = Path(__file__).resolve().parent.parent
    executable_files = [bundle / "run_example.sh"] + sorted((bundle / "scripts").glob("*.py"))
    errors = []
    legacy_sidecar_name = "task" + ".json"
    for path in executable_files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(bundle).as_posix()
        if legacy_sidecar_name in text or "--task " in text:
            errors.append(f"{relative}: executable workflow still references the legacy task sidecar/--task")
        local_prefixes = ("/" + "Users" + "/", "/" + "home" + "/")
        for marker in local_prefixes + ("git clone", "git push", "curl ", "wget ", "requests.", "urllib.request"):
            if marker in text:
                errors.append(f"{relative}: forbidden local-path/network/tooling marker {marker!r}")
    skill = (bundle / "SKILL.md").read_text(encoding="utf-8")
    for required in ("/input/case.json", "/input/task.md", "not_conducted_no_human_verdicts", "bash run_example.sh"):
        if required not in skill:
            errors.append(f"SKILL.md: missing {required}")
    if "--case /input/case.json" not in skill:
        errors.append("SKILL.md: finalization is not documented with case.json")
    if errors:
        for error in errors:
            print(f"STATIC AUDIT FAILURE: {error}", file=sys.stderr)
        return 1
    print("Static audit passed: case.json is authoritative, executable files ignore the legacy task sidecar, and no local absolute paths/network/git tooling were found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
