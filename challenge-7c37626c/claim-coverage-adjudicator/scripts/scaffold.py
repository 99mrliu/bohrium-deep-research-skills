#!/usr/bin/env python3
"""Bank an early partial and build the normalized source-excerpt ledger.

Only actual task, JSON/text, and XML files under the input tree are excerpted.
MathML is retained as XML; the catalog is never treated as a LaTeX answer.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from coverage_common import SCHEMA_VERSION, initial_result, write_json

TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".tsv", ".html", ".htm", ".tex"}
XML_SUFFIXES = {".xml", ".xhtml", ".jats"}
MATH_START = re.compile(r"<(?:(?:[A-Za-z_][\w.-]*):)?math\b[^>]*>", re.I)
MATH_END = re.compile(r"</(?:(?:[A-Za-z_][\w.-]*):)?math\s*>", re.I)
P_BLOCK = re.compile(r"<(?:(?:[A-Za-z_][\w.-]*):)?p\b[^>]*>.*?</(?:(?:[A-Za-z_][\w.-]*):)?p\s*>", re.I | re.S)
ID_ATTR = re.compile(r"\b(?:id|source[_-]?id|formula[_-]?id)\s*=\s*(['\"])(.*?)\1", re.I)


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def task_path(input_root: Path, explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in (input_root / "task.md", Path("/task.md"), Path("task.md")):
        if candidate.is_file():
            return candidate
    return input_root / "task.md"


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def formula_id(tag: str) -> Optional[str]:
    match = ID_ATTR.search(tag)
    return match.group(2) if match else None


class LedgerBuilder:
    def __init__(self, input_root: Path):
        self.input_root = input_root
        self.excerpts: List[Dict[str, Any]] = []
        self.skipped: List[Dict[str, str]] = []

    def relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.input_root.resolve()).as_posix()
        except ValueError:
            return path.name

    def add(self, path: Path, locator: str, text: str, kind: str,
            formula_source_id: Optional[str] = None) -> None:
        if not text:
            return
        record: Dict[str, Any] = {
            "excerpt_id": "ex-%04d" % (len(self.excerpts) + 1),
            "source_file": self.relative(path),
            "locator": locator,
            "kind": kind,
            "text": text,
        }
        if formula_source_id:
            record["formula_source_id"] = formula_source_id
        self.excerpts.append(record)

    def line_chunks(self, path: Path, text: str, kind: str) -> None:
        """Blank-line chunks with exact inclusive line ranges and exact text."""
        lines = text.splitlines(keepends=True)
        start = 0
        current_chars = 0

        def flush(end: int) -> None:
            if end > start:
                chunk = "".join(lines[start:end]).rstrip("\n")
                if chunk.strip():
                    self.add(path, "lines %d-%d" % (start + 1, end), chunk, kind)

        for index, line in enumerate(lines):
            current_chars += len(line)
            at_end = index == len(lines) - 1
            if not line.strip() or current_chars >= 12000 or at_end:
                flush(index + 1)
                start = index + 1
                current_chars = 0
        if not lines and text:
            self.add(path, "line 1", text, kind)

    def xml(self, path: Path, text: str) -> int:
        count = 0
        occupied: List[Tuple[int, int]] = []
        for match in MATH_START.finditer(text):
            # Nested MathML math elements are unusual; ignore a start contained
            # in an already captured formula rather than duplicating its tokens.
            if any(begin <= match.start() < end for begin, end in occupied):
                continue
            end_match = MATH_END.search(text, match.end())
            if not end_match:
                self.skipped.append({"source_file": self.relative(path),
                                     "reason": "unterminated MathML element at offset %d" % match.start()})
                continue
            end = end_match.end()
            occupied.append((match.start(), end))
            start_line = line_number(text, match.start())
            end_line = line_number(text, end)
            source_id = formula_id(match.group(0))
            self.add(path, "MathML element; lines %d-%d%s" % (
                start_line, end_line,
                "; id=%s" % source_id if source_id else ""),
                text[match.start():end], "mathml", source_id)
            count += 1
        for index, match in enumerate(P_BLOCK.finditer(text), 1):
            # Skip a <p> nested in a formula, but retain ordinary paragraphs
            # that themselves contain formulas as contextual evidence.
            self.add(path, "XML <p> #%d; lines %d-%d" % (
                index, line_number(text, match.start()), line_number(text, match.end())),
                match.group(0), "xml_prose")
        # Also retain generic exact line chunks for prose-rich XML. Formula/
        # paragraph indexes alone would omit titles, tables, captions, and
        # numeric cells. A pure formula catalog is already covered by dedicated
        # MathML excerpts. Formula claims still require those dedicated excerpts
        # and matching formula_source_id, not generic document lines.
        if count == 0 or P_BLOCK.search(text):
            self.line_chunks(path, text, "xml_source_lines")
        return count

    def build(self, task: Path) -> Tuple[List[str], List[str]]:
        candidates: List[Path] = []
        if task.is_file() and inside(self.input_root, task):
            candidates.append(task)
        for path in sorted(self.input_root.rglob("*")):
            if path.is_file() and path not in candidates and inside(self.input_root, path):
                candidates.append(path)
        readable: List[str] = []
        formula_ids: List[str] = []
        for path in candidates:
            suffix = path.suffix.casefold()
            source_name = self.relative(path)
            if suffix not in TEXT_SUFFIXES | XML_SUFFIXES:
                if suffix not in {"", ".json"}:
                    self.skipped.append({"source_file": source_name,
                                         "reason": "binary or unsupported text type; not excerpted"})
                continue
            try:
                text = normalized(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError) as exc:
                self.skipped.append({"source_file": source_name,
                                     "reason": "not readable as UTF-8: %s" % exc})
                continue
            readable.append(source_name)
            if suffix in XML_SUFFIXES:
                before = len(self.excerpts)
                self.xml(path, text)
                for excerpt in self.excerpts[before:]:
                    source_id = excerpt.get("formula_source_id")
                    if excerpt.get("kind") == "mathml" and source_id and source_id not in formula_ids:
                        formula_ids.append(source_id)
            else:
                kind = "task" if path == task else "text"
                self.line_chunks(path, text, kind)
        return readable, formula_ids


def missing_objects(case: Dict[str, Any], task_text: str, formula_ids: Sequence[str]) -> List[str]:
    missing: List[str] = []
    lowered = task_text.casefold()
    asks_formula = bool(re.search(r"formula|equation|mathml|公式|方程", lowered))
    asks_derivation = bool(re.search(r"deriv|推导", lowered))
    asks_recalc = bool(re.search(r"recalculat|re-?comput|substitut|verify.*number|复算|代入|数值核验", lowered))
    if asks_formula and not formula_ids:
        missing.append("formula representation")
    if asks_derivation and not formula_ids:
        missing.append("derivation objects and linked formulas")
    if asks_recalc and not formula_ids:
        missing.append("recalculable raw data or explicit numeric inputs")
    if case.get("reported_metrics") and not (case.get("artifacts") or {}) and asks_recalc:
        missing.append("per-item predictions")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/input")
    parser.add_argument("--task", help="task.md path; defaults to /input/task.md, /task.md, then ./task.md")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--out", default="/app/output")
    args = parser.parse_args()
    input_root, work, out = Path(args.input), Path(args.work), Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    case_file = input_root / "case.json"
    try:
        case = json.loads(case_file.read_text(encoding="utf-8"))
        if not isinstance(case, dict):
            raise ValueError("case.json must contain an object")
    except Exception as exc:
        print("scaffold: cannot read %s: %s" % (case_file, exc), file=sys.stderr)
        return 2

    task = task_path(input_root, args.task)
    try:
        task_text = normalized(task.read_text(encoding="utf-8"))
    except OSError as exc:
        print("scaffold: cannot read task %s: %s" % (task, exc), file=sys.stderr)
        return 2

    # This file is deliberately written before source extraction or analysis.
    write_json(out / "result.json", initial_result(case, work))
    builder = LedgerBuilder(input_root)
    readable, discovered_ids = builder.build(task)
    requested = case.get("target_formulas")
    if not isinstance(requested, list):
        requested = discovered_ids
    requested_ids = list(dict.fromkeys(
        value for value in requested if isinstance(value, str) and value
    ))
    gaps = missing_objects(case, task_text, discovered_ids)
    branch = "xml_mathml" if discovered_ids else (
        "text_or_metrics" if readable else "no_readable_objects"
    )
    source_ledger = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.get("case_id"),
        "normalization": "UTF-8; CRLF/CR converted to LF; XML and all other characters retained",
        "task_file": builder.relative(task) if inside(input_root, task) else str(task),
        "task_text": task_text,
        "branch": branch,
        "readable_sources": readable,
        "formula_source_ids": discovered_ids,
        "requested_formula_ids": requested_ids,
        "excerpts": builder.excerpts,
        "missing_objects": gaps,
        "skipped_sources": builder.skipped,
    }
    write_json(work / "source_excerpts.json", source_ledger)
    write_json(work / "claims.template.json", {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.get("case_id"),
        "task_atoms": [],
        "contradictions": [],
        "missing_objects": gaps,
        "instructions": [
            "Agent: replace this template with authored task_atoms; do not treat it as an answer.",
            "Use one or more claims per atom and quotes copied exactly from source_excerpts.json.",
            "Cover every requested formula ID, not just the first; preserve missing objects.",
        ],
    })
    write_json(work / "change_log.json", {"changes": [{
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event": "scaffold",
        "result": str(out / "result.json"),
        "source_excerpts": len(builder.excerpts),
        "formula_source_ids": discovered_ids,
        "missing_objects": gaps,
    }]})
    print("scaffold: early partial=%s source_excerpts=%s formulas=%s branch=%s" % (
        out / "result.json", work / "source_excerpts.json", requested_ids, branch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
