#!/usr/bin/env python3
"""Auditable high-recall retrieval; semantic verdicts always come from a review file.

Stdlib only. PDF extraction optionally calls an existing pdftotext executable.
The tool never treats a retrieval hit as support and never accesses the network.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

VERDICTS = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
HARD_REQUEST_BUDGET = 64
HARD_TIME_BUDGET = 900
KINDS = {"entity", "numeric", "synonym", "figure_table", "restriction", "other"}
CHANNELS = ("exact_phrase", "token_overlap", "numeric_match")
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "did", "do", "does",
    "for", "from", "had", "has", "have", "in", "is", "it", "its", "of", "on", "or",
    "report", "reported", "that", "the", "their", "this", "to", "was", "were", "what",
    "when", "which", "with", "paper", "study", "trial",
}


class PipelineError(Exception):
    pass


class BudgetExhausted(PipelineError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Cannot read UTF-8 JSON {path}: {exc}") from exc


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path):
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise PipelineError(f"Bad JSONL {path}:{line_no}: {exc}") from exc
    except OSError as exc:
        raise PipelineError(f"Cannot read {path}: {exc}") from exc
    return rows


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[\u2010-\u2015/-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str):
    return [t for t in re.findall(r"[^\W_]+", norm(text), re.UNICODE) if t not in STOP]


def numbers(text: str):
    # Canonical numeric values make 18%, 18.0%, and 18.0 percent comparable.
    found = []
    for match in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?", norm(text)):
        try:
            found.append(float(match.group(0)))
        except ValueError:
            pass
    return found


def type_name(spec) -> str:
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        value = spec.get("type", spec.get("kind", ""))
        if isinstance(value, list):
            value = next((v for v in value if v != "null"), "")
        return str(value)
    return ""


def default_for(spec):
    kind = type_name(spec).lower()
    if kind in {"array", "list"}:
        return []
    if kind in {"object", "dict", "dictionary", "map"}:
        return {}
    if kind in {"boolean", "bool"}:
        return False
    if kind in {"number", "integer", "float"}:
        return None
    return ""


def fields_from_collection(value):
    fields = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                fields[item] = {}
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                fields[item["name"]] = item
    elif isinstance(value, dict):
        for name, spec in value.items():
            if isinstance(name, str):
                fields[name] = spec
    return fields


def contract_fields(contract):
    """Accept list, JSON-schema-like, fields/required_fields, or direct mappings."""
    if isinstance(contract, list):
        return fields_from_collection(contract), []
    if not isinstance(contract, dict):
        return {}, ["output_contract must be a list or object"]
    for wrapper in ("schema", "result_schema"):
        if wrapper in contract:
            fields, notes = contract_fields(contract[wrapper])
            if fields:
                return fields, notes
    fields = {}
    notes = []
    properties = contract.get("properties")
    if isinstance(properties, dict):
        fields.update(fields_from_collection(properties))
    for key in ("fields", "result_fields", "output_fields"):
        if key in contract:
            fields.update(fields_from_collection(contract[key]))
    for key in ("required", "required_fields"):
        if key in contract:
            for name, spec in fields_from_collection(contract[key]).items():
                fields.setdefault(name, spec)
    controls = {
        "type", "properties", "fields", "result_fields", "output_fields", "required",
        "required_fields", "additionalProperties", "description", "title", "$schema",
    }
    if not fields:
        for key, value in contract.items():
            if key not in controls:
                fields[key] = value
    if not fields:
        notes.append("output_contract declared no discoverable fields")
    return fields, notes


def shape_value(name, value, spec):
    kind = type_name(spec).lower()
    if kind in {"array", "list"} and not isinstance(value, list):
        return [value] if value not in (None, "") else []
    if kind in {"object", "dict", "dictionary", "map"} and not isinstance(value, dict):
        if isinstance(value, list):
            return {"items": value}
        return {"value": value}
    if kind in {"string", "str"} and value is not None and not isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return value


def claims_from(value):
    rows = value if isinstance(value, list) else value.get("claims", []) if isinstance(value, dict) else []
    claims = []
    for index, item in enumerate(rows, 1):
        if not isinstance(item, dict):
            raise PipelineError("Every claim must be an object")
        claim = dict(item)
        claim["claim_id"] = str(claim.get("claim_id", claim.get("id", f"claim-{index:03d}")))
        claim["question"] = str(claim.get("question", claim.get("claim", ""))).strip()
        if not claim["question"]:
            raise PipelineError(f"{claim['claim_id']} has no question; claims are questions, not assumed facts")
        claims.append(claim)
    if not claims:
        raise PipelineError("No claims supplied")
    if len({c["claim_id"] for c in claims}) != len(claims):
        raise PipelineError("Duplicate claim_id")
    return claims


def parse_variants(family):
    raw = family.get("variants", family.get("queries", []))
    if isinstance(raw, str):
        raw = [raw]
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append({"text": item, "channels": list(CHANNELS)})
        elif isinstance(item, dict) and str(item.get("text", item.get("query", ""))).strip():
            channels = item.get("channels", family.get("channels", list(CHANNELS)))
            if isinstance(channels, str):
                channels = [channels]
            unknown = set(channels) - set(CHANNELS)
            if unknown:
                raise PipelineError(f"Unknown retrieval channels: {sorted(unknown)}")
            result.append({"text": str(item.get("text", item.get("query"))), "channels": channels})
    return result


def planned_families(claim):
    families = claim.get("query_families")
    if families is None:
        # A deliberately insufficient bootstrap. The Agent must expand it before
        # an insufficient_evidence certificate can be issued.
        families = [{"family_id": "bootstrap-entity", "kind": "entity", "variants": [claim["question"]]}]
    normalized = []
    for index, family in enumerate(families, 1):
        family = dict(family)
        family["family_id"] = str(family.get("family_id", family.get("id", f"family-{index:02d}")))
        family["kind"] = str(family.get("kind", "other"))
        if family["kind"] not in KINDS:
            raise PipelineError(f"Unknown query family kind: {family['kind']}")
        family["variants"] = parse_variants(family)
        if not family["variants"]:
            raise PipelineError(f"Empty query family {claim['claim_id']}/{family['family_id']}")
        for idx, variant in enumerate(family["variants"], 1):
            variant["variant_id"] = str(variant.get("variant_id", f"{family['family_id']}-q{idx:02d}"))
        normalized.append(family)
    return normalized


def load_resources(explicit: str | None):
    path = Path(explicit) if explicit else Path(__file__).resolve().parents[1] / "environment" / "resources.yaml"
    values = {"max_requests": HARD_REQUEST_BUDGET, "max_seconds": HARD_TIME_BUDGET, "path": None, "_started_monotonic": time.monotonic()}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineError(f"Cannot read resources.yaml: {exc}") from exc
    # Parse only the flat integer settings needed here; no YAML dependency.
    aliases = {"max_requests": "max_requests", "request_budget": "max_requests", "max_seconds": "max_seconds", "time_budget_seconds": "max_seconds"}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        if key in aliases:
            try:
                values[aliases[key]] = int(value)
            except ValueError as exc:
                raise PipelineError(f"Non-integer resource budget: {key}={value}") from exc
    values["max_requests"] = max(1, min(HARD_REQUEST_BUDGET, values["max_requests"]))
    values["max_seconds"] = max(1, min(HARD_TIME_BUDGET, values["max_seconds"]))
    values["path"] = path.name
    return values


def blank_result(case, claims, contract, resources):
    specs, notes = contract_fields(contract)
    result = {name: default_for(spec) for name, spec in specs.items()}
    aliases = {
        "claims", "claim_results", "results", "verdicts", "assessments",
        "evidence_certificates", "no_evidence_certificates", "search_audit",
        "retrieval_plan", "recall_coverage", "summary",
    }
    values = {
        "case_id": case.get("case_id", ""),
        "status": "partial",
        "sources": [],
        "uncertainty": ["SYNTHETIC pipeline initialized" if case.get("synthetic") else "Pipeline initialized; retrieval and Agent review are incomplete"] + notes,
        "change_records": [{"stage": "skeleton", "at": now(), "detail": "Partial result written before source extraction or retrieval"}],
    }
    for name in aliases:
        values[name] = [] if name not in {"search_audit", "retrieval_plan", "recall_coverage", "summary"} else {}
    canonical = {"claim_results", "no_evidence_certificates", "search_audit", "retrieval_plan", "recall_coverage"}
    for name, value in values.items():
        if name in specs or name in canonical or name in {"case_id", "status", "sources", "uncertainty", "change_records"}:
            result[name] = shape_value(name, value, specs.get(name, {}))
    result["status"] = "partial"
    result["case_id"] = case.get("case_id", "")
    result["_contract_specs"] = specs  # Removed before output; internal helper only.
    return result


def clean_result(result):
    result.pop("_contract_specs", None)
    return result


def change(result, stage, detail):
    record = {"stage": stage, "at": now(), "detail": detail}
    target = result.setdefault("change_records", [])
    if isinstance(target, list):
        target.append(record)
    elif isinstance(target, dict):
        target.setdefault("items", []).append(record)
    else:
        result["change_records"] = [target, record]


def add_uncertainty(result, message):
    target = result.setdefault("uncertainty", [])
    if isinstance(target, list):
        target.append(message)
    elif isinstance(target, dict):
        target.setdefault("items", []).append(message)
    else:
        result["uncertainty"] = [str(target), message]


def discover_documents(input_dir: Path):
    docs = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in {".txt", ".md", ".pdf"}:
            continue
        if path.name == "task.md":
            continue
        docs.append(path)
    if not docs:
        raise PipelineError(f"No .txt, .md, or .pdf paper sources in {input_dir}")
    return docs


def extract_pages(input_dir: Path, resources):
    started = resources["_started_monotonic"]
    request_count = 0
    pages = []
    sources = []
    converter = shutil.which("pdftotext")
    for source_index, path in enumerate(discover_documents(input_dir), 1):
        if time.monotonic() - started > resources["max_seconds"]:
            raise BudgetExhausted("Time budget exhausted during source extraction")
        source_id = f"source-{source_index:03d}"
        relative = path.relative_to(input_dir).as_posix()
        if path.suffix.lower() == ".pdf":
            if converter is None:
                raise PipelineError("PDF found but pdftotext is unavailable; PDF source was not read")
            request_count += 1
            if request_count > resources["max_requests"]:
                raise BudgetExhausted("Request budget exhausted by PDF conversions")
            try:
                proc = subprocess.run(
                    [converter, "-layout", "-enc", "UTF-8", str(path), "-"],
                    check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=max(1, resources["max_seconds"] - int(time.monotonic() - started)),
                )
                text = proc.stdout.decode("utf-8")
            except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
                raise PipelineError(f"pdftotext failed for {relative}: {exc}") from exc
            if proc.returncode != 0:
                raise PipelineError(f"pdftotext failed for {relative}: {proc.stderr.decode('utf-8', 'replace').strip()}")
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise PipelineError(f"Cannot read paper text {relative}: {exc}") from exc
        chunks = text.split("\f")
        if chunks and not chunks[-1].strip():
            chunks.pop()
        if not chunks:
            chunks = [""]
        page_ids = []
        for page_number, chunk in enumerate(chunks, 1):
            page_id = f"{source_id}:p{page_number:04d}"
            page_ids.append(page_id)
            pages.append({"page_id": page_id, "source_id": source_id, "source": relative, "page": page_number, "text": chunk})
        sources.append({
            "source_id": source_id, "path": relative, "media_type": "pdf" if path.suffix.lower() == ".pdf" else "text",
            "page_count": len(chunks), "page_ids": page_ids, "characters": sum(len(c) for c in chunks),
            "extraction": "pdftotext -layout" if path.suffix.lower() == ".pdf" else "UTF-8 direct read",
        })
    return pages, sources, {"local_conversion_requests": request_count, "network_requests": 0}


def make_snippet(text, query):
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= 1400:
        return compact
    qnorm = norm(query)
    cnorm = norm(compact)
    position = cnorm.find(qnorm)
    if position < 0:
        qtokens = tokens(query)
        positions = [cnorm.find(token) for token in qtokens if cnorm.find(token) >= 0]
        position = min(positions) if positions else 0
    start = max(0, position - 500)
    end = min(len(compact), start + 1400)
    return compact[start:end]


def page_id_for(pages, page):
    return page["page_id"]


def execute_retrieval(claims, pages, resources):
    started = resources["_started_monotonic"]
    audits = []
    candidates = []
    page_norms = {p["page_id"]: norm(p["text"]) for p in pages}
    page_tokens = {p["page_id"]: set(tokens(p["text"])) for p in pages}
    page_numbers = {p["page_id"]: set(numbers(p["text"])) for p in pages}
    expected_page_ids = [p["page_id"] for p in pages]
    for claim in claims:
        fused = defaultdict(float)
        details = defaultdict(list)
        for family in planned_families(claim):
            channel_page_scores = defaultdict(lambda: defaultdict(float))
            for variant in family["variants"]:
                if time.monotonic() - started > resources["max_seconds"]:
                    raise BudgetExhausted("Time budget exhausted during retrieval")
                text = variant["text"]
                qnorm = norm(text)
                qtokens = set(tokens(text))
                qnumbers = set(numbers(text))
                channel_hits = {}
                for channel in variant["channels"]:
                    hits = []
                    for page in pages:
                        pid = page_id_for(pages, page)
                        score = 0.0
                        if channel == "exact_phrase" and qnorm and qnorm in page_norms[pid]:
                            score = 1.0 + len(qnorm) / 1000.0
                        elif channel == "token_overlap" and qtokens:
                            matched = qtokens & page_tokens[pid]
                            required = min(2, len(qtokens))
                            coverage = len(matched) / len(qtokens)
                            if len(matched) >= required and coverage >= 0.34:
                                score = coverage + math.log1p(len(matched)) / 10.0
                        elif channel == "numeric_match" and qnumbers:
                            matched = qnumbers & page_numbers[pid]
                            if matched:
                                score = len(matched) / len(qnumbers)
                        if score > 0:
                            hits.append(pid)
                            channel_page_scores[channel][pid] = max(channel_page_scores[channel][pid], score)
                    channel_hits[channel] = hits
                audits.append({
                    "claim_id": claim["claim_id"], "family_id": family["family_id"], "kind": family["kind"],
                    "variant_id": variant["variant_id"], "query": text, "channels": variant["channels"],
                    "planned_pages": expected_page_ids, "pages_scanned": expected_page_ids,
                    "full_document_scope": True, "channel_hit_page_ids": channel_hits,
                    "semantic_verdict": None, "note": "A hit is only a candidate, never support.",
                })
            channel_ranks = {}
            for channel, score_by_page in channel_page_scores.items():
                ranked = sorted(score_by_page, key=lambda pid: (-score_by_page[pid], pid))
                channel_ranks[channel] = {pid: rank for rank, pid in enumerate(ranked, 1)}
            family_pages = set().union(*(set(scores) for scores in channel_page_scores.values())) if channel_page_scores else set()
            for pid in family_pages:
                contributions = [1.0 / (60.0 + channel_ranks[ch][pid]) for ch in channel_ranks if pid in channel_ranks[ch]]
                fused[pid] += sum(contributions)
                details[pid].append({"family_id": family["family_id"], "kind": family["kind"]})
        for pid, score in fused.items():
            page = next(p for p in pages if p["page_id"] == pid)
            matching_audits = [a for a in audits if a["claim_id"] == claim["claim_id"] and pid in set().union(*(set(v) for v in a["channel_hit_page_ids"].values()))]
            query = matching_audits[0]["query"] if matching_audits else claim["question"]
            digest = hashlib.sha256(f"{claim['claim_id']}|{pid}".encode("utf-8")).hexdigest()[:12]
            candidates.append({
                "candidate_id": f"cand-{digest}", "claim_id": claim["claim_id"], "page_id": pid,
                "source_id": page["source_id"], "source": page["source"], "page": page["page"],
                "fused_score": round(score, 6), "origin_families": sorted({d["family_id"] for d in details[pid]}),
                "matched_variants": [{"family_id": a["family_id"], "variant_id": a["variant_id"], "query": a["query"], "channels": [ch for ch, hits in a["channel_hit_page_ids"].items() if pid in hits]} for a in matching_audits],
                "context": make_snippet(page["text"], query), "review_status": "unreviewed",
                "exclusion_reason": None, "semantic_note": "Retrieval candidate only; Agent adjudication required.",
            })
    candidates.sort(key=lambda c: (c["claim_id"], -c["fused_score"], c["candidate_id"]))
    return audits, candidates


def shape_all_fields(result, contract):
    specs, notes = contract_fields(contract)
    for note in notes:
        add_uncertainty(result, note)
    for name, spec in specs.items():
        result.setdefault(name, default_for(spec))
        result[name] = shape_value(name, result[name], spec)
    clean_result(result)
    return result


def prepare(args):
    input_dir = Path(args.input)
    work = Path(args.work)
    output = Path(args.output)
    work.mkdir(parents=True, exist_ok=True)
    case = read_json(input_dir / "case.json")
    if not isinstance(case, dict) or "case_id" not in case or "output_contract" not in case:
        raise PipelineError("case.json requires case_id and output_contract")
    # Fail closed on missing required textual inputs; task.md is read to ensure it exists.
    try:
        (input_dir / "task.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineError(f"Cannot read task.md: {exc}") from exc
    claims_path = Path(args.claims) if args.claims else input_dir / "claims-to-verify.json"
    claims = claims_from(read_json(claims_path))
    resources = load_resources(args.resources)
    contract = case["output_contract"]
    result = blank_result(case, claims, contract, resources)
    clean_result(result)
    write_json(output, result)  # Required partial skeleton comes first.
    try:
        pages, sources, usage = extract_pages(input_dir, resources)
        write_jsonl(work / "pages.jsonl", pages)
        write_json(work / "sources.json", sources)
        result["sources"] = sources
        change(result, "sources_loaded", f"Loaded {len(sources)} source(s), {len(pages)} page(s)")
        for claim in claims:
            claim["query_families"] = planned_families(claim)
        plan = {
            "label": args.label, "claims": claims,
            "coverage": {"page_ids": [p["page_id"] for p in pages], "sources": sources},
            "policy": {"candidate_cap": None, "semantic_verdicts_from_retrieval": False, "resources": {k: v for k, v in resources.items() if not k.startswith("_")}, "usage": usage},
        }
        write_json(work / "retrieval-plan.json", plan)
        audits, candidates = execute_retrieval(claims, pages, resources)
        write_jsonl(work / "search-audit.jsonl", audits)
        write_jsonl(work / "candidates.jsonl", candidates)
        result["retrieval_plan"] = {"claim_count": len(claims), "query_variant_count": len(audits), "full_document_pages": len(pages)}
        result["search_audit"] = {"variant_count": len(audits), "every_variant_full_scope": all(a["full_document_scope"] for a in audits)}
        result["claim_results"] = [{"claim_id": c["claim_id"], "question": c["question"], "verdict": None, "status": "awaiting_Agent_review"} for c in claims]
        specs, _ = contract_fields(contract)
        for alias in ("verdicts", "claims", "assessments", "results"):
            if alias in specs:
                result[alias] = result["claim_results"]
        add_uncertainty(result, "All candidates remain unreviewed; retrieval hits are not evidence verdicts")
        change(result, "retrieval_complete", f"Executed {len(audits)} query variants; generated {len(candidates)} unreviewed candidates")
        result = shape_all_fields(result, contract)
        write_json(output, result)
        return 0
    except (PipelineError, BudgetExhausted) as exc:
        add_uncertainty(result, str(exc))
        change(result, "partial_failure", str(exc))
        result["status"] = "partial"
        clean_result(result)
        write_json(output, shape_all_fields(result, contract))
        print(f"PARTIAL: {exc}", file=sys.stderr)
        return 2


def review_map(review, key):
    raw = review.get(key, {})
    if isinstance(raw, list):
        id_key = "claim_id" if key == "claim_reviews" else "candidate_id"
        return {str(item[id_key]): item for item in raw if isinstance(item, dict) and id_key in item}
    return raw if isinstance(raw, dict) else {}


def certificate_for(claim, claim_review, candidates, audits, coverage):
    cid = claim["claim_id"]
    own_candidates = [c for c in candidates if c["claim_id"] == cid]
    own_audits = [a for a in audits if a["claim_id"] == cid]
    families = claim.get("query_families", [])
    family_ids = {f["family_id"] for f in families}
    executed_ids = {a["family_id"] for a in own_audits}
    kinds = {f["kind"] for f in families}
    expected_pages = set(coverage.get("page_ids", []))
    scope_ok = bool(expected_pages) and bool(own_audits) and all(set(a.get("pages_scanned", [])) == expected_pages for a in own_audits)
    all_variants = [(f["family_id"], v["variant_id"]) for f in families for v in f["variants"]]
    executed_variants = {(a["family_id"], a["variant_id"]) for a in own_audits}
    variants_complete = all(item in executed_variants for item in all_variants)
    numeric_needed = bool(numbers(claim["question"]))
    family_reasons = []
    if len(family_ids) < 2:
        family_reasons.append("fewer than two query families")
    if len(kinds) < 3:
        family_reasons.append("fewer than three family kinds")
    if "synonym" not in kinds:
        family_reasons.append("no synonym family")
    if not ({"entity", "restriction"} & kinds):
        family_reasons.append("no entity or restriction family")
    if numeric_needed and "numeric" not in kinds:
        family_reasons.append("numeric question lacks numeric family")
    if family_ids != executed_ids:
        family_reasons.append("planned and executed family sets differ")
    families_ok = not family_reasons
    used = set(claim_review.get("evidence_candidate_ids", []))
    unreviewed = [c["candidate_id"] for c in own_candidates if c.get("review_status") == "unreviewed"]
    unexplained_unreviewed = [c["candidate_id"] for c in own_candidates if c.get("review_status") == "unreviewed" and not c.get("exclusion_reason")]
    unexplained_exclusions = [c["candidate_id"] for c in own_candidates if c["candidate_id"] not in used and not c.get("exclusion_reason")]
    candidates_ok = not unexplained_unreviewed and not unexplained_exclusions
    valid = families_ok and scope_ok and variants_complete and candidates_ok
    exclusions = [{"candidate_id": c["candidate_id"], "status": c.get("review_status"), "reason": c.get("exclusion_reason")} for c in own_candidates if c["candidate_id"] not in used]
    return {
        "claim_id": cid, "status": "issued" if valid else "not_issued", "valid": valid,
        "meaning": "No retrieved candidate semantically answers the question after review; absence of support is not contradiction.",
        "query_families": [{"family_id": f["family_id"], "kind": f["kind"], "variants": [{"variant_id": v["variant_id"], "query": v["text"], "channels": v["channels"]} for v in f["variants"]]} for f in families],
        "query_family_sufficiency": families_ok, "query_family_limitations": family_reasons,
        "all_planned_variants_executed": variants_complete, "full_document_scope": scope_ok,
        "pages_expected": sorted(expected_pages), "pages_scanned_per_variant": {a["variant_id"]: a.get("pages_scanned", []) for a in own_audits},
        "document_sources": coverage.get("sources", []), "candidate_count": len(own_candidates),
        "unreviewed_candidates": unreviewed, "unexplained_unreviewed_candidates": unexplained_unreviewed,
        "unexplained_exclusions": unexplained_exclusions, "candidate_dispositions": exclusions,
        "conclusion": "no_evidence_after_documented_recall_and_review" if valid else "insufficient_recall_audit_certificate_not_issued",
    }


def coverage_summary(claims, candidates, audits):
    rows = []
    for claim in claims:
        cid = claim["claim_id"]
        own = [c for c in candidates if c["claim_id"] == cid]
        by_family = []
        for family in claim.get("query_families", []):
            fid = family["family_id"]
            own_candidates = [c for c in own if fid in c.get("origin_families", [])]
            by_family.append({
                "family_id": fid, "kind": family["kind"], "variant_count": len(family["variants"]),
                "candidate_count": len(own_candidates),
                "candidate_ids": [c["candidate_id"] for c in own_candidates],
            })
        rows.append({"claim_id": cid, "candidate_count": len(own), "families": by_family,
                     "query_variant_count": len([a for a in audits if a["claim_id"] == cid])})
    return rows


def finalize(args):
    work = Path(args.work)
    output = Path(args.output)
    case = read_json(args.case)
    contract = case["output_contract"]
    result = read_json(output) if output.exists() else blank_result(case, [], contract, {})
    result.pop("_contract_specs", None)
    plan = read_json(work / "retrieval-plan.json")
    sources = read_json(work / "sources.json")
    candidates = read_jsonl(work / "candidates.jsonl")
    audits = read_jsonl(work / "search-audit.jsonl")
    review = read_json(Path(args.review))
    claim_reviews = review_map(review, "claim_reviews")
    candidate_reviews = review_map(review, "candidate_reviews")
    candidate_by_id = {c["candidate_id"]: c for c in candidates}
    for cid, disposition in candidate_reviews.items():
        if cid not in candidate_by_id:
            raise PipelineError(f"Review references unknown candidate {cid}")
        status = disposition.get("status", "reviewed")
        if status not in {"reviewed", "unreviewed"}:
            raise PipelineError(f"Invalid candidate review status {status}")
        candidate_by_id[cid]["review_status"] = status
        candidate_by_id[cid]["relevant"] = disposition.get("relevant")
        candidate_by_id[cid]["exclusion_reason"] = disposition.get("exclusion_reason")
        candidate_by_id[cid]["review_note"] = disposition.get("note")
    write_jsonl(work / "candidates.jsonl", candidates)
    claim_results = []
    certificates = []
    for claim in plan["claims"]:
        cid = claim["claim_id"]
        cr = claim_reviews.get(cid)
        if not cr:
            cr = {"verdict": None, "rationale": "Agent review missing"}
        verdict = cr.get("verdict")
        if verdict not in VERDICTS:
            verdict = None
        evidence_ids = list(cr.get("evidence_candidate_ids", []))
        for evidence_id in evidence_ids:
            if evidence_id not in candidate_by_id or candidate_by_id[evidence_id]["claim_id"] != cid:
                raise PipelineError(f"Invalid evidence candidate {evidence_id} for {cid}")
        entry = {
            "claim_id": cid, "question": claim["question"], "verdict": verdict,
            "rationale": cr.get("rationale", ""), "evidence_candidate_ids": evidence_ids,
            "conflicts": cr.get("conflicts", []), "uncertainty": cr.get("uncertainty", ""),
        }
        if verdict == "insufficient_evidence":
            certificate = certificate_for(claim, cr, candidates, audits, plan["coverage"])
            entry["no_evidence_certificate"] = certificate
            certificates.append(certificate)
        claim_results.append(entry)
    result["claim_results"] = claim_results
    specs, _ = contract_fields(contract)
    for alias in ("verdicts", "claims", "assessments", "results"):
        if alias in specs:
            result[alias] = claim_results
        else:
            result.pop(alias, None)
    result["no_evidence_certificates"] = certificates
    if "evidence_certificates" in specs:
        result["evidence_certificates"] = certificates
    else:
        result.pop("evidence_certificates", None)
    result["sources"] = sources
    result["recall_coverage"] = {"claims": coverage_summary(plan["claims"], candidates, audits),
                                  "unreviewed_candidates": [c["candidate_id"] for c in candidates if c["review_status"] == "unreviewed"]}
    result["search_audit"] = {"variant_count": len(audits), "candidate_count": len(candidates),
                              "every_variant_full_scope": all(a.get("full_document_scope") for a in audits)}
    pending_note = "All candidates remain unreviewed; retrieval hits are not evidence verdicts"
    if isinstance(result.get("uncertainty"), list):
        result["uncertainty"] = [u for u in result["uncertainty"] if u != pending_note]
    elif isinstance(result.get("uncertainty"), dict) and isinstance(result["uncertainty"].get("items"), list):
        result["uncertainty"]["items"] = [u for u in result["uncertainty"]["items"] if u != pending_note]
    overrides = review.get("result_overrides", {})
    if isinstance(overrides, dict):
        result.update(overrides)
    result["status"] = "complete"
    change(result, "Agent_review_applied", f"Applied {len(claim_reviews)} claim review(s) and {len(candidate_reviews)} candidate review(s)")
    result = shape_all_fields(result, contract)
    errors = validate_data(result, case, work)
    if errors:
        result["status"] = "partial"
        for error in errors:
            add_uncertainty(result, error)
        change(result, "validation_failed", "; ".join(errors))
        result = shape_all_fields(result, contract)
        write_json(output, result)
        for error in errors:
            print(f"VALIDATION ERROR: {error}", file=sys.stderr)
        return 1
    change(result, "validated", "Contract, verdicts, candidate review, and no-evidence certificates validated")
    result = shape_all_fields(result, contract)
    write_json(output, result)
    return 0


def validate_data(result, case, work: Path | None = None):
    errors = []
    specs, notes = contract_fields(case.get("output_contract"))
    errors.extend(notes)
    if result.get("case_id") != case.get("case_id"):
        errors.append("case_id mismatch")
    for name, spec in specs.items():
        if name not in result:
            errors.append(f"missing output_contract field: {name}")
            continue
        kind = type_name(spec).lower()
        value = result[name]
        if kind in {"array", "list"} and not isinstance(value, list):
            errors.append(f"contract field {name} is not a list")
        elif kind in {"object", "dict", "dictionary", "map"} and not isinstance(value, dict):
            errors.append(f"contract field {name} is not a dict")
        elif kind in {"string", "str"} and not isinstance(value, str):
            errors.append(f"contract field {name} is not a string")
    for name in ("status", "sources", "uncertainty", "change_records"):
        if name not in result:
            errors.append(f"missing mandatory field: {name}")
    if result.get("status") not in {"partial", "complete", "error"}:
        errors.append("invalid status")
    rows = result.get("claim_results", result.get("verdicts", []))
    if isinstance(rows, dict) and isinstance(rows.get("items"), list):
        rows = rows["items"]
    if not isinstance(rows, list) or not rows:
        errors.append("no claim_results")
        rows = []
    for row in rows:
        if row.get("verdict") not in VERDICTS:
            errors.append(f"{row.get('claim_id')}: missing or invalid four-level verdict")
        conflicts = row.get("conflicts", [])
        if conflicts:
            for conflict in conflicts:
                ids = conflict.get("candidate_ids", []) if isinstance(conflict, dict) else []
                if len(set(ids)) < 2:
                    errors.append(f"{row.get('claim_id')}: conflict does not preserve at least two candidate sides")
        if row.get("verdict") == "insufficient_evidence":
            cert = row.get("no_evidence_certificate")
            if not isinstance(cert, dict) or not cert.get("valid"):
                reason = "; ".join(cert.get("query_family_limitations", [])) if isinstance(cert, dict) else "missing certificate"
                errors.append(f"{row.get('claim_id')}: invalid no-evidence certificate ({reason})")
    if work is not None and work.exists():
        try:
            candidates = read_jsonl(work / "candidates.jsonl")
            candidate_by_id = {c["candidate_id"]: c for c in candidates}
            for c in candidates:
                if c.get("review_status") not in {"reviewed", "unreviewed"}:
                    errors.append(f"{c.get('candidate_id')}: invalid review state")
                if c.get("review_status") == "unreviewed" and not c.get("exclusion_reason"):
                    errors.append(f"{c.get('candidate_id')}: unreviewed without explained exclusion")
                if result.get("status") == "complete" and c.get("review_status") == "unreviewed":
                    errors.append(f"{c.get('candidate_id')}: complete result cannot contain unreviewed candidates")
            for row in rows:
                for conflict in row.get("conflicts", []):
                    conflict_ids = conflict.get("candidate_ids", []) if isinstance(conflict, dict) else []
                    for cid in conflict_ids:
                        candidate = candidate_by_id.get(cid)
                        if candidate is None or candidate.get("claim_id") != row.get("claim_id"):
                            errors.append(f"{row.get('claim_id')}: conflict candidate {cid} is unknown or belongs to another claim")
                for cid in row.get("evidence_candidate_ids", []):
                    candidate = candidate_by_id.get(cid)
                    if candidate is None or candidate.get("claim_id") != row.get("claim_id"):
                        errors.append(f"{row.get('claim_id')}: evidence candidate {cid} is unknown or belongs to another claim")
                    elif candidate.get("review_status") != "reviewed" or not candidate.get("relevant"):
                        errors.append(f"{row.get('claim_id')}: evidence candidate {cid} was not reviewed as relevant")
        except PipelineError as exc:
            errors.append(str(exc))
    return errors


def validate_command(args):
    case = read_json(args.case)
    result = read_json(args.result)
    errors = validate_data(result, case, Path(args.work) if args.work else None)
    if errors:
        for error in errors:
            print(f"VALIDATION ERROR: {error}", file=sys.stderr)
        return 1
    print("VALID: dynamic contract, four-level verdicts, candidate states, and certificates")
    return 0


def coverage_svg(args):
    work = Path(args.work)
    plan = read_json(work / "retrieval-plan.json")
    candidates = read_jsonl(work / "candidates.jsonl")
    audits = read_jsonl(work / "search-audit.jsonl")
    rows = coverage_summary(plan["claims"], candidates, audits)
    bars = []
    for row in rows:
        for family in row["families"]:
            bars.append((row["claim_id"], family["family_id"], family["candidate_count"], family["kind"]))
    width = 1500
    bar_x = 700
    bar_scale = 600
    height = 150 + max(1, len(bars)) * 64
    max_count = max([count for _, _, count, _ in bars] + [1])
    colors = {"entity": "#64748b", "numeric": "#a16207", "synonym": "#0f766e", "figure_table": "#7c3aed", "restriction": "#be123c", "other": "#64748b"}
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="32" y="38" font-family="monospace" font-size="22" fill="#0f172a">{args.label} — recall coverage by query family</text>',
        '<text x="32" y="66" font-family="monospace" font-size="14" fill="#475569">Bars count fused retrieval candidates, not supported claims. Every variant scanned every extracted page.</text>',
    ]
    y = 100
    for cid, fid, count, kind in bars:
        label = f"{cid} / {fid} [{kind}]"
        # IDs in the supplied example are ASCII; escape generic XML text minimally.
        label = label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        bar_width = int(bar_scale * count / max_count)
        out.append(f'<text x="32" y="{y + 18}" font-family="monospace" font-size="14" fill="#1e293b">{label}</text>')
        out.append(f'<rect x="{bar_x}" y="{y}" width="{bar_width}" height="24" fill="{colors.get(kind, "#64748b")}"/>')
        out.append(f'<text x="{bar_x + 15 + bar_width}" y="{y + 18}" font-family="monospace" font-size="14" fill="#0f172a">{count}</text>')
        y += 64
    out.append(f'<text x="32" y="{height - 24}" font-family="monospace" font-size="12" fill="#64748b">Generated from retrieval-plan.json, search-audit.jsonl, and candidates.jsonl; {args.label}.</text>')
    out.append('</svg>')
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("\n".join(out) + "\n", encoding="utf-8")
    return 0


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Write partial result, pages, plan, candidates, and full search audit")
    prep.add_argument("--input", default="/input")
    prep.add_argument("--work", default="/app/work")
    prep.add_argument("--output", default="/app/output/result.json")
    prep.add_argument("--claims", help="Optional claims JSON override, used by the synthetic failure example")
    prep.add_argument("--resources", help="Optional environment/resources.yaml")
    prep.add_argument("--label", default="EVIDENCE-RECALL-SENTINEL")
    prep.set_defaults(func=prepare)
    fin = sub.add_parser("finalize", help="Apply independent Agent semantic review and validate result")
    fin.add_argument("--case", required=True)
    fin.add_argument("--work", default="/app/work")
    fin.add_argument("--output", default="/app/output/result.json")
    fin.add_argument("--review", required=True)
    fin.set_defaults(func=finalize)
    val = sub.add_parser("validate", help="Validate an existing result, optionally with retrieval work files")
    val.add_argument("--case", required=True)
    val.add_argument("--result", required=True)
    val.add_argument("--work")
    val.set_defaults(func=validate_command)
    svg = sub.add_parser("coverage-svg", help="Generate text SVG chart from actual retrieval artifacts")
    svg.add_argument("--work", required=True)
    svg.add_argument("--output", required=True)
    svg.add_argument("--label", default="SYNTHETIC")
    svg.set_defaults(func=coverage_svg)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except PipelineError as exc:
        # Do not leave a stale complete-looking result after a finalization error.
        if getattr(args, "command", None) == "finalize":
            try:
                output = Path(args.output)
                if output.exists():
                    result = read_json(output)
                    result["status"] = "partial"
                    add_uncertainty(result, f"Finalization failed: {exc}")
                    change(result, "finalization_error", str(exc))
                    write_json(output, result)
            except (PipelineError, OSError):
                pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
