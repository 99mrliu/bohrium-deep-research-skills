#!/bin/bash
# negative_tests.sh — 负向测试（真实执行，全部 PASS 才退出 0）：
#   T1 重跑幂等：同一输入跑两遍，输出字节级一致，且无重复节点/边 ID；
#   T2 旧 ID 保留：MERGE/KEEP_DISTINCT 后 baseline 的节点 ID 在 current 中原样保留；
#   T3 引文不匹配：篡改一个 quote 后校验器必须拒绝（退出非 0）并指出位置；
#   T4 冲突不覆盖：apply 前后 baseline 文件逐字节不变，current 中冲突双方并存。
set -u
HERE_DIR="$(cd "$(dirname "$0")" && pwd)"
SYNTH="$(cd "$HERE_DIR/.." && pwd)"
SCRIPTS="$SYNTH/../../scripts"
IN="$SYNTH/input"
CAND="$SYNTH/candidates"
PASS=0; FAIL=0

ok()  { echo "PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

run_pipeline() {  # $1=workdir
    local W="$1"
    mkdir -p "$W"
    python3 "$SCRIPTS/kg_apply.py" init --input-dir "$IN" \
        --candidates "$CAND/baseline-candidates.json" --work-dir "$W" >/dev/null || return 1
    python3 "$SCRIPTS/kg_apply.py" apply --input-dir "$IN" \
        --work-dir "$W" --changeset "$CAND/changeset.json" >/dev/null || return 1
    python3 "$SCRIPTS/kg_diff.py" --baseline "$W/graph-v1.json" \
        --current "$W/graph-v2.json" --out "$W/diff.json" >/dev/null || return 1
    python3 "$SCRIPTS/kg_query.py" --baseline "$W/graph-v1.json" \
        --current "$W/graph-v2.json" \
        --spec "$SYNTH/queries/query-specs.json" --out "$W/queries.json" >/dev/null || return 1
    python3 "$SCRIPTS/kg_assemble.py" --input-dir "$IN" --work-dir "$W" \
        --output-dir "$W/out" >/dev/null || return 1
}

echo "== T1 重跑幂等 / 无重复 ID =="
W1="$(mktemp -d /tmp/kg-t1a.XXXXXX)"; W2="$(mktemp -d /tmp/kg-t1b.XXXXXX)"
run_pipeline "$W1" && run_pipeline "$W2"
if diff -r "$W1/out" "$W2/out" >/dev/null 2>&1; then
    ok "两次完整运行输出逐字节一致（diff -r 无差异）"
else
    bad "两次运行输出不一致"
fi
python3 - "$W1/out/graph-current.json" <<'PY' && ok "current 图无重复节点/边 ID" || bad "current 图存在重复 ID"
import json, sys
g = json.load(open(sys.argv[1]))
ids = [n["id"] for n in g["nodes"]] + [e["id"] for e in g["edges"]]
sys.exit(0 if len(ids) == len(set(ids)) else 1)
PY

echo "== T2 旧 ID 保留（MERGE/KEEP_DISTINCT 不改号） =="
python3 - "$W1/graph-v1.json" "$W1/graph-v2.json" <<'PY' && ok "baseline 全部节点/边 ID 在 current 中原样保留" || bad "旧 ID 丢失或被改号"
import json, sys
g1 = json.load(open(sys.argv[1])); g2 = json.load(open(sys.argv[2]))
ids1 = {n["id"] for n in g1["nodes"]} | {e["id"] for e in g1["edges"]}
ids2 = {n["id"] for n in g2["nodes"]} | {e["id"] for e in g2["edges"]}
lfp1 = [n for n in g1["nodes"] if n["label"] == "LiFePO4/C composite"][0]["id"]
lfp2 = [n for n in g2["nodes"] if "LiFePO4/C composite" in [n["label"]] + [a["label"] for a in n.get("aliases", [])]][0]["id"]
sys.exit(0 if ids1 <= ids2 and lfp1 == lfp2 else 1)
PY

echo "== T3 引文不匹配必须被拒 =="
W3="$(mktemp -d /tmp/kg-t3.XXXXXX)"
python3 - "$CAND/baseline-candidates.json" "$W3/tampered.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c["nodes"][0]["evidence"][0]["quote"] = "a LiFePO4/C composite anode"  # cathode->anode 篡改
json.dump(c, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
PY
if python3 "$SCRIPTS/kg_verify.py" --input-dir "$IN" --candidates "$W3/tampered.json" >/dev/null 2>&1; then
    bad "篡改 quote 未被校验器发现"
else
    python3 "$SCRIPTS/kg_verify.py" --input-dir "$IN" --candidates "$W3/tampered.json" 2>&1 | grep -q "未命中" \
        && ok "篡改 quote 被拒且报错定位（'未命中'）" || bad "拒绝但报错信息不含定位"
fi

echo "== T4 冲突不覆盖 / 基线封存 =="
H_BEFORE="$(md5 -q "$W1/graph-v1.json" 2>/dev/null || md5sum "$W1/graph-v1.json" | cut -d' ' -f1)"
python3 "$SCRIPTS/kg_apply.py" apply --input-dir "$IN" --work-dir "$W1" \
    --changeset "$CAND/changeset.json" >/dev/null 2>&1  # 重复应用（幂等路径）
H_AFTER="$(md5 -q "$W1/graph-v1.json" 2>/dev/null || md5sum "$W1/graph-v1.json" | cut -d' ' -f1)"
[ "$H_BEFORE" = "$H_AFTER" ] && ok "apply 前后 graph-v1.json 逐字节不变（封存基线不被改写）" || bad "baseline 文件被改写"
python3 - "$W1/graph-v2.json" <<'PY' && ok "冲突双方并存且均标 conflicted，未被覆盖" || bad "冲突边缺失或被覆盖"
import json, sys
g = json.load(open(sys.argv[1]))
out = [e for e in g["edges"] if e["relation"] == "outperforms"]
conf = [e for e in out if e.get("conflict_group")]
groups = {e["conflict_group"] for e in conf}
vals = [e.get("attributes", {}).get("value", "") for e in g["edges"] if e["relation"] == "delivers_capacity"]
sys.exit(0 if len(out) == 2 and len(conf) == 2 and len(groups) == 1
           and "158 mAh/g" in vals and "149 mAh/g" in vals else 1)
PY

rm -rf "$W1" "$W2" "$W3"
echo "== 结果: PASS=$PASS FAIL=$FAIL =="
[ "$FAIL" -eq 0 ]
