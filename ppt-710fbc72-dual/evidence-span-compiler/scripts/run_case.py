#!/usr/bin/env python3
"""Prepare or finish an evidence-bound academic presentation case."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Direct script execution imports only sibling modules; no installation is required.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import atomic_json, load_json, make_result, normalize_text
from prepare_case import prepare


def existing(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if path.exists()]


def result_sources(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    sources = list(ledger.get("sources", []))
    known = {item.get("path") for item in sources}
    for item in ledger.get("input_files", []):
        if item.get("kind") == "pptx_template" and item.get("path") not in known:
            sources.append({"source_id": f"deck-{len(sources) + 1:03d}", "path": item["path"],
                            "sha256": item.get("sha256"), "kind": "pptx_base"})
    return sources


def command_prepare(args: argparse.Namespace) -> int:
    input_dir, work, output = Path(args.input), Path(args.work), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    case: Any = {}
    try:
        case_path = input_dir / "case.json"
        if case_path.is_file():
            case = load_json(case_path)
        summary = prepare(input_dir, work)
        case = summary["case"]
        artifacts = existing([
            work / "source_ledger.json", work / "asset_candidates.json", work / "input_inventory.json",
            work / "template_inventory.json", work / "deck_plan.skeleton.json", work / "case_snapshot.json",
        ])
        change_log = ["Discovered actual inputs recursively and classified PDF/PPTX by content.",
                      f"Extracted {summary['span_count']} text spans and {summary['asset_count']} caption assets with source hashes.",
                      "Wrote page previews and a blank plan skeleton; no narrative was invented.",
                      "Status remains partial until an agent authors deck_plan.json and finish succeeds."]
        result = make_result(case, "partial", result_sources(load_json(work / "source_ledger.json")),
                             summary["uncertainties"], change_log, artifacts, work, output)
        atomic_json(output / "result.json", result)
        print(f"PREPARED partial: {summary['span_count']} spans; plan skeleton: {work / 'deck_plan.skeleton.json'}")
        return 0
    except Exception as exc:
        exception = {"code": "prepare_failed", "message": str(exc)}
        result = make_result(case, "failed", [], [str(exc)], ["Prepare failed before compilation."],
                             existing([work / "input_inventory.json", work / "source_ledger.json"]),
                             work, output, [exception])
        atomic_json(output / "result.json", result)
        print(f"PREPARE FAILED: {exc}", file=sys.stderr)
        return 2


def command_finish(args: argparse.Namespace) -> int:
    work, output = Path(args.work), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    case: Any = {}
    try:
        case = load_json(Path(args.input) / "case.json") if args.input else load_json(work / "case_snapshot.json")
        ledger = load_json(work / "source_ledger.json")
        assets = load_json(work / "asset_candidates.json")
        plan_path = work / "deck_plan.json"
        if not plan_path.is_file():
            raise ValueError(f"Missing {plan_path}; copy the skeleton and author an evidence-linked narrative first.")
        plan = load_json(plan_path)
        from validate_plan import validate_plan
        report, evidence_map = validate_plan(plan, ledger, assets, case, work / "source_ledger.json")
        atomic_json(output / "evidence_report.json", report)
        atomic_json(output / "evidence_map.json", evidence_map)
        base_artifacts = [output / "evidence_report.json", output / "evidence_map.json"]
        if not report["valid"]:
            messages = [f"{item['code']}: {item['message']}" for item in report["errors"]]
            result = make_result(case, "failed", result_sources(ledger), messages,
                                 ["Compilation rejected the plan; factual content was retained in deck_plan.json."],
                                 existing(base_artifacts), work, output, report["errors"])
            atomic_json(output / "result.json", result)
            print(f"VALIDATION FAILED with {report['error_count']} errors; see {output / 'evidence_report.json'}", file=sys.stderr)
            return 2
        from build_deck import build
        try:
            pptx, build_report = build(plan, ledger, assets, work, output)
        except Exception as exc:
            exception = {"code": "build_failed", "message": str(exc)}
            result = make_result(case, "failed", result_sources(ledger), [str(exc)],
                                 ["Evidence validation passed; PPTX build failed without removing plan content."],
                                 existing(base_artifacts + [output / "build_report.json"]), work, output, [exception])
            atomic_json(output / "result.json", result)
            print(f"BUILD FAILED: {exc}", file=sys.stderr)
            return 3
        from common import export_pdf, pdf_to_pngs
        pdf, export_report = export_pdf(pptx, output)
        preview_paths: list[str] = []
        preview_errors: list[str] = []
        page_details = []
        if pdf:
            preview_paths, preview_errors = pdf_to_pngs(pdf, output)
            import fitz
            from PIL import Image
            with fitz.open(pdf) as rendered:
                for index, page in enumerate(rendered):
                    item = {"page": index + 1, "text": page.get_text("text"), "png": None, "png_size": None}
                    if index < len(preview_paths):
                        item["png"] = preview_paths[index]
                        with Image.open(preview_paths[index]) as image:
                            item["png_size"] = list(image.size)
                    page_details.append(item)
        missing_text = []
        if pdf:
            def compact(value: Any) -> str:
                return normalize_text(str(value)).replace(" ", "")
            asset_by_id = {item["asset_id"]: item for item in assets.get("assets", [])}
            for index, spec in enumerate(plan["slides"]):
                if index >= len(page_details) or spec.get("preserve"):
                    continue
                expected = [spec.get("title", ""), spec.get("takeaway", "")]
                expected.extend(item.get("text", "") if isinstance(item, dict) else str(item)
                                for item in spec.get("bullets", []))
                expected.extend(asset_by_id[item["asset_id"]]["caption"]
                                for item in spec.get("figures", []) if item.get("asset_id") in asset_by_id)
                actual = compact(page_details[index]["text"])
                for text in expected:
                    if compact(text) and compact(text) not in actual:
                        missing_text.append({"slide": index + 1, "slide_id": spec.get("id"), "expected_text": text})
        render_report = {"pptx": str(pptx), "export": export_report, "pdf": str(pdf) if pdf else None,
                         "png_previews": preview_paths, "preview_errors": preview_errors,
                         "expected_slides": len(plan["slides"]), "rendered_pages": len(page_details),
                         "pages": page_details, "missing_or_clipped_text": missing_text,
                         "visual_inspection_required": True,
                         "inspection_loop": "Inspect every PNG for clipping, overlap, crop context and legibility; adjust plan/bbox and rerun finish."}
        atomic_json(output / "render_report.json", render_report)
        artifacts = base_artifacts + [output / "build_report.json", output / "render_report.json", pptx]
        if pdf:
            artifacts.append(pdf)
        artifacts.extend(Path(path) for path in preview_paths)
        uncertainties = [item["message"] for item in report.get("warnings", [])]
        if not pdf:
            uncertainties.append(export_report.get("message") or "Renderer/export failed; editable PPTX is available but PDF/PNG verification is incomplete.")
        uncertainties.extend(preview_errors)
        uncertainties.extend(f"Rendered slide {item['slide']} is missing expected text; inspect for clipping or font substitution: {item['expected_text']}"
                             for item in missing_text)
        if pdf and len(page_details) != len(plan["slides"]):
            uncertainties.append(f"Rendered page count {len(page_details)} differs from planned {len(plan['slides'])} slides.")
        if pdf and len(preview_paths) != len(page_details):
            uncertainties.append("Not every rendered PDF page has a PNG preview.")
        success = bool(pdf and not preview_errors and not missing_text
                       and len(page_details) == len(plan["slides"])
                       and len(preview_paths) == len(page_details))
        status = "success" if success else "partial"
        change_log = ["Evidence quotes, source hashes, numeric tokens and plan budgets validated.",
                      f"Built editable PPTX in {build_report.get('mode', 'generate')} mode; removed {build_report['removed_template_slide_count']} slides authorized by that mode.",
                      "Added source crops, aspect-fit placement, original captions, and evidence-bearing speaker notes."]
        if pdf:
            change_log.append(f"Exported PDF and rendered {len(preview_paths)} real PNG previews with {export_report['renderer']}.")
        else:
            change_log.append("PDF export unavailable/failed; retained PPTX and marked result partial.")
        result = make_result(case, status, result_sources(ledger), uncertainties, change_log,
                             existing(artifacts), work, output, [], pptx, pdf)
        atomic_json(output / "result.json", result)
        print(f"FINISHED {status}: {pptx}" + (f"; {pdf}" if pdf else "; no verified PDF"))
        # A valid editable deck with no renderer is a usable partial result, not a CLI crash.
        return 0
    except Exception as exc:
        exception = {"code": "finish_failed", "message": str(exc)}
        result = make_result(case, "failed", [], [str(exc)], ["Finish could not compile the case."],
                             existing([output / "evidence_report.json", output / "evidence_map.json"]),
                             work, output, [exception])
        atomic_json(output / "result.json", result)
        print(f"FINISH FAILED: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare", help="Discover inputs and write source/page/template ledgers")
    prepare_parser.add_argument("--input", required=True)
    prepare_parser.add_argument("--work", required=True)
    prepare_parser.add_argument("--output", required=True)
    prepare_parser.set_defaults(function=command_prepare)
    finish_parser = subparsers.add_parser("finish", help="Validate, build, export, and render the authored plan")
    finish_parser.add_argument("--input", help="Original input directory; defaults to the prepared case snapshot")
    finish_parser.add_argument("--work", required=True)
    finish_parser.add_argument("--output", required=True)
    finish_parser.set_defaults(function=command_finish)
    args = parser.parse_args(argv)
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
