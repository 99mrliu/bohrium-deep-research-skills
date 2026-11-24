# examples/ — 合成示例（synthetic, illustrative）

> **本目录全部数据均为合成示例 / synthetic, illustrative**：题名、作者、期刊、
> DOI、案例 ID 皆为虚构，仅用于演示与自检，不得冒充真实文献或正式评测案例结果。

## 目录内容

| 文件 | 说明 |
|---|---|
| input/case.json | 合成案例：GLP-1 受体激动剂与 2 型糖尿病心血管结局（虚构） |
| input/task.md | 合成任务说明 |
| input/records.json | 10 条合成题录，含预埋缺陷（见下） |
| expected_states.json | selfcheck 断言用的逐条预期状态与 PRISMA 计数 |
| negative/broken_records.json | 故意截断损坏的 JSON（负例） |
| output/ | 脚本真实运行产物（case_summary.json、result.skeleton.json、corpus_report.json） |

## 埋雷设计（10 条记录）

| 记录 | 埋雷 | 预期 state |
|---|---|---|
| R01 | 无（干净） | verified |
| R02 | DOI `10.999/fake.x` 注册段仅 3 位，非法（V2） | suspicious |
| R03 | year=2089 超出合理区间（V3） | suspicious |
| R04 | 精确重复对的首条（保留） | verified |
| R05 | 与 R04 规范化 DOI 相同（带 https://doi.org/ 前缀，V4） | duplicate |
| R06 | 近似重复对的首条（保留） | verified |
| R07 | 标题与 R06 仅标点差异、不同一作（V5） | probable_duplicate |
| R08 | note 含 "RETRACTED"（V6） | retraction_flagged |
| R09 | title 为空串（V1） | invalid |
| R10 | 无（干净中文记录，演示 V7 语言打标） | verified |

说明：任务书原文称"3 条干净记录"，按 10 条总数自洽的实现为 4 条 verified
（2 条重复对首条 R04/R06 + 2 条纯干净 R01/R10），selfcheck 以此为准。

## 运行命令与预期退出码

```bash
SKILL=/path/to/bundle-a-corpus-verity   # 本目录的上一级
# 1) 案例解析 → exit 0
python3 $SKILL/scripts/parse_case.py --case $SKILL/examples/input/case.json \
  --task $SKILL/examples/input/task.md --out /tmp/case_summary.json
# 2) 保底骨架 → exit 0
python3 $SKILL/scripts/scaffold_result.py --summary /tmp/case_summary.json \
  --out /tmp/result.json
# 3) 语料核验（正常模式）→ exit 0（埋雷记录被隔离但流程通过）
python3 $SKILL/scripts/verify_corpus.py --records $SKILL/examples/input/records.json \
  --out /tmp/corpus_report.json
# 4) 严格模式 → exit 3（存在 invalid/suspicious/retraction_flagged）
python3 $SKILL/scripts/verify_corpus.py --records $SKILL/examples/input/records.json \
  --out /tmp/strict_report.json --strict
# 5) 损坏 JSON → exit 2（诚实降级）
python3 $SKILL/scripts/verify_corpus.py --records $SKILL/examples/negative/broken_records.json \
  --out /tmp/broken_report.json
# 6) 一键自检 → exit 0
python3 $SKILL/scripts/selfcheck
```

预期 PRISMA 计数：identified=10，duplicates_removed=2，quarantined=4，
clean_for_screening=4。
