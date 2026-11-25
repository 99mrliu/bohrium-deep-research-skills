# 合成示例（synthetic，非正式案例结果）

本目录是一个**完全合成**的最小示例：`input/synthetic_paper.txt` 是两页虚构"论文"
（QZ-117 酶不存在，所有数字均为占位），`input/judgments.jsonl` 三条判断被设计为
分别命中三种门控结果：C1 → `verified`，C2（locator 故意写错页）→ `repaired_locator`，
C3（编造摘录）→ `abstain_unverifiable`。

## 真实运行命令

```bash
B=/path/to/c-anchor-gate
W=$(mktemp -d); O=$(mktemp -d)
cp $B/examples/input/judgments.jsonl $W/judgments.jsonl

python3 $B/scripts/build_index.py --input-dir $B/examples/input \
  --case $B/examples/input/case.json --workdir $W --output-dir $O
python3 $B/scripts/gate.py --workdir $W --judgments $W/judgments.jsonl
python3 $B/scripts/build_result.py --workdir $W --output-dir $O \
  --case $B/examples/input/case.json
```

## 真实输出摘录（2026-11-25 运行，macOS / Python 3.12）

build_index.py：

```
index written: /tmp/anchor-work.wi7AX6/index.json (1 documents, 1 with text layer)
skeleton result written: /tmp/anchor-out.GvuSlr/result.json
```

index.json 显示文档被切成 2 页 7 段，并带 sha256：

```json
{"doc_id": "synthetic_paper", "text_layer": true, "pages": 2, "paragraphs": 7,
 "sha256": "f279f31e0f936c1fedecc5e8f1c9b20d829a4b6844f8335635bcf01141772bbb",
 "pages_file": "pages/synthetic_paper.jsonl"}
```

gate.py：

```
gated 3 rows -> /tmp/anchor-work.wi7AX6/gated.jsonl
verdicts: {"verified": 1, "repaired_locator": 1, "abstain_unverifiable": 1}
```

gated.jsonl 中 C2 被修复定位、C3 被拦截（摘录不放行）：

```json
{"claim_id": "C2", "verdict": "repaired_locator", "final_locator": "p2.¶2",
 "reason": "quote found at p2.¶2 instead of claimed locator p1.¶2"}
{"claim_id": "C3", "verdict": "abstain_unverifiable", "final_locator": null,
 "reason": "quote not found as substring anywhere in extracted text of doc synthetic_paper; possible paraphrase or fabrication"}
```

build_result.py：

```
result.json written: /tmp/anchor-out.GvuSlr/result.json (status=success, evidence=2, abstentions=1)
evidence_table.md written: /tmp/anchor-out.GvuSlr/evidence_table.md (3 rows)
```

result.json 关键片段（output_contract 镜像出实际值，定位修复留痕）：

```json
{"status": "success",
 "output_contract": {"overall_quality_score": 3.5,
                     "verdict_summary": "synthetic demo case; two claims anchored, one abstained"},
 "anchor_coverage": {"synthetic_paper": {"paragraphs_indexed": 7, "claims_anchored": 2}},
 "change_records": [{"type": "locator_repair", "claim_id": "C2",
                     "old_locator": "p1.¶2", "new_locator": "p2.¶2"}],
 "limits": ["1 of 3 judgment rows abstained (see abstentions)"]}
```

## 阴性检查（同为真实运行）

- 不存在的 PDF：`index.json` 标记 `text_layer=false, note="missing: file not found"`，
  该文档判断判 `abstain_no_text_layer`，`result.json` status=`partial`，exit 0。
- 零文档输入：status=`partial`，limits 写明 `no documents discovered ...`，exit 0，不崩溃。
- 畸形 judgments 行（缺字段 / 非法 JSON）：gate.py 逐行列出并以 exit 1 结束。
- 跨段摘录（quote 横跨 ¶3–¶4）：判 `verified_span`，final_locator=`p1.¶3-p1.¶4`。
