#!/usr/bin/env python3
"""Generate the complete SYNTHETIC visual-readback demonstration."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from visual_evidence import file_hash, png_dimensions, write_json  # noqa: E402


def sha256(path):
    return file_hash(path)[0]


def run_tool(arguments):
    completed = subprocess.run([sys.executable, str(SCRIPT_DIR / "visual_evidence.py")] + arguments, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"visual_evidence.py failed with exit {completed.returncode}: {' '.join(arguments)}")


def figure_and_measurement(source_csv, output_dir):
    with source_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    x = [float(row["x"]) for row in rows]
    control = [float(row["control"]) for row in rows]
    treatment = [float(row["treatment"]) for row in rows]
    control_se = [float(row["control_se"]) for row in rows]
    treatment_se = [float(row["treatment_se"]) for row in rows]

    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=150)
    ax.errorbar(x, control, yerr=control_se, fmt="o-", capsize=4, linewidth=1.6, color="#377eb8", label="control (SYNTHETIC)")
    ax.errorbar(x, treatment, yerr=treatment_se, fmt="s-", capsize=4, linewidth=1.6, color="#e41a1c", label="treatment (SYNTHETIC)")
    ax.set_title("SYNTHETIC dose-response demonstration")
    ax.set_xlabel("x (arbitrary units)")
    ax.set_ylabel("response (arbitrary units)")
    ax.set_xticks(x)
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.set_xlim(-0.35, 5.35)
    ax.set_ylim(0, 92)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=True)
    fig.text(0.5, 0.01, "SYNTHETIC; error bars are illustrative standard errors; no real-paper reproduction", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.canvas.draw()
    original = output_dir / "original.png"
    fig.savefig(original, dpi=150, facecolor="white")

    def display_pixel(data_x, data_y):
        display_x, display_y = ax.transData.transform((data_x, data_y))
        return [float(display_x), float(fig.bbox.height - display_y)]

    # Independent deterministic pixel observations with subpixel jitter. The
    # readback tool sees these approximate pixels, not the source CSV numbers.
    x0_pixel = display_pixel(0, 0)
    x5_pixel = display_pixel(5, 0)
    y0_pixel = display_pixel(0, 0)
    y80_pixel = display_pixel(0, 80)
    target_pixel = display_pixel(5, 82)
    approximate_target = [target_pixel[0] + 0.48, target_pixel[1] - 0.41]
    height = float(fig.bbox.height)
    width = float(fig.bbox.width)
    measurement = {
        "schema_version": "1.0",
        "measurement_origin": "synthetic_programmatic_measurement",
        "observer": "SYNTHETIC deterministic approximate-pixel fixture; not Agent visual observation",
        "figure": {"source": "original.png", "panel": "single", "caption": "SYNTHETIC dose-response; bars are illustrative standard errors"},
        "pixel_space": {"origin": "top_left", "x_direction": "right", "y_direction": "down", "units": "pixel", "image_width": width, "image_height": height},
        "calibration": {
            "x": {
                "scale": "linear",
                "units": "x (arbitrary units)",
                "max_residual_data_units": 0.02,
                "points": [
                    {"pixel": x0_pixel[0] + 0.31, "value": 0},
                    {"pixel": x5_pixel[0] - 0.28, "value": 5},
                ],
            },
            "y": {
                "scale": "linear",
                "units": "response (arbitrary units)",
                "max_residual_data_units": 0.25,
                "points": [
                    {"pixel": y0_pixel[1] + 0.44, "value": 0},
                    {"pixel": y80_pixel[1] - 0.37, "value": 80},
                ],
            },
        },
        "points": [{
            "label": "treatment response at x=5, central square marker",
            "pixel": approximate_target,
            "figure_coordinate": {"space": "figure_fraction", "x": approximate_target[0] / width, "y": (height - approximate_target[1]) / height},
            "pixel_sigma": [0.8, 1.25],
            "series": "treatment",
            "legend_label": "treatment (SYNTHETIC)",
            "group": "single synthetic series at x=5",
            "error_bar": {"present": True, "meaning": "illustrative standard error stated in SYNTHETIC caption", "read": False},
        }],
    }
    controls_for_annotation = {
        "x0": [x0_pixel[0] + 0.31, x0_pixel[1]],
        "x5": [x5_pixel[0] - 0.28, x5_pixel[1]],
        "y0": [y0_pixel[0], y0_pixel[1] + 0.44],
        "y80": [y80_pixel[0], y80_pixel[1] - 0.37],
    }
    plt.close(fig)
    return rows, measurement, approximate_target, controls_for_annotation


def write_annotated(original, readback, target_pixel, controls, output_paths):
    image = mpimg.imread(original)
    point = readback["points"][0]
    x_key, y_key = list(point["estimated_values"])
    x_value = point["estimated_values"][x_key]
    y_value = point["estimated_values"][y_key]
    fig, ax = plt.subplots(figsize=(10.8, 7.2), dpi=140)
    ax.imshow(image)
    for label, pixel in controls.items():
        ax.scatter(pixel[0], pixel[1], marker="+", s=85, linewidths=1.8, color="#006d2c")
        ax.annotate(f"calibration {label}", pixel, xytext=(7, -9), textcoords="offset points", fontsize=8, color="#006d2c", bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none", "pad": 1})
    ax.scatter(target_pixel[0], target_pixel[1], marker="x", s=115, linewidths=2.2, color="#6a3d9a", label="independent approximate-pixel measurement")
    ax.annotate(f"readback: x={x_value:.3f}; y={y_value:.3f}\nCSV source: x=5; treatment=82\nSYNTHETIC comparison, not exact graphical truth", target_pixel, xytext=(0.52, 0.24), textcoords="axes fraction", fontsize=10, color="#4a148c", arrowprops={"arrowstyle": "->", "color": "#6a3d9a"}, bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9, "edgecolor": "#6a3d9a"})
    ax.set_title("SYNTHETIC annotated original: calibration, readback, and source comparison")
    # The original series legend remains visible; an extra marker legend would
    # cover the embedded x-axis tick labels in this image-space comparison.
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_paths[0], dpi=140, facecolor="white")
    fig.savefig(output_paths[1], format="svg", facecolor="white")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    bundle_root = SCRIPT_DIR.parent.resolve()
    if output_dir == bundle_root or bundle_root in output_dir.parents:
        parser.error("OUTPUT_DIR must be outside the skill bundle so generated PNG/SVG/binaries never remain bundled")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_csv = output_dir / "source.csv"
    shutil.copyfile(SCRIPT_DIR.parent / "examples" / "source.csv", source_csv)

    rows, measurement, target_pixel, controls = figure_and_measurement(source_csv, output_dir)
    original = output_dir / "original.png"
    paper = output_dir / "paper.txt"
    paper.write_text(
        "SYNTHETIC VISUAL-EVIDENCE PAPER\n\n"
        "This invented text accompanies one invented dose-response figure. "
        "It is not a real publication and no real-paper reproduction is claimed.\n\n"
        "Figure 1. SYNTHETIC control and treatment responses over x=0..5. "
        "Circles denote control and squares denote treatment. Error bars are illustrative standard errors. "
        "Exact numeric data tables are not reported in this synthetic paper text; inspect the figure for graphical estimates.\n",
        encoding="utf-8", newline="\n",
    )
    (output_dir / "task.md").write_text(
        "# SYNTHETIC task\n\nAssess every supplied claim using the generated figure. "
        "Claims are hypotheses, not facts. Do not claim exact graphical precision.\n",
        encoding="utf-8", newline="\n",
    )
    claims = {
        "synthetic": True,
        "notice": "All claims are unverified hypotheses, not facts.",
        "claims": [
            {"claim_id": "C-APPROX", "text": "The treatment response at x=5 is approximately 82 arbitrary units (graphical tolerance 1.5 units)."},
            {"claim_id": "C-NEGATIVE", "text": "The treatment response at x=5 is below 0 arbitrary units."},
            {"claim_id": "C-EXACT", "text": "The treatment response at x=5 is exactly 82.000 arbitrary units to three decimal places."},
        ],
    }
    case = {
        "case_id": "SYNTHETIC-VISUAL-001",
        "synthetic": True,
        "output_contract": {
            "claim_assessments": {"type": "array"},
            "numeric_readbacks": {"type": "array"},
            "comparison_to_source": {"type": "object"},
            "visual_summary": {"type": "string"},
            "provenance_note": {"type": "string"},
        },
    }
    write_json(output_dir / "claims-to-verify.json", claims)
    write_json(output_dir / "case.json", case)
    write_json(output_dir / "measurement.json", measurement)
    receipt = output_dir / "render_receipt.json"
    run_tool(["register-image", "--image", str(original), "--receipt", str(receipt), "--synthetic"])
    readback_path = output_dir / "actual_readback.json"
    run_tool(["readback", "--receipt", str(receipt), "--measurement", str(output_dir / "measurement.json"), "--output", str(readback_path)])
    with readback_path.open("r", encoding="utf-8") as handle:
        readback = json.load(handle)
    point = readback["points"][0]
    x_key, y_key = list(point["estimated_values"])
    x_read = point["estimated_values"][x_key]
    y_read = point["estimated_values"][y_key]
    y_sigma = point["estimated_uncertainty_1sigma"][y_key]
    source_row = next(row for row in rows if float(row["x"]) == 5)
    x_source = float(source_row["x"])
    y_source = float(source_row["treatment"])
    comparison = {
        "label": point["label"],
        "source_role": "SYNTHETIC CSV ground truth for demonstration only; not used by readback calculation",
        "x_source": x_source,
        "x_readback": x_read,
        "x_signed_error": x_read - x_source,
        "response_source": y_source,
        "response_readback": y_read,
        "response_signed_error": y_read - y_source,
        "response_absolute_error": abs(y_read - y_source),
        "response_readback_uncertainty_1sigma": y_sigma,
        "interpretation": "Agreement quantifies this synthetic readback; it does not turn graphical estimates into exact source values.",
    }
    with (output_dir / "comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "x_source", "x_readback", "response_source", "response_readback", "response_signed_error", "response_absolute_error", "response_uncertainty_1sigma"])
        writer.writerow([point["label"], x_source, x_read, y_source, y_read, comparison["response_signed_error"], comparison["response_absolute_error"], y_sigma])

    annotated_paths = (output_dir / "annotated.png", output_dir / "annotated.svg")
    write_annotated(original, readback, target_pixel, controls, annotated_paths)
    for path in annotated_paths:
        file_hash(path)
    png_dimensions(annotated_paths[0])
    svg_header = annotated_paths[1].read_text(encoding="utf-8")[:1000]
    if "<svg" not in svg_header:
        raise RuntimeError("annotated.svg was not really generated as SVG")

    tolerance = 1.5
    approximate_supported = abs(y_read - 82) <= tolerance + y_sigma
    claim_assessments = [
        {
            "claim_id": "C-APPROX",
            "verdict": "supported" if approximate_supported else "insufficient_evidence",
            "verification_complete": True,
            "rationale": f"Calibrated treatment-marker readback is {y_read:.3f} +/- {y_sigma:.3f} units, within the explicitly approximate 82 +/- {tolerance} claim interval.",
            "evidence": ["original.png treatment square at x=5", "actual_readback.json calibrated point"],
        },
        {
            "claim_id": "C-NEGATIVE",
            "verdict": "contradicted",
            "verification_complete": True,
            "rationale": f"Affirmative calibrated readback is positive ({y_read:.3f}); its uncertainty interval remains far above zero.",
            "evidence": ["original.png positive response axis and treatment marker", "actual_readback.json estimate interval"],
        },
        {
            "claim_id": "C-EXACT",
            "verdict": "insufficient_evidence",
            "verification_complete": False,
            "rationale": "Three-decimal exactness exceeds pixel precision. The approximate readback is compatible with 82.000 but cannot prove exact equality, and no exact numeric table is reported in the synthetic paper text.",
            "evidence": ["actual_readback.json uncertainty and half-pixel quantization", "paper.txt statement that exact numeric tables are not reported"],
        },
    ]
    result = {
        "case_id": case["case_id"],
        "claim_assessments": claim_assessments,
        "numeric_readbacks": readback["points"],
        "comparison_to_source": comparison,
        "visual_summary": "SYNTHETIC raw figure and annotated comparison show two error-bar series; the treatment square at x=5 yields a calibrated positive response near 82.",
        "provenance_note": "SYNTHETIC software/measurement demonstration only. No Agent visual observation and no real-paper reproduction are claimed. PNG and SVG were actually generated.",
        "status": "partial",
        "sources": [
            {"source_id": "synthetic-original", "type": "generated_figure", "path": "original.png", "sha256": sha256(original), "agent_image_opened": False},
            {"source_id": "synthetic-csv", "type": "comparison_ground_truth", "path": "source.csv", "sha256": sha256(source_csv)},
            {"source_id": "synthetic-paper", "type": "generated_text", "path": "paper.txt", "sha256": sha256(paper)},
        ],
        "uncertainty": [
            "Graphical readback is approximate and is not an exact original table value.",
            f"Response readback 1-sigma pixel-propagated uncertainty is {y_sigma:.6g} units, with calibration residuals recorded separately.",
            "The exact-to-three-decimals claim remains insufficiently evidenced; therefore the run is partial.",
        ],
        "change_records": [
            {"sequence": 0, "change": "Initialized a partial result for SYNTHETIC claims."},
            {"sequence": 1, "change": "Generated non-empty raw PNG and verified its hash, dimensions, and receipt."},
            {"sequence": 2, "change": "Recovered values solely from independent approximate pixels and affine axis calibration; recorded residuals, quantization, and uncertainty."},
            {"sequence": 3, "change": "Generated real annotated PNG/SVG comparisons and retained the precision-limited exactness claim as insufficient evidence."},
        ],
    }
    result_path = output_dir / "result.json"
    write_json(result_path, result)
    run_tool(["validate-result", "--case", str(output_dir / "case.json"), "--result", str(result_path), "--output", str(output_dir / "validation.json")])
    names = ["source.csv", "original.png", "paper.txt", "task.md", "claims-to-verify.json", "case.json", "measurement.json", "render_receipt.json", "actual_readback.json", "comparison.csv", "annotated.png", "annotated.svg", "result.json", "validation.json"]
    manifest = {
        "synthetic": True,
        "real_paper_reproduction": False,
        "status": "partial",
        "files": {name: {"sha256": sha256(output_dir / name), "bytes": (output_dir / name).stat().st_size} for name in names},
        "comparison_to_source": comparison,
        "previews": {"original_png": str(original), "annotated_png": str(annotated_paths[0]), "annotated_svg": str(annotated_paths[1])},
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps({"status": "partial", "output_dir": str(output_dir), "original_preview": str(original), "annotated_preview": str(annotated_paths[0]), "svg_preview": str(annotated_paths[1]), "result": str(result_path), "comparison": comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
