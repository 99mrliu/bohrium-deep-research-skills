# 最小调用示例（合成示例，非正式案例结果）

本目录是**合成示例**：`case.example.json`（含 "SYNTHETIC EXAMPLE" 标注，case_id `demo-evidence-01`）中的研究问题、4 条文献、摘要与 DOI 均为演示虚构；S4 带 `fixture_note` 标注其为 S1 的合成重复导出夹具（仅作 provenance 演示）。`decisions.example.json` 是手写的演示判定，每条 `evidence_quote` 都是对应记录标题/摘要的真实逐字子串。仅用于说明接口与完整流程，不冒充平台正式案例的结果。

## 运行（端到端）

```bash
W=$(mktemp -d); mkdir -p $W/input $W/work $W/output
cp examples/minimal/case.example.json $W/input/case.json
cp examples/minimal/decisions.example.json $W/work/decisions.json
# 1. 锚定：引文 → 字符偏移，核验失败的进入 rejected_register 并降级
python3 scripts/evidence_engine.py anchor --case $W/input/case.json \
  --decisions $W/work/decisions.json --out $W/work/anchored.json
# 2. 卡片与装配：确定性排序 + 理由卡片 + 契约字段镜像
python3 scripts/evidence_engine.py cards --case $W/input/case.json \
  --anchored $W/work/anchored.json --out $W/output/result.json \
  --cards-md $W/output/rationale_cards.md
# 3. 交付校验：从 result.json 重算每一个锚点
python3 scripts/evidence_engine.py validate --case $W/input/case.json \
  --result $W/output/result.json
```

预期输出：

```
anchor: case_id=demo-evidence-01 records=4 verified=4 rejected=0 undecided=0 -> .../anchored.json
cards: state=complete verification_rate=1.0000 records=4 -> .../result.json (+ .../rationale_cards.md)
VALIDATE PASS: case_id=demo-evidence-01 records=4 contract_fields=5 verification_rate=1.0000 state=complete
```

排序结果（label 层级 → confidence 降序 → record_id）：S1(keep,0.93,rank1) → S3(pending,0.55,rank2) → S4(exclude,0.80,rank3，fixture_note 标注的 S1 重复导出，仅作 provenance) → S2(exclude,0.88,rank4)。`rationale_cards.md` 中每条引文以偏移 + 源字段 ±40 字符上下文渲染，可人工抽读核对。

## 退化路径（诚实 partial）

省略 `--decisions` 重跑第 1–2 步：全部记录 pending（"not judged"），`verification_rate=0.0`，`status.state=partial` 且 `incomplete` 列出未判定记录——validate 仍 PASS（partial 是合法交付态）。

## 拒绝路径（反编造演示）

把任一 `evidence_quote` 改成摘要中不存在的句子（例如 "quantum retrosynthesis achieved 99 percent accuracy"）再跑第 1–3 步：该引文进入 `rejected_register`（附 difflib 最近邻匹配的 ratio 与真实子串），对应决定被降级为 pending（reason "evidence anchor failed verification"），`verification_rate=0.75`，`status.state=partial`——validate 仍 PASS，因为降级后的结果自洽；编造的引文**无法**以 keep 标签进入 result.json。反之，若有人直接篡改 result.json 中的 `surface_form` 或偏移，validate 重算不变式 `record[field][start:end] == surface_form` 失败，输出 VALIDATE FAIL（退出码 1）。
