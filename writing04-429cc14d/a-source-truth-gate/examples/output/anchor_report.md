# 论断-来源锚点审计报告（claim_anchor_audit）

- 生成时间（UTC）：1970-01-01T00:00:00Z
- 来源目录：`examples/input/sources`
- 台账文件：`examples/input/claims.jsonl`
- 审计依据：本审计仅依据 --sources 目录中的来源文本文件，未进行任何联网核实；FAIL 的论断必须修复为逐字引文、改为明确转述，或降级标注为证据不足。

## 汇总：PASS 4 / FAIL 1 / ERROR 0（共 5 条）

| id | 状态 | 诊断 | char_offset |
| --- | --- | --- | --- |
| C1 | PASS |  | 432 |
| C2 | PASS |  | 414 |
| C3 | PASS |  | 411 |
| C4 | FAIL | paraphrase_or_minor_alteration |  |
| C5 | PASS |  | 530 |

## 逐条明细

### C1 — PASS

- 论断：HNX-3 在 320 K 下 ZT 达到 1.42，较基线提升约 37%
- 来源文件：`fake_paper_alpha.txt`
- 锚点偏移（归一化文本）：432

### C2 — PASS

- 论断：绿地覆盖率提高至 40% 时夏季夜间平均气温降低 1.8 °C
- 来源文件：`fake_paper_beta.txt`
- 锚点偏移（归一化文本）：414
- 定位符 `第 3 节` 是否见于来源：True

### C3 — PASS

- 论断：GMP-7 对 S-伪素的 kcat/Km 为 3.6×10^5 L/(mol·s)
- 来源文件：`fake_paper_gamma.txt`
- 锚点偏移（归一化文本）：411

### C4 — FAIL

- 论断：HNX-3 的热电优值在 320 K 时较基线提升约 37%
- 来源文件：`fake_paper_alpha.txt`
- 诊断：paraphrase_or_minor_alteration（转述或细微改动冒充逐字引文）
- 最接近窗口（前 60 字符）：20 K 时,HNX-3 的无量纲热电优值 ZT 达到 1.42,较基线材料提升约 37%。
- 窗口相似度：0.9348（偏移 435）

### C5 — PASS

- 论断：HNX-3 的热导率最低值出现在 400 K
- 来源文件：`fake_paper_alpha.txt`
- 锚点偏移（归一化文本）：530

---
免责声明：FAIL/ERROR 记录对应的论断-引用关系不得原样进入成品；必须修复为逐字引文、改写为明确转述，或标注证据不足。
