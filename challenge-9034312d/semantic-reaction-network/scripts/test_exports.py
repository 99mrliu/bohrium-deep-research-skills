#!/usr/bin/env python3
"""Regression checks for honest optional PNG/PDF export and output contracts."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import srn  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", type=Path, default=HERE.parent / "examples" / "synthetic")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    graph_path = (args.example_dir / "input" / "semantic_graph.json").resolve()
    original = srn.load_json(graph_path)
    temp_parent = args.report.resolve().parent if args.report else HERE
    temp_parent.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix="srn-export-", dir=str(temp_parent)) as tmp:
        root = Path(tmp)
        structural_pdf = root / "structural.pdf"
        structural_pdf.write_bytes(b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n%%EOF\n")
        structural = srn.inspect_pdf(structural_pdf)
        checks.append({
            "name": "pdf_signature_page_and_eof_required",
            "passed": structural["valid"] and structural["page_count"] == 1,
            "observed": structural,
        })
        malformed = root / "malformed.pdf"
        malformed.write_bytes(b"%PDF-1.4\nnot a page and no EOF\n")
        rejected = srn.inspect_pdf(malformed)
        checks.append({
            "name": "pdf_header_alone_rejected",
            "passed": not rejected["valid"] and not rejected["eof"] and rejected["page_count"] == 0,
            "observed": rejected,
        })

        svg_path = root / "minimal.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20"/></svg>\n',
            encoding="utf-8",
        )
        unavailable_pdf = root / "unavailable.pdf"
        unavailable = srn.export_pdf(svg_path, unavailable_pdf, tools={})
        checks.append({
            "name": "missing_pdf_tools_never_fabricate_output",
            "passed": unavailable["status"] == "unavailable" and not unavailable_pdf.exists(),
            "observed": {"status": unavailable["status"], "file_created": unavailable_pdf.exists()},
        })
        unavailable_png = root / "unavailable.png"
        png_unavailable = srn.export_png(svg_path, unavailable_png, tools={})
        checks.append({
            "name": "missing_png_tools_never_fabricate_output",
            "passed": png_unavailable["status"] == "unavailable" and not unavailable_png.exists(),
            "observed": {"status": png_unavailable["status"], "file_created": unavailable_png.exists()},
        })

        graph = copy.deepcopy(original)
        # Absolute input paths let the temporary graph retain its real source bindings.
        for source in graph["sources"]:
            source["path"] = str((graph_path.parent / source["path"]).resolve())
        for node in graph["nodes"]:
            if node.get("kind") == "chart":
                node["chart"]["csv_path"] = str((graph_path.parent / node["chart"]["csv_path"]).resolve())
        contract = graph["output_contract"]
        contract.pop("preview_png", None)
        contract["export_pdf"] = "conventional.pdf"
        contract["delivery_attachment"] = "nested/delivery.PDF"
        contract["auxiliary_note"] = "notes.txt"
        contract["export_report"] = "export_report.json"
        mutated_path = root / "contract.json"
        srn.dump_json(mutated_path, graph)
        output = root / "output"
        output.mkdir()
        (output / "notes.txt").write_text("existing auxiliary text\n", encoding="utf-8")
        # Even a structurally plausible stale PDF must not be claimed without a fresh export.
        (output / "conventional.pdf").write_bytes(structural_pdf.read_bytes())
        real_detection = srn.detect_export_tools
        try:
            srn.detect_export_tools = lambda: {}
            returncode = srn.build(mutated_path, output, None)
        finally:
            srn.detect_export_tools = real_detection
        result = srn.load_json(output / "result.json")
        export_report = srn.load_json(output / "export_report.json")
        arbitrary_keys_present = all(key in result for key in contract)
        null_pdfs = result["export_pdf"] is None and result["delivery_attachment"] is None
        checks.append({
            "name": "arbitrary_contract_keys_and_unavailable_pdfs_are_honest",
            "passed": bool(
                returncode == 0 and result["status"] == "partial" and arbitrary_keys_present and
                null_pdfs and result["auxiliary_note"] == "notes.txt" and
                result["export_report"] == "export_report.json" and
                export_report["status"] == "partial" and len(export_report["pdfs"]) == 2 and
                all(item["status"] == "unavailable" for item in export_report["pdfs"])
            ),
            "observed": {
                "returncode": returncode,
                "status": result["status"],
                "all_contract_keys_top_level": arbitrary_keys_present,
                "conventional_pdf": result["export_pdf"],
                "generic_pdf": result["delivery_attachment"],
                "auxiliary_file": result["auxiliary_note"],
                "pdf_export_statuses": [item["status"] for item in export_report["pdfs"]],
            },
        })
        automatic_graph = copy.deepcopy(original)
        for source in automatic_graph["sources"]:
            source["path"] = str((graph_path.parent / source["path"]).resolve())
        for node in automatic_graph["nodes"]:
            if node.get("kind") == "chart":
                node["chart"]["csv_path"] = str((graph_path.parent / node["chart"]["csv_path"]).resolve())
        automatic_graph["output_contract"].pop("preview_png", None)
        automatic_path = root / "automatic-contract.json"
        srn.dump_json(automatic_path, automatic_graph)
        automatic_output = root / "automatic-output"
        automatic_returncode = srn.build(automatic_path, automatic_output, None)
        automatic_result = srn.load_json(automatic_output / "result.json")
        automatic_pdf = automatic_output / "synthetic-preview.pdf"
        installed_pdf_tool = any(real_detection().get(name) for name in ("rsvg-convert", "inkscape", "magick", "browsers"))
        automatic_checks = srn.inspect_pdf(automatic_pdf)
        expected_automatic_status = "success" if installed_pdf_tool else "partial"
        checks.append({
            "name": "contract_pdf_exports_without_preview_pdf_flag",
            "passed": bool(
                automatic_returncode == 0 and automatic_result["status"] == expected_automatic_status and
                ((installed_pdf_tool and automatic_result["export_pdf"] == "synthetic-preview.pdf" and
                  automatic_checks["valid"] and automatic_checks["page_count"] >= 1) or
                 (not installed_pdf_tool and automatic_result["export_pdf"] is None))
            ),
            "observed": {
                "returncode": automatic_returncode,
                "status": automatic_result["status"],
                "installed_pdf_tool_detected": installed_pdf_tool,
                "export_pdf": automatic_result["export_pdf"],
                "validation": automatic_checks,
            },
        })

    report = {
        "test": "SYNTHETIC export regression checks",
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
