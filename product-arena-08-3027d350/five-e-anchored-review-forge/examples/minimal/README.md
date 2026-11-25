# minimal 示例（**合成示例**，非正式案例、非真实论文）

演示 anchored-review-forge 的端到端流水线：`inputs/make_sample.py` 用纯
Python 标准库手写一个合成单栏 PDF（2 页 Letter，含 title、两个 heading、
若干 body、一条 `Figure 1:` caption、一条公式行 `E = m c^2 + ...`），
随后四个脚本依次产出 blocks、逐页 SVG 叠加图、自包含 review.html、
manifest 与契约感知 result.json。

> 注：平台约束要求 bundle 全部为 UTF-8 文本、无二进制，因此
> `inputs/sample.pdf` 不随 bundle 提交；运行 `make_sample.py` 即可逐字节
> 重建（生成器是确定性的，重建后 blocks/坐标与 `outputs/` 中一致；
> 仅 review.html 内嵌的生成时间戳会随运行时刻变化，其 sha256 也随之变化，
> 每次重跑第 4 步会重新生成自洽的 manifest.json）。

## 复现命令

```bash
cd examples/minimal
python3 inputs/make_sample.py                # 生成 inputs/sample.pdf
python3 ../../scripts/mini_extract.py   --pdf inputs/sample.pdf --out-dir outputs
python3 ../../scripts/render_overlay.py --blocks outputs/blocks.jsonl --page-meta outputs/page_meta.json --out-dir outputs
python3 ../../scripts/render_review.py  --blocks outputs/blocks.jsonl --page-meta outputs/page_meta.json --out-dir outputs
python3 ../../scripts/render_manifest.py --out-dir outputs --blocks outputs/blocks.jsonl --page-meta outputs/page_meta.json --case inputs/case.json --pdf inputs/sample.pdf
```

四步退出码均为 0（`*.report.json` 中 status 均为 success，engine=pymupdf）。

## 目检结论（实际做过的检查）

1. **SVG 良构**：`xmllint --noout overlays/page-1.svg overlays/page-2.svg`
   均无输出通过；脚本写出前也用 `xml.etree.ElementTree.fromstring` 自检。
2. **矩形数 = 块数**：page-1.svg 含 9 个块矩形对应 9 个块，page-2.svg
   含 4 个对应 4 个（页面底框 rect 不计）；13 个 `blk-*` id 全文唯一。
3. **坐标抽查**：全部 13 个矩形满足 `0 ≤ x, y` 且 `x+w ≤ 612`、`y+h ≤ 792`
   （页宽页高）；抽查 p1.b1 title 矩形 y=70.74 与 make_sample.py 中
   title 排版 y=72 吻合（差值为行框上留白）。
4. **kind 分类**：13 块 = title×1、heading×2、equation×1、caption×1、
   body×8，与合成版式设计逐项一致。
5. **review.html**：Python `html.parser` 全文解析无异常；13 个徽章的
   `data-anchor` 集合 = SVG `blk-*` id 集合 = blocks.jsonl 的 id 集合
   （三向一致）；文件头注释含生成时间与 blocks.jsonl/page_meta.json 的
   sha256，与实算一致；内嵌 2 个 `<svg>`，无 `<img>` 外链、无外部
   脚本/样式。另用含 `& < > " '` 的对抗文本块做过转义压测（在 /tmp，
   不进 outputs）：SVG 可解析且 `<title>` 往返还原，HTML 中无裸注入。
6. **manifest 哈希复核**（`shasum -a 256` 实算 vs manifest.json 条目）：
   - `review.html`：`36c0dadcbce7ad35eac92a64476f6b10702bb43a8d1106dc7dd12315c2834837` —— 一致
   - `overlays/page-1.svg`：`923131b5b27f625b6e9df3271986261de0c3956dc20c22d95aeb877f19d1a33c` —— 一致
7. **状态流转**：除本示例外，自测中真实触发过 partial（屏蔽 pymupdf
   走 pdftotext 引擎，产出相同 13 块并记 title 兜底 warning，退出码 2）
   与 failed（PDF 不存在 / 输入缺失，退出码 3）路径。
