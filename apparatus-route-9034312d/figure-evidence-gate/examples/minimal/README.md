# 最小合成示例（synthetic minimal example）

**这是示例，不是真实案例结果。** 源文本 `sources/methods_excerpt.txt` 是为演示而虚构的一段
"Methods 摘录"（豆粕多肽酶解-纯化），文中已明确标注"合成/虚拟"。

## 目录内容

| 文件 | 说明 |
|---|---|
| `sources/methods_excerpt.txt` | 虚构的抽取源文本（扮演 `/app/work/sources/*.txt` 的角色） |
| `ledger.json` | 证据台账：8 个元素，覆盖全部 6 种 kind；7 条带逐字 quote，1 条（`note-1`）演示豁免路径（`waived:true` + `waiver_reason`） |
| `gate_report.json` | **真实**门禁输出（在本机对上面两个文件运行所得，非手写）：7 verified + 1 waived，verdict=passed |
| `figure.svg` | **真实**渲染输出（`ledger_render.py` 确定性生成；重跑字节一致） |
| `export_report.json` | **真实**导出输出（`export_svg.py`）；末尾附 `local_environment_note` 说明本机各导出工具可用性。按打包约束，PDF/PNG 二进制不随包分发（测试时写入 /tmp） |

## 复现方式

```bash
cd examples/minimal

# 1) 门禁：quote 逐条核验（退出码 0 = passed）
python3 ../../scripts/evidence_gate.py ledger.json \
    --sources-dir sources --report gate_report.json

# 2) 渲染：台账 → SVG（确定性；连跑两次可用 cmp 验证字节一致）
python3 ../../scripts/ledger_render.py ledger.json --out figure.svg

# 3) 导出：回退链 cairosvg → rsvg-convert → inkscape → chrome-headless
python3 ../../scripts/export_svg.py figure.svg \
    --pdf /tmp/figure.pdf --png /tmp/figure.png --report export_report.json
```

## 演示要点

- 每个 SVG 图元组携带 `id="el-<eid>"` 与 `data-eid`，`<title>` 内含该元素的证据 quote，
  可在浏览器/编辑器中悬停回查。
- `note-1` 为豁免元素：图中呈琥珀色虚线 + `[waived]` 角标，gate_report.json 中
  计为 `waived` 并附理由——展示"豁免必须如实披露，不得隐藏"。
- 负例自测：把任一 quote 改动几个字再跑门禁，会得到 `unverified` 及 difflib
  near-miss 提示（相似度+原文候选），据此修正 quote 即可复归通过。
