# bilingual-align-render

长文献翻译的「分段 + 双语段落对照」工程化技能:确定性分段、稳定段落 ID、锚点对齐、双语对照渲染。
核心目标——**译文 100% 可回溯,无丢段/重段/乱序**;任何缺口显式登记,绝不静默修补。

## 文件结构

```
skill/
├── SKILL.md                        # 技能定义(frontmatter + Runtime contract + Workflow)
├── README.md                       # 本文件
├── GITHUB_URL.txt                  # 仓库定位
├── scripts/
│   ├── segment_text.py             # PDF/TXT → paragraphs.jsonl(页码追踪、断词修复、页眉页脚剔除)
│   ├── align_bilingual.py          # 源段 ↔ 译文段锚点对齐 → alignment.json(缺失即退出码 1)
│   ├── render_side_by_side.py      # alignment → 双语对照 bilingual.html / .md(状态配色 + 锚点)
│   └── write_result.py             # 占位先行、就地改进的 result.json 写入器
├── references/
│   ├── segmentation_rules.md       # 分段规则全文(页断、断词、页眉页脚、ID 方案、已知限制)
│   └── alignment_format.md         # alignment.json schema、状态分类表、[[PXXXX]] 标签约定
└── examples/
    ├── minimal_example.md          # 端到端最小示例(合成数据)与预期输出
    └── data/                       # 合成 3 页 mini-paper 源文 + 完整/缺陷两份译文
```

## 环境要求

- Python 3.8+(仅标准库,无第三方依赖)
- `pdftotext`(poppler)——仅当输入为 PDF 时需要;TXT/MD 输入不需要

## 快速开始

```bash
# 1. 分段(PDF 自动调用 pdftotext -layout;TXT 直接读取)
python3 scripts/segment_text.py --src paper.pdf --out paragraphs.jsonl --report seg_report.json
# 2. 翻译:按 paragraphs.jsonl 逐段产出 target_zh.txt(空行分块,建议块首写 [[P0001]] 标签)
# 3. 对齐(有 missing-translation 时退出码 1)
python3 scripts/align_bilingual.py --src paragraphs.jsonl --tgt target_zh.txt \
    --out alignment.json --report align_report.json
# 4. 渲染双语对照
python3 scripts/render_side_by_side.py --alignment alignment.json --src paragraphs.jsonl \
    --tgt target_zh.txt --out bilingual.html --md bilingual.md
# 5. 结果文件(先写占位,再就地改进)
python3 scripts/write_result.py --case /input/case.json --out /app/output/result.json --status partial
```

端到端可运行示例见 `examples/minimal_example.md`。

## 维护说明

- 所有脚本均为确定性实现;改动规则时同步更新 `references/` 文档与示例预期。
- 新增对齐状态时同步更新三处:`align_bilingual.py`、`references/alignment_format.md`、
  `render_side_by_side.py` 的 CSS 配色。
- 示例数据均为合成数据;修改后需重跑 `examples/minimal_example.md` 中全部命令验证。
