# 合成示例说明

本目录为**合成示例**：`synthetic-input/mindmap.json` 描述虚构课题「催化剂Q研究规划」（14 节点、3 层、2 条备注、3 条类型化关系，含一处刻意构造的引号与 `&` 字符以演示 XML 转义），不代表任何真实研究内容。

`synthetic-output/` 收录对该输入真实执行三个脚本得到的全部**文本**产物：

- `mindmap.mm` / `mindmap.opml` / `mindmap.md` / `mindmap.mmd` / `mindmap.html`（`emit_formats.py`）
- `render_manifest.json`（`render_preview.py`；记录了构建机上的实际渲染环境）
- `roundtrip_report.json`（`roundtrip_check.py`，`match=true`）

**关于 PNG/PDF**：`mindmap.png` 与 `mindmap.pdf` 为二进制运行时产物，依包约束不入库。构建时已按下列命令在临时目录生成（PNG 2271×1507，约 100 KB；PDF 单页约 43 KB），并对 PNG 完成目视检查：

- 版面无重叠、无裁剪，肘形连线与节点底框清晰；
- CJK 渲染正确，无缺字；构建机选中字体 **PingFang SC**（见 `render_manifest.json` 的 `font.chosen`）；
- 三条关系弧线（支撑/验证/并行）均绕开中间节点，类型标注白底可读；
- 双跑比对确认 PNG/PDF/manifest 字节级一致。

复现命令（在技能包根目录执行，输出到任一临时目录）：

```bash
python3 scripts/emit_formats.py --map examples/synthetic-input/mindmap.json --outdir OUT
python3 scripts/render_preview.py --map examples/synthetic-input/mindmap.json --outdir OUT
python3 scripts/roundtrip_check.py --map examples/synthetic-input/mindmap.json \
    --mm OUT/mindmap.mm --report OUT/roundtrip_report.json
```

预期：前两步退出码 0；第三步退出码 0 且报告中 `match=true`。
