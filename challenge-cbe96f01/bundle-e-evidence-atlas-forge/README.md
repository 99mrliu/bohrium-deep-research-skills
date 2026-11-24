# evidence-atlas-forge

引用与事实核验的**下游渲染工程**交付协议：三态同源交付（result.json / HTML 证据图谱 / SVG 页图预览），渲染即校验——quote 回查失败的证据卡打 VERIFICATION FAILED 徽标并退出码 1。详见 [SKILL.md](SKILL.md)。

## 布局

- `SKILL.md` — Skill 本体（运行契约、工作流程、异常处理、result.json schema）
- `scripts/ingest.py` — 材料解析
- `scripts/build_atlas.py` — 证据图谱渲染门（自包含 HTML + 输入哈希 manifest）
- `scripts/page_maps.py` — 逐 finding SVG 页图（摘录行高亮）
- `references/` — 三态交付一致性契约、严重度分级与视觉编码
- `examples/` — **合成示例**（`bash examples/run_example.sh`）

## 快速自检

```bash
bash examples/run_example.sh
# 期望：正常 result 渲染通过（exit 0），得到 atlas/report.html 与 3 张 SVG 页图；
# 埋了过期摘录的 result 被渲染门拦下（exit 1，VERIFICATION FAILED）
```

无第三方依赖：Python ≥3.8 标准库；PDF 用系统 `pdftotext`（可回退纯文本）。SVG/HTML 为文本产物，可直接在浏览器目检。
