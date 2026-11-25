#!/usr/bin/env python3
"""Run the independent stdlib pipeline using /input, work and output paths."""
import argparse
import sys
from pathlib import Path

from compare_lib import (
    assemble_result, dump_json, failed_result, load_json, make_clusters,
    render_atlas, render_common_matrix, validate_workorder,
)
from source_io import prepare_documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("/input"))
    parser.add_argument("--work-dir", type=Path, default=Path("/app/work"))
    parser.add_argument("--output-dir", type=Path, default=Path("/app/output"))
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    case = {}
    workorder = {}
    try:
        case_path = args.input_dir / "case.json"
        workorder_path = args.input_dir / "comparison-workorder.json"
        task_path = args.input_dir / "task.md"
        if not task_path.is_file():
            raise ValueError("missing /input equivalent task.md")
        task_text = task_path.read_text(encoding="utf-8")
        if not task_text.strip():
            raise ValueError("task.md is empty")
        case = load_json(case_path)
        workorder = load_json(workorder_path)
        if not isinstance(case.get("case_id"), str) or not case["case_id"]:
            raise ValueError("case.json requires exact nonempty case_id")
        registry, _ = prepare_documents(workorder, args.input_dir, args.work_dir)
        dump_json(args.work_dir / "source-registry.json", registry)
        validation = validate_workorder(workorder, case, registry)
        dump_json(args.work_dir / "validation.json", validation)
        if not validation["valid"]:
            raise ValueError("validation failed: " + " | ".join(validation["errors"]))
        clusters = make_clusters(workorder)
        dump_json(args.work_dir / "clusters.json", clusters)
        matrix = render_common_matrix(workorder, registry)
        atlas = render_atlas(workorder, clusters, registry)
        (args.output_dir / "comparison-matrix.md").write_text(matrix, encoding="utf-8")
        (args.output_dir / "conflict-atlas.md").write_text(atlas, encoding="utf-8")
        (args.output_dir / "integrated-response.md").write_text(
            "# Integrated response\n\n" + workorder["integrated_response"] + "\n", encoding="utf-8"
        )
        result = assemble_result(case, workorder, args.output_dir, validation, clusters)
        dump_json(args.output_dir / "result.json", result)
        for artifact in result["artifacts"]:
            if artifact["name"] == "result.json":
                artifact.update({"exists": True, "path": str(args.output_dir / "result.json")})
                artifact.pop("sha256", None)
                artifact["hash_note"] = "self-referential hash intentionally omitted"
                artifact.pop("bytes", None)
        dump_json(args.output_dir / "result.json", result)
        print(f"Completed {result['case_id']}: status={result['status']}")
        return 0 if result["status"] in {"success", "partial"} else 1
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        error = str(exc)
        result = failed_result(case, workorder, args.output_dir, error)
        dump_json(args.output_dir / "result.json", result)
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
