#!/usr/bin/env python3
"""decompose_questions.py -- turn task text into a question ledger.

Sources of questions, in priority order:
  1. case.json ``questions`` list (if present);
  2. task.md lines that are questions (end with ? / ？) or numbered items;
  3. the case output_contract's required fields (each becomes a slot).

Each ledger entry: {q_id, text, kind, slots: {subject, comparator, metric,
setting}, source}. Slots are filled by the agent during adjudication; the
ledger only guarantees every requested item has an addressable id, so no
question can be silently dropped.
"""
import argparse
import json
import re


def from_task_md(text):
    out = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("#>*- ").strip()
        if not line or line.startswith(("```", "|---")):
            continue
        numbered = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        body = numbered.group(2) if numbered else line
        if body.rstrip().endswith(("?", "？")) or numbered:
            if len(body) >= 8:
                out.append(body)
    return out


def from_contract(contract):
    out = []

    def walk(schema, path):
        if not isinstance(schema, dict):
            return
        if schema.get("type") == "object":
            for req in schema.get("required", []):
                if req == "case_id":
                    continue
                out.append("required field: " + path + "." + req)
            for key, sub in schema.get("properties", {}).items():
                walk(sub, path + "." + key)

    walk(contract, "$")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", help="task.md path")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)

    entries = []
    for i, q in enumerate(case.get("questions", []) or [], start=1):
        entries.append({"q_id": "q%d" % i, "text": q, "source": "case.json"})
    if not entries and args.task:
        with open(args.task, encoding="utf-8") as fh:
            for i, q in enumerate(from_task_md(fh.read()), start=1):
                entries.append({"q_id": "q%d" % i, "text": q, "source": "task.md"})
    slot_entries = from_contract(case.get("output_contract", {}))
    for i, s in enumerate(slot_entries, start=1):
        entries.append({"q_id": "s%d" % i, "text": s, "source": "output_contract"})

    for e in entries:
        e.setdefault("kind", "question" if e["q_id"].startswith("q") else "contract-slot")
        e["slots"] = {"subject": None, "comparator": None, "metric": None, "setting": None}
        e["status"] = "open"
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"case_id": case.get("case_id"), "questions": entries}, fh,
                  ensure_ascii=False, indent=2)
    print(json.dumps({"questions": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
