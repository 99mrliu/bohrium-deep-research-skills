# 最小示例（合成，非正式测试案例结果）

## 输入

`examples/make_fixtures.py` 在本地生成两份**纯 ASCII 最小 PDF**（虚构论文，
内容为演示而编造；已一并提交于 `examples/input/`，均为合法 UTF-8 文本）：
`synth_paper_alpha.pdf`（2 页）与 `synth_paper_beta.pdf`（1 页正文 + 1 个故意
留白的页，用于演示 QC 空页检出）。

## 运行

```bash
bash examples/run_example.sh
```

## 实跑结果（示例产物，标注为合成示例）

1. `ingest_register`：两份 PDF 被 pdftotext **真实解析**为文本层，
   `work/source_registry.json` 登记 SHA-256、逐页字符统计（alpha 2 页、beta 2 页
   其中第 2 页 0 字符）；`work/ingest_report.md` 列出空页。
2. `extraction_qc qc`：beta 判 `ok_with_notes`（空页:2），alpha 判 `ok`；
   报告在 `work/qc/`。
3. `locate` 真实引文 "baseline B achieves metric X = 0.71"：**命中
   alpha 第 1 页**，给出页码与字符偏移（`work/locate_hit.json`）。
4. `locate` 编造引文 "method M achieves 99 percent accuracy..."：**exit 1
   未命中**（`work/locate_miss.json`）——按规则该"证据"不得进入综述。

关键观察点：管线不假设任何预提取文本层；PDF 从原始字节真实解析，引文必须
能被机器定位到页，编造的引文会被确定性拒绝。
