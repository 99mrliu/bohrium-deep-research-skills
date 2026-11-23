# 最小端到端示例(合成示例 / 非正式案例结果)

> 本目录 `data/` 下所有文件均为**合成数据**:并非真实论文,也不是任何评测案例的正式结果,
> 仅用于演示与自测。`source_en.txt` 是一篇 3 页合成 mini-paper(含字面 `\f` 分页符、
> 每页页眉 `Synthetic Example Journal 2026`、一处断词 `charge-`+`transport`、每页页码行)。

## 命令(在 skill/ 目录下执行)

```bash
# 1. 分段
python3 scripts/segment_text.py --src examples/data/source_en.txt \
    --out /tmp/paragraphs.jsonl --report /tmp/seg_report.json

# 2a. 对齐:完整译文(带 [[PXXXX]] 标签)→ 退出码 0
python3 scripts/align_bilingual.py --src /tmp/paragraphs.jsonl \
    --tgt examples/data/target_zh_full.txt \
    --out /tmp/alignment_full.json --report /tmp/align_full_report.json
echo "exit=$?"   # 0

# 2b. 对齐:缺陷译文(无标签,删了第 4 段,第 5/6 段交换)→ 退出码 1
python3 scripts/align_bilingual.py --src /tmp/paragraphs.jsonl \
    --tgt examples/data/target_zh_flawed.txt \
    --out /tmp/alignment_flawed.json --report /tmp/align_flawed_report.json
echo "exit=$?"   # 1

# 3. 渲染缺陷对齐结果,供人工检查
python3 scripts/render_side_by_side.py --alignment /tmp/alignment_flawed.json \
    --src /tmp/paragraphs.jsonl --tgt examples/data/target_zh_flawed.txt \
    --out /tmp/bilingual.html --md /tmp/bilingual.md
```

## 预期结果

**分段**(`seg_report.json`):
- `pages = 3`
- `hyphen_joins >= 1`(`charge-` + `transport` 被修复为 `chargetransport`)
- `dropped_repeated_lines` 包含 `Synthetic Example Journal 2026`(页眉出现在全部 3 页页首)
- `page_number_lines_dropped = 3`
- `paragraphs = 6`,seg_id 为 P0001…P0006

**完整译文对齐**:
- 退出码 `0`;所有 6 段通过 `[[PXXXX]]` 标签硬对齐,`coverage.missing` 为空。

**缺陷译文对齐**:
- 退出码 `1`。
- 贪心锚点匹配的表现:P0001–P0003 正常对齐(anchor_score 1.0 / 1.0 / 0.5);
  P0004 的锚点 `n:12` 与「P0005 的译文块」(含 `[12]`)重叠,于是 P0004 被配到该块,
  状态为 `aligned` 但 **anchor_score 仅 0.33**(远低于正常配对的 1.0,需人工复核);
  P0005 退而配到顺序在它之前的「P0006 的译文块」,锚点完全不重叠
  → 同时标记 `anchor-mismatch` 与 `order-swap`;P0006 没有任何可用译文块
  → `missing-translation`。
- 因此 `coverage.missing = ["P0006"]`、`coverage.order_swaps = ["P0005"]`、
  `coverage.anchor_mismatch = ["P0005"]`。
- 这正是设计意图:**删除+乱序不会被静默吞掉**,而是以 missing / order-swap /
  anchor-mismatch 三种显式登记呈现,人工据此回到翻译环节补 P0004、恢复 5/6 顺序后重跑。

**渲染**:
- `bilingual.html` 含 `<nav>` 索引、每行 `id="P0001"` 锚点与状态 CSS class
  (`anchor-mismatch` 琥珀色、`missing-translation` 红色);
- `bilingual.md` 为两栏预览表(ID + 状态 + 前 80 字符)。
