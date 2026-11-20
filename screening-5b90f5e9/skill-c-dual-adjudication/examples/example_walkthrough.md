# 合成示例走查（example_walkthrough）

> 本目录所有数据均为**合成虚构**：文献、DOI、作者、标注者 FX-A/FX-B 均不存在，
> 仅用于演示流程与格式，不代表真实文献或真实标注。

## 示例场景

- 9 条虚构题录（example_records.jsonl）：R02 是 R01 的精确重复导出（同 DOI/题名），
  R07 摘要为空，R08 为非英文记录，R09 仅会议摘要。
- 去重后 8 条进入筛选。
- 两位虚构标注者（fixture）在 R05（混合人群 → D1）、R06（是否读到未测 HbA1c 句 → D2）、
  R07（空摘要如何处理 → D3）上分歧；R09 双方一致 uncertain → 人工门。
- 预期终判：included=2（R01, R05），excluded=4（R03, R04, R06, R08），
  needs_human=2（R07, R09）；一致率 5/8=0.625。

## dual_model 模式走查

```bash
# 0. 准备模拟运行时目录
mkdir -p /tmp/demo/{input,work,output}
cp examples/example_case.json /tmp/demo/input/case.json
cp examples/example_records.jsonl /tmp/demo/input/records.jsonl
printf '# 任务\n对提供题录按研究问题完成纳排筛选。\n' > /tmp/demo/input/task.md
SKILL=/path/to/skill-c-dual-adjudication

# 1-3. 解析、骨架、导入、去重
python3 $SKILL/scripts/parse_case.py --input-dir /tmp/demo/input --work /tmp/demo/work
python3 $SKILL/scripts/scaffold_result.py --work /tmp/demo/work --output-dir /tmp/demo/output
python3 $SKILL/scripts/load_records.py --input-dir /tmp/demo/input --work /tmp/demo/work
python3 $SKILL/scripts/exact_dedup.py --work /tmp/demo/work   # identified=9 removed=1 screened=8

# 4. 生成两套互不可见空白表，模拟两次独立模型请求填表（此处用合成填写结果代替）
python3 $SKILL/scripts/prepare_sheets.py --work /tmp/demo/work
cp examples/filled_s1.jsonl /tmp/demo/work/annotations_s1.jsonl
cp examples/filled_s2.jsonl /tmp/demo/work/annotations_s2.jsonl
python3 $SKILL/scripts/validate_annotations.py --work /tmp/demo/work --sheet /tmp/demo/work/annotations_s1.jsonl
python3 $SKILL/scripts/validate_annotations.py --work /tmp/demo/work --sheet /tmp/demo/work/annotations_s2.jsonl

# 5. 一致性与分歧
python3 $SKILL/scripts/agreement.py --work /tmp/demo/work   # disagree=3, kappa_3class≈0.3333, kappa_binary≈0.3846

# 6. 仲裁（模型一次批量请求；此处用合成仲裁记录代替）
cp examples/filled_arbitrations.json /tmp/demo/work/arbitrations.json
python3 $SKILL/scripts/adjudicate.py --work /tmp/demo/work  # include=2 exclude=4 needs_human=2

# 7-8. 审计链、填充 result.json、终检
python3 $SKILL/scripts/audit_log.py --work /tmp/demo/work
# （按 SKILL.md 第 4 节映射表填充 /tmp/demo/output/result.json）
python3 $SKILL/scripts/selfcheck.py --work /tmp/demo/work --output-dir /tmp/demo/output
```

## dual_fixture 模式走查

在第 0 步额外放入 fixture：

```bash
cp examples/example_fixture_annotations.json /tmp/demo/input/fixture_annotations.json
```

- parse_case 判定 mode=dual_fixture；
- load_records 旁路保存 external_annotations.json（fixture 原样 + 输入 fixture 声明）；
- prepare_sheets 直接把 fixture 两组标注转换为 annotations_s1/s2.jsonl
  （带 source=external_fixture；R02 标注因记录被去重而丢弃并写 fixture_dropped.json）；
- 后续 validate → agreement → adjudicate → audit → selfcheck 与上相同。
- 注意：fixture 两组标注是**输入材料**，不是金标准；分歧仍需 D1–D4 分类并仲裁。

## 故意失败演示（验证 exit 3）

- 把 annotations_s1.jsonl 某条 evidence_quote 改成摘要中不存在的文字
  → validate_annotations exit 3 并写 validation_errors_annotations_s1.json；
- 从 arbitrations.json 删掉一条 → adjudicate exit 3 并写 adjudication_errors.json；
- 修复后重跑即 exit 0（幂等）。

完整自测命令与退出码记录见 examples/selftest_log.md。
