#!/usr/bin/env python3
"""Build a deterministic, byte-attributed text-node index; stdlib Python 3 only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

SCHEMA_VERSION = "source-map/v1"
SUPPORTED = {".json", ".jsonl", ".md", ".markdown", ".txt"}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceMapError(Exception):
    pass


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def json_path(parent, key):
    if isinstance(key, int):
        return "%s[%d]" % (parent, key)
    if IDENTIFIER.match(key):
        return parent + "." + key
    return parent + "[" + json.dumps(key, ensure_ascii=False) + "]"


def atomic_json(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def looks_like_row(path, text):
    lowered = path.lower()
    stripped = text.strip()
    pipe_row = "|" in stripped and (stripped.startswith("|") or stripped.endswith("|"))
    return pipe_row or bool(re.search(r"(?:^|[.\[\]\"'])(?:row|rows|tr|tbody)(?:$|[.\[\]\"'])", lowered))


def split_string(path, text, inherited_page=None):
    """Split only textual layout boundaries; never paraphrase or infer content."""
    if not text.strip():
        return []
    # JSON strings conventionally used as a table cell stay intact.
    if "\n" not in text and "\r" not in text:
        kind = "row" if looks_like_row(path, text) else "paragraph"
        return [(kind, 1, text, inherited_page)]

    lines = text.splitlines()
    blocks = []
    pending = []
    row_count = 0
    paragraph_count = 0

    def flush():
        nonlocal pending, paragraph_count
        if pending:
            paragraph_count += 1
            blocks.append(("paragraph", paragraph_count, "\n".join(pending), inherited_page))
            pending = []

    for line in lines:
        if not line.strip():
            flush()
        elif looks_like_row(path, line):
            flush()
            row_count += 1
            blocks.append(("row", row_count, line, inherited_page))
        else:
            pending.append(line)
    flush()
    return blocks


def collect_json(value, path, page, output):
    local_page = page
    if isinstance(value, dict):
        candidate = value.get("page", page)
        if candidate is None or isinstance(candidate, (str, int, float)) and not isinstance(candidate, bool):
            local_page = candidate
    if isinstance(value, str):
        for kind, index, text, node_page in split_string(path, value, local_page):
            if text.strip():
                output.append({
                    "path": path,
                    "locator": {"kind": kind, "index": index},
                    "page": node_page,
                    "text": text,
                })
        return
    if isinstance(value, dict):
        for key in sorted(value.keys(), key=lambda item: str(item)):
            if not isinstance(key, str):
                raise SourceMapError("JSON object key is not a string at " + path)
            collect_json(value[key], json_path(path, key), local_page, output)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            collect_json(item, json_path(path, index), local_page, output)


def collect_plain(text, markdown, output):
    pending = []
    pending_start = None
    paragraph_count = 0
    row_count = 0
    headings = []

    def flush():
        nonlocal pending, pending_start, paragraph_count
        if pending:
            paragraph_count += 1
            output.append({
                "path": "$.lines[%d-%d]" % (pending_start, pending_start + len(pending) - 1),
                "locator": {"kind": "paragraph", "index": paragraph_count},
                "page": None,
                "section": list(headings),
                "text": "\n".join(pending),
            })
            pending = []
            pending_start = None

    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            flush()
            continue
        if markdown and re.match(r"^#{1,6}\s+", line):
            flush()
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            headings[:] = headings[:level - 1]
            headings.append(title)
            paragraph_count += 1
            output.append({
                "path": "$.lines[%d]" % line_number,
                "locator": {"kind": "paragraph", "index": paragraph_count},
                "page": None,
                "section": list(headings),
                "text": line,
            })
        elif looks_like_row("$", line):
            flush()
            row_count += 1
            output.append({
                "path": "$.lines[%d]" % line_number,
                "locator": {"kind": "row", "index": row_count},
                "page": None,
                "section": list(headings),
                "text": line,
            })
        else:
            if pending_start is None:
                pending_start = line_number
            pending.append(line)
    flush()


def discover(inputs):
    selected = []
    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            raise SourceMapError("input does not exist: " + raw)
        if path.is_symlink():
            raise SourceMapError("symlink input is not accepted: " + raw)
        if path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if candidate.is_symlink():
                    raise SourceMapError("symlink inside input directory is not accepted: " + str(candidate))
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED:
                    selected.append((candidate, candidate.relative_to(path).as_posix()))
            if not selected:
                raise SourceMapError("directory has no supported JSON/JSONL/MD/TXT files: " + raw)
        elif path.is_file():
            if path.suffix.lower() not in SUPPORTED:
                raise SourceMapError("unsupported source extension (expected JSON/JSONL/MD/TXT): " + raw)
            selected.append((path, path.name))
        else:
            raise SourceMapError("input is not a regular file or directory: " + raw)
    resolved = [str(path.resolve()) for path, _ in selected]
    if len(set(resolved)) != len(resolved):
        raise SourceMapError("the same source file was supplied more than once")
    labels = [label for _, label in selected]
    if len(set(labels)) != len(labels):
        raise SourceMapError("source display paths are ambiguous; supply one common directory")
    return selected


def build(inputs):
    files = discover(inputs)
    all_nodes = []
    sources = []
    warnings = []
    for path, display in files:
        raw = path.read_bytes()
        digest = sha256_bytes(raw)
        if not raw:
            raise SourceMapError("empty source file: " + display)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise SourceMapError("source is not valid UTF-8: %s: %s" % (display, error)) from error
        source_id = "src_" + sha256_bytes((display + "\0" + digest).encode("utf-8"))[:20]
        raw_nodes = []
        extension = path.suffix.lower()
        try:
            if extension == ".json":
                collect_json(json.loads(text), "$", None, raw_nodes)
            elif extension == ".jsonl":
                nonempty = 0
                for line_number, line in enumerate(text.splitlines(), 1):
                    if not line.strip():
                        continue
                    nonempty += 1
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise SourceMapError("bad JSONL at %s line %d: %s" % (display, line_number, error)) from error
                    collect_json(value, "$.lines[%d]" % line_number, None, raw_nodes)
                if not nonempty:
                    raise SourceMapError("JSONL has no records: " + display)
            else:
                collect_plain(text, extension in {".md", ".markdown"}, raw_nodes)
        except json.JSONDecodeError as error:
            raise SourceMapError("bad JSON in %s: %s" % (display, error)) from error
        if not raw_nodes:
            raise SourceMapError("no non-empty indexable strings in source: " + display)
        source_nodes = []
        seen_ids = set()
        for raw_node in raw_nodes:
            kind = raw_node["locator"]["kind"]
            index = raw_node["locator"]["index"]
            identity = json.dumps([
                source_id, raw_node["path"], kind, index, raw_node["text"]
            ], ensure_ascii=False, separators=(",", ":"))
            node_id = "node_" + sha256_bytes(identity.encode("utf-8"))[:24]
            if node_id in seen_ids:
                raise SourceMapError("stable node ID collision in " + display)
            seen_ids.add(node_id)
            node = {
                "node_id": node_id,
                "source_id": source_id,
                "source_file": display,
                "file_path": str(path.resolve()),
                "source_sha256": digest,
                "path": raw_node["path"],
                "locator": raw_node["locator"],
                "kind": kind,
                "page": raw_node.get("page"),
                "text": raw_node["text"],
                "text_sha256": sha256_bytes(raw_node["text"].encode("utf-8")),
                "normalized_text": normalized(raw_node["text"]),
            }
            if "section" in raw_node:
                node["section"] = raw_node["section"]
            source_nodes.append(node)
        sources.append({
            "source_id": source_id,
            "source_file": display,
            "file_path": str(path.resolve()),
            "format": extension.lstrip("."),
            "sha256": digest,
            "byte_count": len(raw),
            "node_count": len(source_nodes),
        })
        all_nodes.extend(source_nodes)
    if not all_nodes:
        raise SourceMapError("source map would be empty")
    return {
        "schema_version": SCHEMA_VERSION,
        "node_id_method": "SHA256(source_id, JSON path, locator, exact text), truncated to 24 hex characters",
        "normalization_for_matching_only": "NFKC then Unicode whitespace collapse; node.text remains exact",
        "sources": sources,
        "nodes": all_nodes,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Index actual UTF-8 JSON/JSONL/MD/TXT strings as source nodes.")
    parser.add_argument("inputs", nargs="+", help="source files and/or directories")
    parser.add_argument("--output", required=True, help="source-map JSON output")
    args = parser.parse_args()
    try:
        result = build(args.inputs)
        atomic_json(args.output, result)
    except (SourceMapError, OSError) as error:
        print("SOURCE_MAP_ERROR: " + str(error), file=sys.stderr)
        return 2
    print("SOURCE_MAP_OK nodes=%d sources=%d output=%s" % (
        len(result["nodes"]), len(result["sources"]), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
