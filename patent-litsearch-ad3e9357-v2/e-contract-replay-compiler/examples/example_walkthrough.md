# 走查示例：从 case.json 到可交付复核报告

以下命令均真实执行过；所贴输出为**示意输出（合成示例）**——fixtures 中的所有对象、号码、来源均为虚构。工作目录为 skill 根目录，产物写到 `/tmp/rcrc-walkthrough`。

## 0. 准备

```bash
cd /path/to/skill
W=/tmp/rcrc-walkthrough; mkdir -p "$W"
```

## 1. 脚手架：诚实 partial 立即落地

```bash
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json \
    --out "$W/output" --note "初始脚手架：契约镜像，诚实 partial"
```

示意输出（合成示例）：

```
[完成] result.json 已写入: /tmp/rcrc-walkthrough/output/result.json
  case_id        : SYNTH-EXAMPLE-005
  status         : partial
  契约字段数     : 7（仍为 null: 4）
  uncertainty    : 4 条
  change_records : 1 条
```

## 2. 合并一批填充

```bash
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json \
    --out "$W/output" --fill examples/fixtures/fill.json \
    --note "合并 fill.json：填入 1 条候选与 1 条来源（合成示例）"
```

示意输出（合成示例）：

```
[信息] 复用既有结果文件: /tmp/rcrc-walkthrough/output/result.json
[完成] result.json 已写入: /tmp/rcrc-walkthrough/output/result.json
  case_id        : SYNTH-EXAMPLE-005
  status         : partial
  契约字段数     : 7（仍为 null: 3）
  uncertainty    : 3 条
  change_records : 2 条
```

此时的 result.json（示意输出，合成示例，节选）：

```json
{
  "case_id": "SYNTH-EXAMPLE-005",
  "status": "partial",
  "sources": [
    {"name": "虚构专利检索库（合成示例）", "version": "v0.0-fixture", "query_date": "2026-11-24"}
  ],
  "uncertainty": [
    "evidence_records: 未填写（脚手架初始化为 null，待补）",
    "legal_status: 未填写（脚手架初始化为 null，待补）",
    "omissions_note: 未填写（脚手架初始化为 null，待补）"
  ],
  "change_records": [
    {"ts": "2026-11-24T08:40:07Z", "note": "初始脚手架：契约镜像，诚实 partial"},
    {"ts": "2026-11-24T08:40:07Z", "note": "合并 fill.json：填入 1 条候选与 1 条来源（合成示例）"}
  ],
  "candidates": [
    {"name": "虚构装置甲（合成示例）", "pub_no": "CN000000000A",
     "evidence": ["fixture://synthetic/doc1#para-0007", "fixture://synthetic/doc1#claim-1"]}
  ],
  "evidence_records": null,
  "legal_status": null,
  "omissions_note": null
}
```

## 3. 契约校验（好结果，exit 0）

```bash
python3 scripts/contract_validate.py --case examples/fixtures/case_fixture.json \
    --result "$W/output/result.json" --out "$W/output/validate_report.json"
```

示意输出（合成示例）：

```
[V1 通过] case_id 一致性
    - case_id = SYNTH-EXAMPLE-005
[V2 通过] 契约字段齐备
    - 7 个契约字段均在顶层且标注一致
[V3 通过] status 合法且自洽
    - status=partial 与字段填充情况一致
[V4 通过] 来源记录完整
    - 1 条来源记录均含 name 与日期
[V5 通过] 编造标记检查
    - 未发现空证据候选或编造标记
[V6 通过] 变更记录非空
    - change_records 共 2 条
[总体] 通过，报告: /tmp/rcrc-walkthrough/output/validate_report.json
```

## 4. 反例一：缺失契约字段（exit 1，V2 fail）

```bash
python3 scripts/contract_validate.py --case examples/fixtures/case_fixture.json \
    --result examples/fixtures/result_bad_missing_field.json \
    --out "$W/validate_missing.json"   # 退出码 1
```

