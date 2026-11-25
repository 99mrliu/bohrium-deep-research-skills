#!/usr/bin/env python3
"""Generate common-field matrix, conflict atlas and integrated response."""
import argparse
from pathlib import Path

from compare_lib import load_json, render_atlas, render_common_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workorder", type=Path, required=True)
    parser.add_argument("--clusters", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    workorder = load_json(args.workorder)
    clusters = load_json(args.clusters)
    if args.source_registry:
        registry = load_json(args.source_registry)
    else:
        registry = {"documents": [{"source_document_id": doc["source_document_id"]} for doc in workorder["documents"]]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "comparison-matrix.md").write_text(render_common_matrix(workorder, registry), encoding="utf-8")
    (args.output_dir / "conflict-atlas.md").write_text(render_atlas(workorder, clusters, registry), encoding="utf-8")
    (args.output_dir / "integrated-response.md").write_text("# Integrated response\n\n" + workorder["integrated_response"] + "\n", encoding="utf-8")
    print("Wrote comparison-matrix.md, conflict-atlas.md and integrated-response.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
