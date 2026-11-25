# 示例走查（example_walkthrough.md）

> **合成示例 / 示意输出**：本文件全部基于 `fixtures/` 下的合成夹具（内容虚构，不对应任何真实案件）。下列输出为真实运行所得、经删节标注；路径中的 `$SKILL` 指技能根目录。

## 0. 夹具

- `fixtures/claims_pub_HX1001.txt`：虚构案件 HX1001 公开版权利要求（3 项，装置权利要求）。
- `fixtures/claims_grant_HX1001.txt`：对应授权版（前序改写；`a fastener` 收窄为 `a titanium alloy fastener`；删除 damping pad 要素；从属项重排）。
- `fixtures/claims_wo_boundary_HX1002.txt`：虚构案件 HX1002 的 WO 合并 OCR 单版本文本，含一条已声明的合并边界行。
- `fixtures/note_bad.md`：故意含违禁措辞的伪造说明（闸门演示用）。
- `fixtures/case_fixture.json`：case_id 与 output_contract 示例。

## 1. 切分（claim_segment.py）

```bash
python3 $SKILL/scripts/claim_segment.py \
  --input $SKILL/examples/fixtures/claims_pub_HX1001.txt --output /tmp/seg_pub.json
python3 $SKILL/scripts/claim_segment.py \
  --input $SKILL/examples/fixtures/claims_grant_HX1001.txt --output /tmp/seg_grant.json
```

`seg_pub.json` 要点（示意输出，删节）：

```json
{
  "num_claims": 3,
  "segmentation_degraded": false,
  "claims": [
    {"number": 1, "type": "independent", "references": [],
     "transition": {"quote": "comprising", "span": [227, 237]},
     "preamble": {"quote": "A mounting bracket for a photovoltaic panel,", "span": [182, 226]},
     "elements": [
       {"index": 1, "kind": "element", "quote": "a frame member", "span": [239, 253]},
       {"index": 2, "kind": "element", "quote": "a fastener configured to secure the frame member to a rail", "span": [255, 313]},
       {"index": 3, "kind": "element", "quote": "and a damping pad disposed between the frame member and the rail.", "span": [315, 380]}
     ]},
    {"number": 2, "type": "dependent", "references": [1]},
    {"number": 3, "type": "dependent", "references": [1, 2]}
  ]
}
```

逐字性可机器复核：每个节点 `quote == 原文[span[0]:span[1]]`。

## 2. 对齐（claim_align.py）

```bash
python3 $SKILL/scripts/claim_align.py --a /tmp/seg_pub.json --b /tmp/seg_grant.json \
  --threshold 0.60 --output /tmp/corr.json
```

对应表要点（示意输出，删节）：

```json
{
  "status": "ok",
  "threshold": 0.6,
  "statistics": {"claims_a": 3, "claims_b": 2, "claim_pairs": 2,
                 "claims_added": 0, "claims_removed": 1,
                 "element_pairs": {"unchanged": 3, "modified": 2, "added": 1, "removed": 2, "reordered": 0}},
  "claim_pairs": [
    {"number_a": 1, "number_b": 1,
     "element_pairs": [
       {"classification": "modified", "similarity": 0.8073,
        "a": {"kind": "preamble", "quote": "A mounting bracket for a photovoltaic panel,"},
        "b": {"kind": "preamble", "quote": "A mounting bracket assembly for a photovoltaic panel, the bracket"}},
       {"classification": "modified", "similarity": 0.8788,
        "a": {"quote": "a fastener configured to secure the frame member to a rail"},
        "b": {"quote": "a titanium alloy fastener configured to secure the frame member to a rail."}},
       {"classification": "removed", "similarity": null,
        "a": {"quote": "and a damping pad disposed between the frame member and the rail."}, "b": null}
     ]},
    {"number_a": 2, "number_b": 2,
     "candidates": [{"similarity": 0.4286, "note": "below_threshold_not_forced",
        "a": {"quote": "wherein the damping pad comprises rubber."},
        "b": {"quote": "wherein the frame member is an extruded aluminum profile."}}]}
  ],
  "claims_removed": [{"number": 3, "quote": "3. The mounting bracket of claim 1 or 2, wherein ..."}]
}
```

解读：收窄要素判为 `modified`；被丢弃要素判为 `removed`；同编号但主题不同的从属项，其 wherein 从句相似度 0.4286 < 0.60，只列为候选、未强制配对；公开版第 3 项在授权版无对应编号，判为整项删除。`statistics` 由脚本按对应表重算。

## 3. 渲染与闸门（scope_note.py）

```bash
python3 $SKILL/scripts/scope_note.py --table /tmp/corr.json --case-id HX-SYNTH-0001 --output /tmp/note.md
python3 $SKILL/scripts/scope_note.py --gate /tmp/note.md
# -> 措辞闸门通过：未检出违禁结论性措辞。（退出码 0）

python3 $SKILL/scripts/scope_note.py --gate $SKILL/examples/fixtures/note_bad.md
# -> 措辞闸门检出违禁结论性措辞（2 处）：
#      第 5 行：含违禁短语「保护范围相同」：...
#      第 5 行：含违禁短语「未实质改变」：...
# （退出码 1）
```

渲染说明节选（示意输出）：

```markdown
## 状态与限制
- status：`ok`；mode：`two_version`
## 统计（由对齐脚本按对应表重新计算）
- 要素对：未变更 3，已修改 2，新增 1，删除 2，顺序调整 0。
### 权利要求：版本 A 第 1 项 ↔ 版本 B 第 1 项
4. 文本分类：**已修改**（相似度 0.8788）
  - 版本 A（element #2，span 255–313）：
> a fastener configured to secure the frame member to a rail
  - 版本 B（element #2，span 421–495）：
> a titanium alloy fastener configured to secure the frame member to a rail.
---
> **诚实性声明（固定文本，不得删改）**：本说明仅逐字报告两版本权利要求文本层面的差异；……
```

## 4. 缺失版本与 OCR 边界（partial 情形）

```bash
python3 $SKILL/scripts/claim_segment.py \
  --input $SKILL/examples/fixtures/claims_wo_boundary_HX1002.txt --output /tmp/seg_wo.json
python3 $SKILL/scripts/claim_align.py --a /tmp/seg_wo.json --output /tmp/one_sided.json
```

要点（示意输出）：

```json
{
  "mode": "one_sided_inventory",
  "status": "partial",
  "limits": [
    "仅提供单一版本（缺少 --b）：未执行双版本比对，以下为单侧清单。",
    "权利要求 1 的 span [271, 425] 跨越已声明的 OCR 合并边界；边界偏移见版本 A 的 ocr_boundaries。"
  ],
  "one_sided_claims": [{"number": 1, "type": "independent"}, {"number": 2, "type": "dependent"}]
}
```

`seg_wo.json` 中 `contains_ocr_boundary: true`，`ocr_boundaries` 记录边界行 span 与逐字 quote，权利要求 1 及其跨越边界的要素带 `crosses_ocr_boundary: true`——比对只在该处是部分的，且位置被明确指出。
