# minimal 示例（完全合成数据）

> **合成声明**：本示例中的"论文"、作者、期刊名、引用、公式、图表题全部为演示而编造，
> 不对应任何真实文献。`inputs/blocks.jsonl` 是手工编写的 20 个块，用来覆盖全部
> 8 种 kind 及两类异常（2 个 unresolved、1 个 bbox=null 的 body 块）。

## 运行（Python 3 标准库即可，无第三方依赖）

```bash
cd examples/minimal
python3 ../../scripts/anchor_map.py --blocks inputs/blocks.jsonl --out outputs/anchor_map.json
python3 ../../scripts/render_preview.py --blocks inputs/blocks.jsonl \
    --anchor-map outputs/anchor_map.json \
    --out-md outputs/deliverable.md --out-html outputs/preview.html
python3 ../../scripts/render_qc.py --blocks inputs/blocks.jsonl \
    --anchor-map outputs/anchor_map.json \
    --md outputs/deliverable.md --html outputs/preview.html \
    --case inputs/case.json \
    --out-qc outputs/render_qc.json --out-result outputs/result.json --outdir .
```

预期 stdout 末行：`qc pass: blocks=20 md=20 html=20 problems=0 warnings=2`，退出码 0。

## 如何检查 preview.html

直接双击 `outputs/preview.html`（无需网络、无需服务器）。应当看到：

- 左侧深色侧栏：Page 1 / Page 2 分组，列出全部 20 个锚点链接，点击可跳转；
- 正文每个块左上角有蓝色锚点徽章（如 `p1-b5`），鼠标悬停块体显示 page/bbox/kind；
- `p1-b6`（bbox=null 的 body 块）带黄色 `bbox: n/a` 徽标；
- `p2-b7`、`p2-b10`（unresolved）红框、红色徽章，显示无法解析的原因；
- 公式块（`p1-b7`、`p2-b5`）等宽字体浅蓝底；图注块斜体；
- 页眉页脚（`p1-b1`、`p1-b9`、`p2-b1`、`p2-b11`）在文末附录中置灰（opacity 0.45）；
- 查看源码可确认：只有内联 `<style>`，没有 `<script>`，没有任何 `http://` / `https://` 引用。

## 本目录输出的真实性

`outputs/` 下的 5 个文件（anchor_map.json、deliverable.md、preview.html、render_qc.json、
result.json）均为上述命令**真实运行**的产物，并已人工核对：Markdown 锚点齐全、HTML 侧栏 /
data-anchor / 置灰 / 红框 / 等宽公式均符合预期、无外部引用；QC 结果 `pass` 且 warnings
正确报告了 `p1-b6` 的 bbox=null 与 2 个 unresolved 块。

## 已知警告（属预期，非缺陷）

`render_qc.json.warnings` 中的两条：

1. `p1-b6` bbox=null —— 渲染正常但无坐标，演示"警告而不崩溃、不丢弃"；
2. `p2-b7, p2-b10` unresolved —— 演示未解析块的保留与高亮策略。
