# 端到端演练（合成示例·虚构数据）

以下命令均在 skill 根目录真实执行；输出为真实粘贴，标记为**示意输出（合成示例）**。
夹具主题：虚构的"柔性锌空气电池"（3 篇虚构专利 + 2 篇虚构论文）。

工作目录约定：`W=/tmp/dtrl_walk`（先 `mkdir -p "$W"`）。

## 1. 校验合法 spec

```bash
python3 scripts/query_build.py validate --spec examples/fixtures/query_spec_valid.json
```

示意输出（合成示例）：

```
validate: OK（R1–R9 前置规则全部通过；R9 由 render 的确定性保证）
exit=0
```

## 2. 双轨渲染

```bash
python3 scripts/query_build.py render --spec examples/fixtures/query_spec_valid.json \
    --track patent --out "$W/q_patent.txt"
python3 scripts/query_build.py render --spec examples/fixtures/query_spec_valid.json \
    --track npl --out "$W/q_npl.txt"
```

示意输出（合成示例）——patent 轨（含 CLASS 过滤）：

```
render: 已写出 /tmp/dtrl_walk/q_patent.txt（track=patent，361 字符）
# dual-track-retrieval-lab 渲染输出（确定性：同一 spec 必得同一串）
# research_question: （虚构）2015 年以来柔性锌空气电池（凝胶/固态电解质方向）的专利与论文证据有哪些？
# track: patent
# exclusion reasons: 锂空气 ← 研究问题限定锌体系，锂空气为相邻但不同的技术路线，命中即排除以避免体系混淆
( "锌空气电池" OR "锌-空气电池" ) AND ( "柔性" OR "可穿戴" ) AND ( "金属空气电池" OR "H01M 12/06" ) AND CLASS IN ( "H01M 12/06" ) AND DATE IN [ 2015-01-01 .. 2026-12-31 ] NOT ( "锂空气" )
```

示意输出（合成示例）——npl 轨（stderr 出现 R5 的 NOTE，正文不含 CLASS）：

```
NOTE: classification_codes 在 npl 轨不生效，渲染时已丢弃: H01M 12/06
render: 已写出 /tmp/dtrl_walk/q_npl.txt（track=npl，387 字符）
# NOTE: classification_codes 在 npl 轨不生效，渲染时已丢弃: H01M 12/06
( "锌空气电池" OR "锌-空气电池" ) AND ( "柔性" OR "可穿戴" ) AND ( "金属空气电池" OR "H01M 12/06" ) AND DATE IN [ 2015-01-01 .. 2026-12-31 ] NOT ( "锂空气" )
```

## 3. 反面样例（退出码 2）

```bash
python3 scripts/query_build.py validate --spec examples/fixtures/query_spec_bad_bare_not.json
python3 scripts/query_build.py validate --spec examples/fixtures/query_spec_bad_no_intent.json
```

示意输出（合成示例）：

```
FAIL R4: 块「排除锂体系」使用裸 NOT 运算；排除仅允许经顶层 exclusion_terms 并附 reason
validate: 1 条违规
exit=2

FAIL R2: 块「电池体系」词项 '锌-空气电池' 的 intent 缺失或非法（须为 core/variant/classification/exclusion）
validate: 1 条违规
exit=2
```

## 4. 本地语料双轨执行

```bash
python3 scripts/corpus_search.py run --spec examples/fixtures/query_spec_valid.json \
    --roots examples/fixtures/corpus --out "$W/hits.json"
```

示意输出（合成示例）：

```
run: 扫描 5 个文件（跳过 0），原始命中 3，去重后记录 2，排除 1，未命中 1 → /tmp/dtrl_walk/hits.json
exit=0
```

要点解读（均在 hits.json 中可核对）：

- `pat_EX1001` 与 `pat_EX1002` 共享虚构同族号，合并为一条
  `FAM:EXFAM-2026-0001` 记录（`members` 含两者，各自带 file+line 定位）。
