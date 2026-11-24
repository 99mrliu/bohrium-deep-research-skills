#!/usr/bin/env bash
# run_example.sh — contract-forge 端到端合成示例（非正式案例结果）
# 流程：contract_probe → result_scaffold → 模拟填充 → preview_render → delivery_gate
# 另含负例：构造缺字段的 result.json，验证门禁判 FAIL。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CASE="$HERE/case"
WORK="$HERE/expected/work"
OUT="$HERE/expected"

echo "== 清理并重建 expected/ =="
rm -rf "$OUT"
mkdir -p "$WORK"

echo "== ① contract_probe =="
python3 "$ROOT/scripts/contract_probe.py" --input-dir "$CASE" --work-dir "$WORK"

echo "== ② result_scaffold =="
python3 "$ROOT/scripts/result_scaffold.py" --contract "$WORK/contract.json" \
    --work-dir "$WORK" --output-dir "$OUT"

echo "== ③ 模拟模型写作与增量填充（合成示例） =="
cat > "$OUT/chapter.md" <<'EOF'
# 方法与实验（合成示例，非正式案例结果）

## 步骤

实验按以下流程执行：首先加载 SynthTiny-1k 数据集并按 8:1:1 分层抽样划分为
训练 800 条、验证 100 条、测试 100 条；随后构建 2 层 MLP（隐藏维 128，ReLU 激活），
使用 SGD 优化器训练 20 个 epoch；最后在验证集上选模并在测试集上评估。

## 实验设置

训练在单 CPU 环境完成，随机种子固定为 42，全流程耗时 95 秒。

## 参数与来源

| 参数 | 取值 | 来源 |
|------|------|------|
| 学习率 | 0.05 | notes.md（经验选取，未做超参搜索） |
| 动量 | 0.9 | notes.md |
| batch size | 32 | notes.md |
| epoch | 20 | notes.md |

## 数据集与划分

SynthTiny-1k 共 1000 条样本、10 个类别，训练/验证/测试为 800/100/100 条。

## 对照

- baseline-1：逻辑回归，验证准确率 0.71
- baseline-2：随机森林 100 棵树，验证准确率 0.74
- 本文 MLP：验证准确率 0.78，测试准确率 0.76

## 复现与限制

所有数值来自 notes.md，随机种子 42 可复现。限制：未做超参搜索，
学习率按经验选取；数据为程序合成，结论外推需谨慎。
EOF

python3 - "$WORK/result.skeleton.json" "$OUT/result.json" <<'PYEOF'
import json, sys
skel_path, out_path = sys.argv[1], sys.argv[2]
with open(skel_path, encoding="utf-8") as f:
    r = json.load(f)
r.pop("skeleton_meta", None)
src = [{"file": "notes.md", "locator": "全文", "note": "实验记录唯一来源"}]
r["artifact"] = {"status": "done", "value": "chapter.md", "sources": src,
                 "uncertainty": [], "assumptions": [], "notes": "合成示例正文"}
r["sources"] = {"status": "done", "value": ["notes.md"], "sources": src,
                "uncertainty": [], "assumptions": [], "notes": ""}
r["uncertainty"] = {"status": "done",
                    "value": ["未做超参搜索，学习率 0.05 为经验值", "合成数据，外推性有限"],
                    "sources": src, "uncertainty": [], "assumptions": [], "notes": ""}
r["status"] = {"status": "done", "value": "done", "sources": [],
               "uncertainty": [], "assumptions": [], "notes": "示例流程全部完成"}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(r, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("OK: 填充完成 -> %s" % out_path)
PYEOF

echo "== ④ preview_render =="
python3 "$ROOT/scripts/preview_render.py" --chapter "$OUT/chapter.md" \
    --output "$OUT/chapter.preview.svg"

echo "== ⑤ delivery_gate（正例，应 PASS） =="
python3 "$ROOT/scripts/delivery_gate.py" --input-dir "$CASE" --output-dir "$OUT" \
    --chapter "$OUT/chapter.md" --report "$OUT/gate_report"

echo "== ⑥ 负例：缺 sources 字段，应 FAIL =="
NEG="$(mktemp -d)"
trap 'rm -rf "$NEG"' EXIT
python3 - "$OUT/result.json" "$NEG/result.json" <<'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    r = json.load(f)
del r["sources"]
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(r, f, ensure_ascii=False, indent=2)
PYEOF
cp "$OUT/chapter.md" "$OUT/chapter.preview.svg" "$NEG/"
if python3 "$ROOT/scripts/delivery_gate.py" --input-dir "$CASE" --output-dir "$NEG" \
        --chapter "$NEG/chapter.md" --report "$NEG/gate_report"; then
    echo "ERROR: 负例未判 FAIL，门禁失效" >&2
    exit 1
else
    echo "OK: 负例如期判 FAIL（退出码 $?）"
fi

echo "== 全部完成；产物见 $OUT =="
