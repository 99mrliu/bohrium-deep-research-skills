#!/usr/bin/env bash
# 一键演示：run → verify → 打印 result.json 与 engine_report.md 尾部。
# 从任意工作目录均可运行（全部路径基于脚本所在目录解析）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENGINE="${ROOT_DIR}/scripts/case_engine.py"
INPUT_DIR="${SCRIPT_DIR}/synthetic_case"
DEMO_DIR="${SCRIPT_DIR}/output_demo"
WORK_DIR="${DEMO_DIR}/work"
OUTPUT_DIR="${DEMO_DIR}/output"

echo "[run_example] engine: ${ENGINE}"
rm -rf "${DEMO_DIR}"
mkdir -p "${WORK_DIR}" "${OUTPUT_DIR}"

echo "== step 1: engine run =="
python3 "${ENGINE}" run --input "${INPUT_DIR}" --work "${WORK_DIR}" --output "${OUTPUT_DIR}"

echo "== step 2: engine verify =="
python3 "${ENGINE}" verify --input "${INPUT_DIR}" --work "${WORK_DIR}" --output "${OUTPUT_DIR}"

echo "== result.json =="
cat "${OUTPUT_DIR}/result.json"

echo "== engine_report.md (tail 40 lines) =="
tail -n 40 "${WORK_DIR}/engine_report.md"

echo "[run_example] done, exit 0"
