#!/usr/bin/env bash
# pdf-ingest-provenance 合成示例驱动脚本（非正式测试案例）。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/output/work"
rm -rf "$HERE/output"; mkdir -p "$WORK"

echo "=== 0) 生成合成夹具 PDF（纯 ASCII 最小 PDF，虚构内容）==="
python3 "$HERE/make_fixtures.py"

echo "=== 1) ingest_register：真实解析 PDF 并登记 ==="
python3 "$HERE/../scripts/ingest_register.py" --input "$HERE/input" --work "$WORK"

echo "=== 2) extraction_qc qc：文本层质检（beta 的空白页应被记录）==="
python3 "$HERE/../scripts/extraction_qc.py" qc \
    --registry "$WORK/source_registry.json" --out "$WORK/qc"
echo "qc exit=$?"

echo "=== 3) locate：真实引文（预期命中 alpha 第1页）==="
python3 "$HERE/../scripts/extraction_qc.py" locate \
    --registry "$WORK/source_registry.json" \
    --quote "baseline B achieves metric X = 0.71" > "$WORK/locate_hit.json"
echo "locate exit=$?"

echo "=== 4) locate：编造的引文（预期 exit 1，未命中）==="
python3 "$HERE/../scripts/extraction_qc.py" locate \
    --registry "$WORK/source_registry.json" \
    --quote "method M achieves 99 percent accuracy on dataset D" \
    > "$WORK/locate_miss.json" 2> "$WORK/locate_miss.stderr.txt"
echo "locate exit=$?"

echo "=== 产物 ==="
find "$HERE/output" -type f | sort
