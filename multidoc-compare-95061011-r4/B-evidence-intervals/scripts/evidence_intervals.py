#!/usr/bin/env python3
"""Stdlib evidence-interval indexing, validation, and rendering primitives."""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

SOURCE_SUFFIXES = {".txt", ".pdf"}
HYPHENS = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2212\ufe58\ufe63\uff0d"), "-")


class BundleError(Exception):
    """Expected, auditable input or runtime failure."""


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"Cannot read JSON {path}: {exc}") from exc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(value) -> str:
    """Stable matching normalization; never use this to replace original text."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).translate(HYPHENS)
    return re.sub(r"\s+", " ", text).strip()


def folded(value) -> str:
    return normalize_text(value).casefold()


def literal_occurs(haystack: str, needle: str) -> bool:
    """Containment with numeric boundaries so 128 does not validate 1280."""
    hay = folded(haystack)
    need = folded(needle)
    if not need:
        return False
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", need):
        return re.search(r"(?<![\d.])" + re.escape(need) + r"(?![\d.])", hay) is not None
    return need in hay


def source_files(input_dir: Path):
    if not input_dir.is_dir():
        raise BundleError(f"Input directory does not exist: {input_dir}")
    candidates = [p for p in sorted(input_dir.rglob("*"), key=lambda p: str(p)) if p.is_file()]
    selected, ignored = [], []
    for path in candidates:
        if path.suffix.casefold() in SOURCE_SUFFIXES:
            selected.append(path)
        elif path.name not in {"case.json", "comparison-workorder.json", "evidence.json"}:
            ignored.append(str(path))
    if not selected:
        raise BundleError(f"No .txt or .pdf sources found under {input_dir}")
    return selected, ignored


def extract_source(path: Path) -> str:
    if path.suffix.casefold() == ".txt":
        try:
            return path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise BundleError(f"Cannot decode UTF-8 text {path}: {exc}") from exc
    executable = shutil.which("pdftotext")
    if not executable:
        raise BundleError(f"PDF {path} requires optional pdftotext; it is not available")
    try:
        proc = subprocess.run(
            [executable, "-layout", str(path), "-"],
            check=False, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BundleError(f"PDF extraction failed for {path}: {exc}") from exc
    if proc.returncode != 0:
        raise BundleError(f"pdftotext failed for {path}: {proc.stderr.strip()}")
    return proc.stdout


def paragraphs_for(document_id: str, text: str):
    paragraphs = []
    pages = text.split("\f")
    for page_number, page in enumerate(pages, 1):
        for chunk in re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", page):
            value = chunk.strip()
            if not value:
                continue
            ordinal = len(paragraphs) + 1
            paragraphs.append({
                "paragraph_id": f"{document_id}-p{ordinal:04d}",
                "page": page_number,
                "start": 0,
                "end": len(value),
                "text": value,
                "content_sha256": sha256_text(value),
            })
    return paragraphs


def build_index(input_dir: Path):
    documents, errors = [], []
    try:
        files, ignored = source_files(input_dir)
    except BundleError:
        raise
    used_ids = {}
    for path in files:
        document_id = path.stem
        if document_id in used_ids:
            errors.append({"source": str(path), "error": f"Duplicate source_document_id {document_id}; also used by {used_ids[document_id]}"})
            continue
        used_ids[document_id] = str(path)
        try:
            text = extract_source(path)
            paragraphs = paragraphs_for(document_id, text)
            if not paragraphs:
                raise BundleError("No locatable non-empty paragraphs")
            documents.append({
                "source_document_id": document_id,
                "file_name": path.name,
                "source_path": str(path),
                "media_type": "pdf" if path.suffix.casefold() == ".pdf" else "text",
                "content_sha256": sha256_text(text),
                "paragraphs": paragraphs,
            })
        except BundleError as exc:
            errors.append({"source": str(path), "error": str(exc)})
    if not documents and not errors:
        errors.append({"source": str(input_dir), "error": "No usable source documents"})
    changes = [{"stage": "index", "action": "indexed", "source_document_id": d["source_document_id"], "content_sha256": d["content_sha256"]} for d in documents]
    changes.extend({"stage": "index", "action": "ignored_non_source", "path": p} for p in ignored)
    changes.extend({"stage": "index", "action": "source_error", **e} for e in errors)
    return {"schema_version": "1.0", "documents": documents, "errors": errors, "change_records": changes}


def index_lookup(index):
    docs, paragraphs = {}, {}
    for doc in index.get("documents", []):
        doc_id = doc.get("source_document_id")
        docs[doc_id] = doc
        for para in doc.get("paragraphs", []):
            paragraphs[(doc_id, para.get("paragraph_id"))] = para
    return docs, paragraphs


def comparison_list(workorder):
    raw = workorder.get("comparisons", [])
    if isinstance(raw, dict):
        result = []
        for key, value in raw.items():
            item = dict(value) if isinstance(value, dict) else {}
            item.setdefault("comparison_id", key)
            result.append(item)
        return result
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def comparison_map(workorder):
    result = {}
    for comp in comparison_list(workorder):
        cid = comp.get("comparison_id")
        if isinstance(cid, str) and cid:
            result[cid] = comp
    return result


def _allowed(comp, keys):
    for key in keys:
        if key not in comp:
            continue
        value = comp[key]
        return value if isinstance(value, list) else [value]
    return None


def _scope_error(record, comp, label, value, keys):
    allowed = _allowed(comp, keys)
    if allowed is not None and folded(value) not in {folded(x) for x in allowed}:
        return f"{label} {value!r} is outside workorder scope {allowed!r}"
    return None


def validate_span(span, record, paragraphs):
    errors = []
    if not isinstance(span, dict):
        return ["span is not an object"]
    sid = span.get("span_id")
    doc_id = span.get("source_document_id")
    pid = span.get("paragraph_id")
    if not isinstance(sid, str) or not sid:
        errors.append("span_id must be a non-empty string")
    if span.get("role") not in {"support", "context", "definition"}:
        errors.append(f"{sid}: invalid role")
    if doc_id != record.get("source_document_id"):
        errors.append(f"{sid}: wrong source_document_id")
    para = paragraphs.get((doc_id, pid))
    if para is None:
        errors.append(f"{sid}: unknown document/paragraph locator {doc_id}/{pid}")
        return errors
    if span.get("page") != para["page"]:
        errors.append(f"{sid}: wrong page locator")
    if span.get("content_sha256") != para["content_sha256"]:
        errors.append(f"{sid}: paragraph content hash mismatch/version drift")
    start, end = span.get("start"), span.get("end")
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(end, bool) or not isinstance(end, int):
        errors.append(f"{sid}: offsets must be integers")
        return errors
    if not (0 <= start < end <= len(para["text"])):
        errors.append(f"{sid}: offsets outside paragraph")
        return errors
    quote = span.get("quote")
    if not isinstance(quote, str) or normalize_text(quote) != normalize_text(para["text"][start:end]):
        errors.append(f"{sid}: quote does not match original paragraph slice")
    return errors


def span_source_text(span, paragraphs):
    """Return indexed source text, never trust a mutable supplied quote for value checks."""
    if not isinstance(span, dict):
        return ""
    para = paragraphs.get((span.get("source_document_id"), span.get("paragraph_id")))
    start, end = span.get("start"), span.get("end")
    if para is None or isinstance(start, bool) or not isinstance(start, int) or isinstance(end, bool) or not isinstance(end, int):
        return ""
    if not (0 <= start < end <= len(para["text"])):
        return ""
    return para["text"][start:end]


def eval_formula(expression, operands):
    """Evaluate only arithmetic over explicitly named numeric operands."""
    tree = ast.parse(expression, mode="eval")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in operands:
            return float(operands[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        raise ValueError("formula contains a forbidden node or unknown operand")

    return visit(tree)


def validate_derived(record, span_map, paragraphs):
    errors = []
    derivation = record.get("derivation")
    if not isinstance(derivation, dict):
        return ["derived record requires a derivation object"]
    if derivation.get("result_unit") != record.get("unit"):
        errors.append("derivation result_unit differs from record unit")
    if not normalize_text(derivation.get("justification")):
        errors.append("derivation justification is required")
    raw_operands = derivation.get("operands")
    if not isinstance(raw_operands, list) or not raw_operands:
        return errors + ["derivation requires operands"]
    values, names = {}, set()
    for operand in raw_operands:
        if not isinstance(operand, dict):
            errors.append("operand is not an object")
            continue
        name = operand.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w*", name) or name in names:
            errors.append(f"invalid or duplicate operand name {name!r}")
            continue
        names.add(name)
        value = operand.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"operand {name}: non-numeric or non-finite value")
            continue
        values[name] = value
        if not normalize_text(operand.get("unit")):
            errors.append(f"operand {name}: unit required")
        span_id = operand.get("source_span_id")
        span = span_map.get(span_id)
        if span is None:
            errors.append(f"operand {name}: unknown source_span_id {span_id!r}")
        elif not literal_occurs(span_source_text(span, paragraphs), str(operand.get("value_literal", ""))):
            errors.append(f"operand {name}: literal not found in {span_id}")
    formula = derivation.get("formula")
    try:
        calculated = eval_formula(formula, values)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as exc:
        errors.append(f"formula evaluation failed: {exc}")
    else:
        value = record.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isclose(calculated, value, rel_tol=1e-9, abs_tol=1e-9):
            errors.append(f"formula result {calculated!r} does not equal record value {value!r}")
    return errors


def _base_record(record):
    """Remove private validator bookkeeping before public rendering."""
    return {k: v for k, v in record.items() if not k.startswith("_")}


def validate_records(evidence, index, workorder):
    docs, paragraphs = index_lookup(index)
    comparisons = comparison_map(workorder)
    accepted, excluded, global_errors = [], [], []
    seen_ids = set()
    records = evidence.get("records", []) if isinstance(evidence, dict) else []
    if not isinstance(records, list):
        records = []
        global_errors.append("evidence.records must be a list")
    for position, original in enumerate(records):
        record = dict(original) if isinstance(original, dict) else {}
        errors = []
        eid = record.get("evidence_id", f"record-{position + 1}")
        if not isinstance(eid, str) or not eid or eid in seen_ids:
            errors.append("evidence_id must be non-empty and unique")
        seen_ids.add(eid)
        doc_id = record.get("source_document_id")
        if doc_id not in docs:
            errors.append(f"unknown source_document_id {doc_id!r}")
        cid = record.get("comparison_id")
        comp = comparisons.get(cid)
        if comp is None:
            errors.append(f"unknown comparison_id {cid!r}")
            comp = {}
        expected_task = comp.get("task_id", comp.get("task", workorder.get("task_id", workorder.get("task"))))
        if expected_task is None or folded(record.get("task")) != folded(expected_task):
            errors.append("task does not match workorder comparison task")
        for label, keys in [
            ("metric", ("metric", "metrics", "allowed_metrics")),
            ("unit", ("unit", "units", "request_unit", "requested_unit")),
            ("material", ("material", "materials", "material_scope", "allowed_materials")),
            ("pollutant", ("pollutant", "pollutants", "pollutant_scope", "allowed_pollutants")),
            ("budget", ("budget", "budgets", "budget_scope", "allowed_budgets")),
        ]:
            if label == "unit" and record.get("value_type") == "absent" and record.get("unit") is None:
                continue
            message = _scope_error(record, comp, label, record.get(label), keys)
            if message:
                errors.append(message)
        if comp.get("field") is not None and record.get("field") != comp.get("field"):
            errors.append("field does not match comparison field")
        value_type = record.get("value_type")
        if value_type not in {"direct", "derived", "inference", "absent"}:
            errors.append(f"invalid value_type {value_type!r}")
        spans = record.get("source_spans")
        if not isinstance(spans, list):
            errors.append("source_spans must be a list")
            spans = []
        span_map = {}
        for span in spans:
            errors.extend(validate_span(span, record, paragraphs))
            if isinstance(span, dict):
                sid = span.get("span_id")
                if sid in span_map:
                    errors.append(f"duplicate span_id {sid}")
                elif isinstance(sid, str):
                    span_map[sid] = span
        support = [s for s in spans if isinstance(s, dict) and s.get("role") == "support"]
        context = [s for s in spans if isinstance(s, dict) and s.get("role") == "context"]
        if value_type != "absent":
            if len(support) != 1:
                errors.append("non-absent record requires exactly one support span")
            else:
                if record.get("paragraph_id") != support[0].get("paragraph_id"):
                    errors.append("record paragraph_id differs from support paragraph")
                if record.get("page") != support[0].get("page"):
                    errors.append("record page differs from support page")
            for qualifier in ("material", "pollutant", "metric", "unit", "budget"):
                if not normalize_text(record.get(qualifier)):
                    errors.append(f"qualifier {qualifier} is required")
            if value_type in {"direct", "derived"}:
                if not context:
                    errors.append("quantitative direct/derived record requires context")
                bindings = record.get("qualifier_evidence")
                if not isinstance(bindings, dict):
                    errors.append("qualifier_evidence object required")
                    bindings = {}
                for qualifier in ("material", "pollutant", "metric", "unit", "budget"):
                    span_ids = bindings.get(qualifier)
                    if not isinstance(span_ids, list) or not span_ids:
                        errors.append(f"qualifier {qualifier} has no evidence span binding")
                        continue
                    found = False
                    for sid in span_ids:
                        span = span_map.get(sid)
                        if span is None:
                            errors.append(f"qualifier {qualifier}: unknown span {sid!r}")
                        elif literal_occurs(span_source_text(span, paragraphs), str(record.get(qualifier, ""))):
                            found = True
                        else:
                            errors.append(f"qualifier {qualifier}: span {sid} does not contain exact qualifier")
                    if not found and span_ids:
                        errors.append(f"qualifier {qualifier} is not established by its bindings")
            value = record.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append("non-absent value must be a finite number")
            if value_type == "direct":
                if record.get("derivation") is not None:
                    errors.append("direct record must not contain derivation")
                if not support or not literal_occurs(span_source_text(support[0], paragraphs), str(record.get("value_literal", ""))):
                    errors.append("direct value literal not found in support span")
            elif value_type == "derived":
                errors.extend(validate_derived(record, span_map, paragraphs))
            elif value_type == "inference" and record.get("status") != "inference":
                errors.append("inference record must have status inference")
        else:
            if record.get("value") != "not_reported" or record.get("status") != "not_reported":
                errors.append("absent record requires value/status not_reported")
            if record.get("paragraph_id") is not None or record.get("page") is not None or spans:
                errors.append("absent record must have null locator/page and no fake spans")
            scope = record.get("search_scope")
            if not isinstance(scope, dict):
                errors.append("absent record requires searched scope")
            else:
                if scope.get("source_document_id") != doc_id:
                    errors.append("search scope document mismatch")
                if doc_id in docs:
                    expected = {p["paragraph_id"] for p in docs[doc_id]["paragraphs"]}
                    actual = scope.get("paragraph_ids")
                    if not isinstance(actual, list) or set(actual) != expected or len(actual) != len(expected):
                        errors.append("absence search must cover every indexed document paragraph exactly once")
                    if scope.get("corpus_sha256") != docs[doc_id]["content_sha256"]:
                        errors.append("absence search content hash mismatch")
                queries = scope.get("queries")
                if not isinstance(queries, list) or not queries or not all(normalize_text(q) for q in queries):
                    errors.append("absence search requires non-empty queries")
        if not normalize_text(record.get("uncertainty")):
            errors.append("record-level uncertainty statement required")
        if errors:
            excluded.append({**_base_record(record), "evidence_id": eid, "validation_errors": errors})
        else:
            clean = _base_record(record)
            clean["_span_map"] = span_map
            accepted.append(clean)
    # Conflict tests operate only on otherwise valid quantitative records.
    families = {}
    for record in accepted:
        if record.get("value_type") not in {"direct", "derived", "inference"}:
            continue
        key = tuple(folded(record.get(k)) for k in ("source_document_id", "comparison_id", "field", "material", "pollutant", "metric", "unit", "budget"))
        families.setdefault(key, []).append(record)
    conflict_ids = set()
    for family in families.values():
        values = {float(r["value"]) for r in family}
        groups = {r.get("conflict_group") for r in family}
        if len(values) > 1:
            if any(not normalize_text(g) for g in groups):
                conflict_ids.update(r["evidence_id"] for r in family)
            elif any(r.get("status") != "conflicted" for r in family):
                conflict_ids.update(r["evidence_id"] for r in family)
    grouped = {}
    for record in accepted:
        group = record.get("conflict_group")
        if normalize_text(group):
            grouped.setdefault((record.get("source_document_id"), group), []).append(record)
    for members in grouped.values():
        if len(members) < 2 or len({float(r["value"]) for r in members}) < 2:
            conflict_ids.update(r["evidence_id"] for r in members)
    if conflict_ids:
        still = []
        for record in accepted:
            if record["evidence_id"] in conflict_ids:
                excluded.append({**_base_record(record), "validation_errors": ["conflicting values require a multi-record conflict_group and status conflicted; singleton groups are invalid"]})
            else:
                still.append(record)
        accepted = still
    if not comparisons:
        global_errors.append("workorder contains no valid comparisons")
    if not records:
        global_errors.append("no evidence records supplied")
    return accepted, excluded, global_errors


def common_fields(workorder, contract):
    fields = workorder.get("common_fields", [])
    if isinstance(fields, dict):
        fields = list(fields)
    if not isinstance(fields, list):
        fields = []
    for comp in comparison_list(workorder):
        for field in comp.get("common_fields", []) if isinstance(comp.get("common_fields", []), list) else []:
            fields.append(field)
    if isinstance(contract, dict) and isinstance(contract.get("matrix_columns"), list):
        fields.extend(contract["matrix_columns"])
    required = ["source_document_id", "paragraph_id", "comparison_id", "field", "material", "pollutant", "metric", "value", "unit", "budget", "value_type", "evidence_status"]
    result = []
    for field in fields + required:
        if isinstance(field, str) and field and field not in result:
            result.append(field)
    return result


def matrix_row(record, fields):
    source = {
        "page": record.get("page") if record.get("page") is not None else "not_reported",
        "paragraph_id": record.get("paragraph_id") if record.get("paragraph_id") is not None else "not_reported",
        "evidence_status": record.get("status"),
        "comparability": record.get("comparability", "noncomparable"),
        **record,
    }
    source["page"] = record.get("page") if record.get("page") is not None else "not_reported"
    source["paragraph_id"] = record.get("paragraph_id") if record.get("paragraph_id") is not None else "not_reported"
    return {field: source.get(field, "not_reported") for field in fields}


def missing_row(doc_id, comp, fields):
    source = {
        "source_document_id": doc_id,
        "paragraph_id": "missing_evidence_record",
        "page": "missing_evidence_record",
        "comparison_id": comp.get("comparison_id"),
        "field": comp.get("field", comp.get("metric", "missing_evidence_record")),
        "metric": comp.get("metric", "missing_evidence_record"),
        "value": None,
        "value_type": "missing",
        "evidence_status": "missing_evidence_record",
        "comparability": "noncomparable",
        "uncertainty": "No validated evidence record supplied; this is not a not_reported source conclusion.",
    }
    return {field: source.get(field, "not_reported") for field in fields}


def make_synthesis(matrix, accepted):
    comparisons = {}
    for row in matrix:
        cid = row["comparison_id"]
        bucket = comparisons.setdefault(cid, {"comparison_id": cid, "records": [], "withheld": [], "aggregation": {"value": "noncomparable", "reason": "Record-level reporting only; no pooling across documents, datasets, materials, pollutants/dyes, metrics, units, or budgets."}})
        if row.get("evidence_status") in {"confirmed"} and row.get("value_type") in {"direct", "derived"}:
            bucket["records"].append({k: row.get(k) for k in ("evidence_id", "source_document_id", "paragraph_id", "field", "material", "pollutant", "metric", "value", "unit", "budget", "value_type", "comparability")})
        else:
            bucket["withheld"].append({"evidence_id": row.get("evidence_id"), "source_document_id": row.get("source_document_id"), "paragraph_id": row.get("paragraph_id"), "value": row.get("value"), "reason": row.get("evidence_status"), "comparability": row.get("comparability")})
    return {
        "strategy": "Validated record-level comparison only; no arithmetic pooling.",
        "validated_evidence_ids": [r["evidence_id"] for r in accepted],
        "comparisons": list(comparisons.values()),
        "excluded_quantitative_statuses": ["inference", "conflicted", "not_reported", "missing_evidence_record"],
    }


def markdown_table(headers, rows):
    def cell(value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str("" if value is None else value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(cell(x) for x in headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(row.get(h)) for h in headers) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def render_ledger(accepted, excluded):
    lines = ["# Evidence interval ledger", "", "Only records in the validated section feed matrix and synthesis.", ""]
    lines.append(f"## Validated records ({len(accepted)})")
    lines.append("")
    for record in accepted:
        lines.extend([
            f"### {record['evidence_id']}", "",
            f"- Document: `{record['source_document_id']}`; paragraph: `{record.get('paragraph_id') or 'not_reported'}`; page: `{record.get('page') or 'not_reported'}`",
            f"- Claim: {record.get('material')} / {record.get('pollutant')} / {record.get('metric')} = **{record.get('value')} {record.get('unit') or ''}**",
            f"- Budget: {record.get('budget')}",
            f"- Evidence class/status: `{record.get('value_type')}` / `{record.get('status')}`; comparability: `{record.get('comparability')}`",
            f"- Uncertainty: {record.get('uncertainty')}", "",
        ])
        for span in record.get("source_spans", []):
            lines.extend([
                f"#### {span['span_id']} (`{span['role']}`)", "",
                f"Locator `{span['source_document_id']}` / `{span['paragraph_id']}` / page {span['page']} / characters {span['start']}:{span['end']} / SHA-256 `{span['content_sha256']}`", "",
                "> " + span["quote"].replace("\n", "\n> ") + "", "",
            ])
        if record.get("derivation"):
            lines.extend(["Derivation (independently evaluated):", "", "```json", json.dumps(record["derivation"], ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
        if record.get("search_scope"):
            lines.extend(["Negative-evidence search scope (no quotation):", "", "```json", json.dumps(record["search_scope"], ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    lines.extend([f"## Excluded records ({len(excluded)})", ""])
    for record in excluded:
        lines.extend([f"### {record.get('evidence_id')}", "", "Excluded from matrix and quantitative synthesis:", ""])
        lines.extend(f"- {error}" for error in record.get("validation_errors", []))
        lines.append("")
    return "\n".join(lines) + "\n"


def contract_fields(contract):
    if isinstance(contract, list):
        raw = contract
    elif isinstance(contract, dict):
        if "required_fields" in contract:
            raw = contract["required_fields"]
        elif "fields" in contract:
            raw = contract["fields"]
        else:
            raw = {k: v for k, v in contract.items() if k not in {"version", "description", "matrix_columns"}}
    else:
        raw = []
    result = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                result.append((item, {}))
            elif isinstance(item, dict):
                name = item.get("name", item.get("field", item.get("key")))
                if isinstance(name, str) and name:
                    result.append((name, item))
    elif isinstance(raw, dict):
        for name, spec in raw.items():
            if isinstance(name, str):
                result.append((name, spec if isinstance(spec, dict) else {"type": spec}))
    seen, unique = set(), []
    for name, spec in result:
        if name not in seen:
            unique.append((name, spec))
            seen.add(name)
    return unique


def empty_for_spec(spec):
    kind = spec.get("type") if isinstance(spec, dict) else spec
    if kind in {"list", "array"}:
        return []
    if kind in {"dict", "object", "mapping"}:
        return {}
    if kind in {"string", "str"}:
        return ""
    if kind in {"boolean", "bool"}:
        return False
    return None


def assemble_contract(case, matrix, synthesis, comparison_scope, limitations, sources, uncertainty, changes, status):
    result, unknown = {}, []
    contract = case.get("output_contract", [])
    aliases = {
        "matrix": matrix, "common_matrix": matrix, "common_field_matrix": matrix, "comparison_matrix": matrix,
        "synthesis": synthesis, "comparison_synthesis": synthesis,
        "comparison_scope": comparison_scope, "scope": comparison_scope,
        "limitations": limitations, "limitation": limitations,
        "sources": sources, "uncertainty": uncertainty, "change_records": changes,
        "status": status, "case_id": case.get("case_id"),
    }
    for name, spec in contract_fields(contract):
        if name in aliases:
            result[name] = aliases[name]
        else:
            result[name] = empty_for_spec(spec)
            unknown.append(name)
    if unknown:
        uncertainty = uncertainty + [f"No registered producer for output_contract field(s): {', '.join(unknown)}; explicit placeholders retained."]
        result["uncertainty"] = uncertainty
        if status == "success":
            status = "partial"
    result.update({"case_id": case.get("case_id"), "status": status, "sources": sources, "uncertainty": uncertainty, "change_records": changes})
    # Reassert a requested status alias after final status determination.
    if any(name == "status" for name, _ in contract_fields(contract)):
        result["status"] = status
    return result


def validate_and_render(input_dir: Path, index, evidence, output_dir: Path):
    case_path, task_path, workorder_path = input_dir / "case.json", input_dir / "task.md", input_dir / "comparison-workorder.json"
    case = read_json(case_path)
    workorder = read_json(workorder_path)
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise BundleError("case.json requires exact non-empty case_id")
    if not isinstance(workorder, dict):
        raise BundleError("comparison-workorder.json must contain an object")
    try:
        task_text = task_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BundleError(f"Cannot read task.md: {exc}") from exc
    accepted, excluded, validation_errors = validate_records(evidence, index, workorder)
    docs, _ = index_lookup(index)
    comparisons = comparison_map(workorder)
    fields = common_fields(workorder, case.get("output_contract"))
    matrix = []
    for doc_id in sorted(docs):
        for cid, comp in comparisons.items():
            matching = [r for r in accepted if r["source_document_id"] == doc_id and r["comparison_id"] == cid]
            if matching:
                matrix.extend(matrix_row(r, fields) for r in sorted(matching, key=lambda r: r["evidence_id"]))
            else:
                matrix.append(missing_row(doc_id, comp, fields))
    synthesis = make_synthesis(matrix, accepted)
    comparison_scope = {
        "task": workorder.get("task", task_text.strip()),
        "comparisons": comparison_list(workorder),
        "common_fields": fields,
        "pooling": "disabled; distinct datasets/materials/pollutants/budgets/metrics/units remain separate",
    }
    sources = [{k: v for k, v in doc.items() if k not in {"paragraphs", "source_path"}} | {"paragraph_count": len(doc["paragraphs"])} for doc in index.get("documents", [])]
    limitations = [f"{len(excluded)} evidence record(s) excluded after validation.", "not_reported is scoped to the indexed source, not a universal absence claim.", "Inference and conflicted values are visible in the matrix but withheld from factual quantitative synthesis."]
    uncertainty = list(validation_errors)
    uncertainty.extend(f"Source indexing error: {e['source']}: {e['error']}" for e in index.get("errors", []))
    uncertainty.extend(f"Excluded evidence {r.get('evidence_id')}: {'; '.join(r.get('validation_errors', []))}" for r in excluded)
    missing = [r for r in matrix if r.get("evidence_status") == "missing_evidence_record"]
    uncertainty.extend(f"Missing evidence coverage: {r['source_document_id']} / {r['comparison_id']}" for r in missing)
    uncertainty.extend(f"{r['evidence_id']}: {r.get('uncertainty')}" for r in accepted if r.get("status") in {"conflicted", "not_reported", "inference"})
    changes = list(index.get("change_records", []))
    changes.extend([
        {"stage": "validate", "action": "accepted", "count": len(accepted)},
        {"stage": "validate", "action": "excluded", "count": len(excluded)},
        {"stage": "render", "action": "matrix_rows", "count": len(matrix)},
    ])
    usable = [r for r in matrix if r.get("evidence_status") != "missing_evidence_record"]
    if not usable:
        status = "failed"
    elif excluded or missing or index.get("errors") or validation_errors:
        status = "partial"
    else:
        status = "success"
    result = assemble_contract(case, matrix, synthesis, comparison_scope, limitations, sources, uncertainty, changes, status)
    write_json(output_dir / "matrix.json", matrix)
    write_text(output_dir / "matrix.md", "# Common-field evidence matrix\n\n" + markdown_table(fields, matrix))
    write_text(output_dir / "evidence-ledger.md", render_ledger(accepted, excluded))
    write_json(output_dir / "result.json", result)
    return result


def failure_result(input_dir: Path, output_dir: Path, message: str):
    try:
        case = read_json(input_dir / "case.json")
    except BundleError:
        case = {"case_id": None, "output_contract": []}
    uncertainty = [message]
    result = assemble_contract(case, [], {"strategy": "not_run", "comparisons": []}, {}, [], [], uncertainty, [{"stage": "runtime", "action": "failed", "error": message}], "failed")
    write_json(output_dir / "result.json", result)
    return result