- `npl_EX2001` 按虚构 DOI 归并为 `DOI:10.9999/synth.2026.0001`。
- `pat_EX1003` 正文含排除词"锂空气" → 进入 `excluded_docs`（附行号与理由）。
- `npl_EX2002` 未覆盖"柔性特征"块 → 进入 `no_match_docs`（计入扫描分母）。

## 5. 筛选决策与 PRISMA 重算

```bash
cat > "$W/decisions.json" <<'EOF'
[
  {"doc_id": "FAM:EXFAM-2026-0001", "decision": "include",
   "reason": "直接公开柔性锌空气电池凝胶电解质方案"},
  {"doc_id": "DOI:10.9999/synth.2026.0001", "decision": "exclude",
   "reason": "综述性对照文献，不含可复用的柔性实施例数据"}
]
EOF
python3 scripts/prisma_screen.py screen --hits "$W/hits.json" \
    --decisions "$W/decisions.json" --out "$W/screened.json"
python3 scripts/prisma_screen.py report --screened "$W/screened.json" --out "$W/prisma.json"
```

示意输出（合成示例）：

```
screen: 2 条记录（include 1 / exclude 1）→ /tmp/dtrl_walk/screened.json
exit=0
report: identification(raw=3, dup_removed=1) screening(screened=2, excluded=1) included=1 → /tmp/dtrl_walk/prisma.json
exit=0
```

缺 decision 时（示意输出·合成示例）：

```
MISSING decision: DOI:10.9999/synth.2026.0001
screen 中止：1 条记录缺决策，0 条决策非法
exit=2
```

## 6. 自报计数对账（--claim）

```bash
# 篡改的计数 → 退出 3
echo '{"raw_hits": 3, "duplicates_removed": 0, "records_screened": 2, "included": 2, "excluded": 0}' \
    > "$W/claim_bad.json"
python3 scripts/prisma_screen.py report --screened "$W/screened.json" \
    --out "$W/prisma.json" --claim "$W/claim_bad.json"
```

示意输出（合成示例）：

```
MISMATCH: duplicates_removed: 自报 0 ≠ 重算 1
MISMATCH: included: 自报 2 ≠ 重算 1
MISMATCH: excluded: 自报 0 ≠ 重算 1
report 中止：自报计数与脚本重算不一致（exit 3）
exit=3
```

正确计数（`{"raw_hits": 3, "duplicates_removed": 1, "records_screened": 2,
"included": 1, "excluded": 1}`）则 `exit=0`，prisma.json 中记录
`claim_check: 通过：自报计数与重算一致`。

## 7. 结果骨架

```bash
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json --out "$W/out"
```

示意输出（合成示例）：

```
scaffold: case_id=SYNTH-EXAMPLE-003 status=partial → /tmp/dtrl_walk/out/result.json（仍为 null 的契约字段: research_question、query_log、candidates、screening、omissions_note）
exit=0
```

随后把检索式、候选、PRISMA 计数、遗漏说明写入 `fill.json`，用
`--fill fill.json --status ok` 合并回填。

## 8. 遗漏说明模板（report 自动生成）

示意输出（合成示例）：

```
遗漏说明（模板，请结合案例实际改写后填入 result.omissions_note）：
1. 召回范围：扫描 5 个文件；原始命中 3 条，去重后 2 条进入筛选。
2. 未覆盖概念块：无（所有块至少命中一篇）。
3. 零命中词项：无。
4. 查询层排除（命中排除词）1 篇；扫描但未覆盖全部概念块 1 篇。
5. 筛选层排除 1 条，按理由分布：综述性对照文献，不含可复用的柔性实施例数据×1。
6. 残余风险：字面词组匹配可能遗漏未列入词表的同义表述；如需扩充召回，请在 spec 中增补 variant 词项后重跑并记录变更。
```

## 9. 自查

```bash
python3 scripts/selfcheck.py
```

示意输出（合成示例）：22 项 `[PASS]`，末行
`selfcheck: 全部 22 项断言通过（exit 0）`。
