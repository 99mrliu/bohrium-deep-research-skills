# 最小示例（SYNTHETIC / 合成数据）

**免责声明**：`inputs/raw_ocr.txt` 是为演示手写的 3 页伪“材料学论文”OCR
文本（页间以 form feed `\f` 分隔），植入了 15 处人工错误；它不来自任何
真实扫描件。`outputs/` 中的全部文件都是**真实运行**下列命令生成、并经
人工逐条目检（eyeball）确认的，不是手工编造。

## 运行命令（Python 3 标准库，无第三方依赖）

```bash
cd skill
# 一键：
python3 scripts/run_pipeline.py \
  --input examples/minimal/inputs/raw_ocr.txt \
  --case examples/minimal/inputs/case.json \
  --out examples/minimal/outputs
# 或分步：
python3 scripts/confusion_scan.py --input examples/minimal/inputs/raw_ocr.txt \
  --out examples/minimal/outputs
python3 scripts/postcorrect.py --input examples/minimal/inputs/raw_ocr.txt \
  --candidates examples/minimal/outputs/candidates.jsonl \
  --out examples/minimal/outputs
python3 scripts/ocr_qc.py --raw examples/minimal/inputs/raw_ocr.txt \
  --corrected examples/minimal/outputs/corrected.txt \
  --candidates examples/minimal/outputs/candidates.jsonl \
  --change-log examples/minimal/outputs/change_log.jsonl \
  --review examples/minimal/outputs/review_list.json \
  --case examples/minimal/inputs/case.json \
  --out examples/minimal/outputs
```

## 植入错误与预期结局（默认门控）

| 植入 | 覆盖模式 | 规则 | 置信 | 结局 |
|---|---|---|---|---|
| c0mposition | 0→O | dig0_o | high | ✅ 纠正为 composition |
| phot0n | 0→O | dig0_o | high | ✅ 纠正为 photon |
| spectr0scopy | 0→O | dig0_o | high | ✅ 纠正为 spectroscopy |
| ana1ysis | 1→l | dig1_l | high | ✅ 纠正为 analysis |
| 1attice | 1→l | dig1_l | high | ✅ 纠正为 lattice |
| crysta11ine | 1→l ×2 | dig1_l | high | ✅ 纠正为 crystalline |
| cata1yst | 1→l | dig1_l | high | ✅ 纠正为 catalyst |
| annea1ing | 1→l | dig1_l | high | ✅ 纠正为 annealing |
| fina1 | 1→l | dig1_l | high | ✅ 纠正为 final |
| diff raction | 伪分词（连字 ff 丢失） | split_merge | high | ✅ 纠正为 diffraction |
| nished | fi 连字丢失 | lig_fi | high | ✅ 纠正为 finished |
| a-particles | 希腊字母拉丁化 α→a | greek_a | high | ✅ 纠正为 α-particles |
| rnetal | rn→m | seq_rn_m | medium | ⏸ 暂缓，进 review_list（需 --aggressive） |
| vvavelength | vv→w | seq_vv_w | medium | ⏸ 暂缓，进 review_list（需 --aggressive） |
| `l`（"was l mV"） | 孤立 l/1 歧义 | alone_l | low | ⏸ 永不改动，进 review_list（真正歧义：1 mV 还是 l？） |
| `#7@z~` | 符号乱码 | unreadable_sym | high | 🏷 标记为 [unreadable]，绝不猜测 |

合计：16 个候选；13 处应用（12 处替换 + 1 处标记）；3 处暂缓。
12 处替换纠正 ≥ 10 的验收门槛；review_list 非空证明 precision-first
门控确实生效。

## 看什么

- `outputs/change_log.jsonl` —— 每条含 page/line/col/before/after/rule/
  confidence；可用 `line[col:col+len(before)] == before` 在原文上复核。
- `outputs/review_list.json` —— 3 条暂缓项各带机器可读原因；**这就是
  “不猜”的证据**。
- `outputs/qc_report.json` —— 可疑词元率 0.1067 → 0.0201（16/150 →
  3/149）；剩余的 3 个 suspicious 正是 review_list 中的三项，诚实闭环。
- `outputs/result.json` —— `case_id` 原样回显，`output_contract` 四字段
  全部 produced；`sources.tools` 如实记录本机无 tesseract / 无平台
  ocr-tool（本 Skill 是 OCR 下游，不依赖它们）。

## 复跑 --aggressive（可选）

加 `--aggressive` 后 medium 两项（rnetal→metal、vvavelength→wavelength）
会被应用（15 处编辑），low 项 `l` 依然不动——低置信永不应用是硬策略。