示意输出（合成示例，节选）：

```
[V2 失败] 契约字段齐备
    - 缺失契约字段: omissions_note
[总体] 存在失败规则，报告: /tmp/rcrc-walkthrough/validate_missing.json
```

## 5. 反例二：过度声明（exit 1，V3 fail）

```bash
python3 scripts/contract_validate.py --case examples/fixtures/case_fixture.json \
    --result examples/fixtures/result_bad_overclaim.json \
    --out "$W/validate_overclaim.json"   # 退出码 1
```

示意输出（合成示例，节选）：

```
[V2 失败] 契约字段齐备
    - 字段为 null 但未列入 uncertainty: legal_status
[V3 失败] status 合法且自洽
    - status=ok 但以下契约字段仍为 null（过度声明）: legal_status
[总体] 存在失败规则，报告: /tmp/rcrc-walkthrough/validate_overclaim.json
```

## 6. 运行日志 → manifest → 复跑核验

```bash
python3 scripts/replay_pack.py log --runlog "$W/run_log.jsonl" \
  --cmd "scaffold_result.py --case case_fixture.json --fill fill.json --out output" \
  --inputs examples/fixtures/case_fixture.json examples/fixtures/fill.json \
  --outputs "$W/output/result.json" --workdir "$W"

python3 scripts/replay_pack.py log --runlog "$W/run_log.jsonl" \
  --cmd "contract_validate.py --case case_fixture.json --result output/result.json" \
  --inputs "$W/output/result.json" --outputs "$W/output/validate_report.json" --workdir "$W"

python3 scripts/replay_pack.py pack --runlog "$W/run_log.jsonl" --out "$W/replay_manifest.json"
python3 scripts/replay_pack.py verify --manifest "$W/replay_manifest.json"
```

示意输出（合成示例）：

```
[完成] replay manifest 已写入: /tmp/rcrc-walkthrough/replay_manifest.json（2 个步骤）
[verify] manifest 生成于 2026-11-24T08:40:33Z，共 2 步
  步骤 1: fresh（可复跑，文件未变化）
    cmd: scaffold_result.py --case case_fixture.json --fill fill.json --out output
  步骤 2: fresh（可复跑，文件未变化）
    cmd: contract_validate.py --case case_fixture.json --result output/result.json
[汇总] fresh=2 stale=0 missing-input=0
```

若此后改动任一输入文件，再次 verify 时对应步骤标 `stale（文件已变化，重放结果可能不同）`；输入文件被删除则标 `missing-input` 且 verify 退出码为 1。

## 7. 渲染复核报告 + 最终校验

```bash
python3 scripts/report_render.py --result "$W/output/result.json" \
    --manifest "$W/replay_manifest.json" --out "$W/review.md"
python3 scripts/contract_validate.py --case examples/fixtures/case_fixture.json \
    --result "$W/output/result.json" --out "$W/output/validate_final.json"
```

生成的 `review.md` 含六个章节：案例标识与状态 / 主结果表 / 来源清单 / 不确定性与未完成项 / 变更记录 / 可复跑性（逐步骤 fresh/stale）。示意输出（合成示例，节选）：

```markdown
# 复核报告

## 案例标识与状态
- **case_id**: `SYNTH-EXAMPLE-005`
- **交付状态**: **partial**

## 主结果表
| name | pub_no | evidence |
| --- | --- | --- |
| 虚构装置甲（合成示例） | CN000000000A | fixture://synthetic/doc1#para-0007<br>fixture://synthetic/doc1#claim-1 |

## 可复跑性
| 步骤 | 命令 | 输入 | 输出 | 复跑状态 |
| --- | --- | --- | --- | --- |
| 1 | scaffold_result.py --case case_fixture.json --fill fill.json --out output | 2 个 | 1 个 | fresh（未变化，可复跑） |
```

## 8. 端到端自检

```bash
python3 scripts/selfcheck.py   # 37 项断言，全部 PASS，退出码 0
```
