#!/usr/bin/env python3
"""Build the labelled synthetic example using the real deterministic validators."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from scope_mesh import DIMENSIONS, SECTIONS, audit_claims_payload, validate_contract_payload, validate_scope_payload, write_json


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(path: Path) -> Any:
    import json
    return json.loads(read_text(path))


def display(value: Any) -> str:
    if isinstance(value, dict) and "status" in value:
        return f"**{value['status']}** — {value['reason']}"
    return str(value).replace("\n", " ")


def mesh_markdown(records_payload: Any, claims_payload: Any, claim_audit: Any) -> str:
    lines = [
        "# Synthetic scope mesh / 合成范围网格",
        "",
        "**SYNTHETIC / 合成示例. Fictional Aster-17 study; no real-world claim or evidence. Structural checks are not semantic validation.**",
        "",
        "## Bounded scope records",
        "",
    ]
    for record in records_payload["records"]:
        lines.extend([
            f"### {record['record_id']} — {record['claim_id']}",
            "",
            f"- Classification: `{record['classification']}`",
        ])
        for field in DIMENSIONS:
            lines.append(f"- `{field}`: {display(record[field])}")
        if "inference_reasoning" in record:
            lines.append(f"- `inference_reasoning`: {record['inference_reasoning']}")
        if "not_reported_basis" in record:
            lines.append(f"- `not_reported_basis`: {record['not_reported_basis']}")
        for evidence in record.get("evidence", []):
            lines.append(f"- Evidence: `{evidence['source']} [{evidence['anchor']}]` — “{evidence['quote']}”")
        lines.append("")
    audits = {item["claim_id"]: item for item in claim_audit["claims"]}
    lines.extend(["## Universal-claim closure", ""])
    for claim in claims_payload["claims"]:
        if not claim.get("universal"):
            continue
        audit = audits[claim["claim_id"]]
        lines.extend([
            f"### {claim['claim_id']}",
            "",
            f"- Triggered statement: {claim['statement']}",
            f"- Assessment: **{audit['assessment']}**",
            f"- Flags: `{', '.join(audit['flags'])}`",
            f"- Bounded restatement: {claim.get('bounded_restatement', 'NONE')}",
            "- Section coverage:",
        ])
        for section in SECTIONS:
            entry = claim.get("section_coverage", {}).get(section, {})
            ev = entry.get("evidence", {})
            lines.append(f"  - {section}: checked={entry.get('checked') is True}; anchor={ev.get('anchor', 'NONE')}; quote=“{ev.get('quote', '')}”")
        search = claim.get("exception_search", {})
        lines.append(f"- Exception-search terms: {', '.join(search.get('terms', []))}")
        lines.append(f"- Exception-search locations: {', '.join(search.get('locations', []))}")
        for counterexample in claim.get("counterexamples", []):
            lines.append(f"- Counterexample: `{counterexample['record_id']}`; disposition=`{counterexample['disposition']}`; reason={counterexample['reason']}")
        lines.append("")
    lines.extend([
        "## Adjudication caveat",
        "",
        "The thin-coupon contrary subgroup defeats the universal statement. The bounded pooled result remains separate from that subgroup. No service-life, other-alloy, field-condition, or state-of-the-art conclusion is demonstrated. Automated checks do not decide whether evidence semantically supports these records.",
        "",
    ])
    return "\n".join(lines)


def audit_markdown(scope_report: Any, claim_report: Any, contract_report: Any) -> str:
    flags = [f"{item['claim_id']}: {', '.join(item['flags']) or 'none'}" for item in claim_report["claims"]]
    return "\n".join([
        "# Synthetic audit report / 合成审计报告",
        "",
        "**SYNTHETIC / 合成示例. This audits a fictional study and authored records.**",
        "",
        "## Deterministic results",
        "",
        f"- Scope records valid: `{scope_report['valid']}`; records={scope_report['record_count']}; evidence items={scope_report['evidence_count']}; errors={scope_report['error_count']}.",
        f"- Claim-audit input valid: `{claim_report['valid']}`; claims={claim_report['claim_count']}; errors={claim_report['error_count']}.",
        f"- Result contract valid: `{contract_report['valid']}`; case_id=`{contract_report['case_id']}`; errors={contract_report['error_count']}.",
        "- Required contract fields, nesting, types, array counts, and `additionalProperties: false` were checked against the supplied synthetic case schema.",
        "- Every scope-record and universal-coverage evidence quotation was checked for exact containment in its named source anchor.",
        "",
        "## Universal-claim flags",
        "",
    ] + [f"- {flag}" for flag in flags] + [
        "",
        "`UNSUPPORTED_GENERALIZATION` is an expected scientific audit finding, not a malformed-input error. The contrary thin-coupon record prevents the universal from being accepted; the bounded restatement is used in `result.json`.",
        "",
        "## Errors and caveats",
        "",
        f"- Scope errors: {json.dumps(scope_report['errors'], ensure_ascii=False)}",
        f"- Claim-input errors: {json.dumps(claim_report['errors'], ensure_ascii=False)}",
        f"- Contract errors: {json.dumps(contract_report['errors'], ensure_ascii=False)}",
        "- No automatic semantic validation is claimed. Exact quotation matching does not show that a quotation supports an interpretation.",
        "- The exception search is closed over the supplied synthetic source only; it is not a literature search and cannot prove absence of other exceptions.",
        "- Numeric values are retained as fictional report content, not recomputed. No real paper, comparison set, or external dataset was used.",
        "- Source, uncertainty, and change records are retained inside the contract-permitted result; detailed mesh and this audit are sidecars.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    root = Path(args.example_dir)
    out = Path(args.output_dir)
    try:
        case = load(root / "case.json")
        task = read_text(root / "task.md")
        source = read_text(root / "source.txt")
        records = load(root / "scope_records.json")
        claims = load(root / "claims.json")
        authored = load(root / "authored_response.json")
        synthetic_labels = [
            case.get("synthetic") is True,
            records.get("synthetic") is True,
            claims.get("synthetic") is True,
            authored.get("synthetic") is True,
            "SYNTHETIC / 合成示例" in task,
            "SYNTHETIC / 合成示例" in source,
        ]
        if not all(synthetic_labels):
            raise ValueError("all synthetic example inputs must be explicitly labelled SYNTHETIC / 合成示例")
        scope_report = validate_scope_payload(records, source_root=str(root))
        claim_report = audit_claims_payload(claims, records, source_root=str(root))
        result = copy.deepcopy(authored["result"])
        contract_report = validate_contract_payload(result, case)
        mesh = {
            "synthetic": True,
            "label": "SYNTHETIC / 合成示例 — entirely fictional",
            "case_id": case["case_id"],
            "records": records["records"],
            "authored_claims": claims["claims"],
            "claim_audit": claim_report,
            "semantic_validation": False,
        }
        out.mkdir(parents=True, exist_ok=True)
        write_json(str(out / "result.json"), result)
        write_json(str(out / "scope_mesh.json"), mesh)
        (out / "scope_mesh.md").write_text(mesh_markdown(records, claims, claim_report), encoding="utf-8")
        (out / "audit_report.md").write_text(audit_markdown(scope_report, claim_report, contract_report), encoding="utf-8")
        print(json.dumps({
            "synthetic": True,
            "output_dir": str(out),
            "scope_valid": scope_report["valid"],
            "claim_input_valid": claim_report["valid"],
            "contract_valid": contract_report["valid"],
            "semantic_validation": False,
        }, ensure_ascii=False))
        return 0 if scope_report["valid"] and claim_report["valid"] and contract_report["valid"] else 1
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"synthetic example error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
