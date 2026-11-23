# EXPECTED — 示例预期行为与本机实测记录

> 本目录全部内容为**合成示例**：paper.txt 是虚构论文，claims.json 的论断是
> 待核验问题而非权威事实，verdicts.json 是演示用判定输入。示例仅用于验证
> 交付工程流水线本身，不构成任何科研结论。

## 运行方式

```bash
bash examples/run_example.sh
```

产物写入 `examples/out/`（每次运行先清空重建）。

## 预期流水线

1. `paper.txt → pages.jsonl`（按换页符 `\f` 分页，3 页）；
2. `contract_assemble.py skeleton`：发现 8 个契约字段，骨架 status=partial，
   契约字段全部 null 占位，missing_items 列出 8 字段；
3. `contract_assemble.py merge`：写入 3 条判定、摘要、分布等（先存后改，
   空占位不覆盖已有非空字段）；
4. `cards_render.py`：3 张卡片（C1 supported、C2 contradicted、
   C3 partially_supported 且含冲突并列行）；
5. `report_render.py`：verification-report.md + 真实渲染预览 + render-info.json；
6. 回写产物路径与渲染链、置 status=success，`validate` 通过；
7. `gate.py`：契约校验 + 6 条 quote 归一化回查 + 卡片-结果一致性，PASS，exit 0。

## 本机实测记录（2026-11-23，macOS arm64，Python 3.12.14）

- 渲染链实际路径：**xelatex 未安装 → pdflatex 未安装 → pandoc 未安装 →
  html 兜底成功**（`render-info.json` 的 `attempts` 逐条记录）。
- 预览产物：`examples/out/verification-report.html`（约 6.5 KB，自包含、
  内联 CSS）；报告尾部含"渲染降级声明"。
- `run_example.sh` 全程 `set -euo pipefail`，最终 exit 0；gate 输出
  `GATE: PASS（0 个 ERROR，0 个 WARN）`。
- 已验证的失败路径：validate 遇空契约字段 exit 1；cards_render 遇非法
  verdict/空 quotes exit 1；gate 遇篡改 quote exit 1；IO 错误 exit 2。

## 在其他机器上

若机器装有 xelatex / pdflatex / pandoc，第 5 步会产出真实的
`verification-report.pdf`（render-info.json 记录实际命中的链），报告中
不再有降级声明。两条路径均为合法预期；唯一不合法的是"声称有 PDF 但实际没有"。
