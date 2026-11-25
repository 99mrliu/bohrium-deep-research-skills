# 示例走查（合成示例 / 示意输出）

> **合成示例声明**：本走查使用的全部记录、日期、号码均为虚构（见 `fixtures/` 各文件头注释），
> 仅用于演示管线与自检，不对应任何真实专利。下文所有输出均为**示意输出**，
> 为实际运行的真实结果（节选处已注明），路径中的 `$T` 为临时目录。

## 0. 准备

```bash
cd skill/                       # 评测环境中为 /skills/weekly-skill
T=$(mktemp -d)                  # 评测环境中使用 /app/work
```

案例夹具：`fixtures/case_fixture.json`（`case_id: SYN-CHRON-001`，含 output_contract 模板）。
记录：`rec_GX1001.txt`（多格式 + 歧义数字日期）、`rec_GX1002.txt`（OCR 错乱 + 顺序冲突）、
`rec_GX1003.txt`（GX1001 的观测同族，优先权日冲突）。

## 1. 单日期归一化（date_norm.py）

```bash
python3 scripts/date_norm.py "Jun. 5, 2018"
```
示意输出（退出码 0）：
```json
{"raw": "Jun. 5, 2018", "iso": "2018-06-05", "precision": "day",
 "format_tag": "us_long",
 "interpretations": [{"iso": "2018-06-05", "precision": "day", "format_tag": "us_long"}],
 "warnings": []}
```

```bash
python3 scripts/date_norm.py "03/04/2018"     # 歧义：两种解释 + 警告，退出码 0
```
```json
{"raw": "03/04/2018", "iso": "2018-03-04",
 "format_tag": "ambiguous:numeric_slash_eu_dmy+numeric_slash_us_mdy",
 "interpretations": [
   {"iso": "2018-03-04", "precision": "day", "format_tag": "numeric_slash_us_mdy"},
   {"iso": "2018-04-03", "precision": "day", "format_tag": "numeric_slash_eu_dmy"}],
 "warnings": ["AMBIGUOUS_NUMERIC_DATE: ..."]}
```

```bash
python3 scripts/date_norm.py "2O18-06-05"                                     # 退出码 1：保留原文
python3 scripts/date_norm.py "2O18-06-05" --ocr-policy fix-digit-confusion    # 退出码 0：声明式修复
```
```json
{"raw": "2O18-06-05", "iso": "2018-06-05", "format_tag": "ocr_fixed:iso8601",
 "warnings": ["OCR_DIGIT_CONFUSION_FIXED: ... 该修复仅为工作假设，须人工核对原件。"]}
```

## 2. 事件抽取（event_extract.py）

```bash
for r in GX1001 GX1002 GX1003; do
  python3 scripts/event_extract.py examples/fixtures/rec_$r.txt -o $T/$r.json
done
python3 scripts/event_extract.py examples/fixtures/rec_GX1002.txt \
    --ocr-policy fix-digit-confusion -o $T/GX1002_fix.json
```

`rec_GX1001` 事件一览（示意，退出码 0）：

| event | kind | raw | iso | format_tag |
| --- | --- | --- | --- | --- |
| evt-01 | priority | `Jun. 5, 2018` | 2018-06-05 | us_long |
| evt-02 | filing | `20190603` | 2019-06-03 | compact_yyyymmdd |
| evt-03 | publication | `2020-12-10` | 2020-12-10 | iso8601 |
| evt-04 | grant | `Apr. 12, 2022` | 2022-04-12 | us_long |
| evt-05 | **unknown** | `6/5/2018` | 2018-06-05 | ambiguous:numeric_slash_eu_dmy+numeric_slash_us_mdy |

evt-05 同时带有 `AMBIGUOUS_NUMERIC_DATE` 与 `UNKNOWN_EVENT_KIND` 警告，
并保留逐字 `quote` 与 `span`（如 `[586, 594]`）。

`rec_GX1002`（keep-raw）：`filing 2019年6月4日→2019-06-04`；`publication 2O2O-O6-15→iso=null`
（`UNPARSEABLE_DATE_KEPT_RAW` + `SUSPECTED_OCR_DIGIT_CONFUSION`）；`grant 2018-05-01`。
改用 `--ocr-policy fix-digit-confusion` 后，该公开日解析为 `2020-06-15`
（`ocr_fixed:iso8601` + `OCR_DIGIT_CONFUSION_FIXED`）。

## 3. 时间轴与顺序冲突（timeline_build.py）

```bash
python3 scripts/timeline_build.py --events $T/GX1001.json $T/GX1002.json -o $T/timelines.json
echo $?    # → 1：检出冲突（冲突已写入输出，属正常产出）
```

示意输出（节选）——GX1001 时间轴有序
`priority 2018-06-05 ≤ filing 2019-06-03 ≤ publication 2020-12-10 ≤ grant 2022-04-12`
（unknown 事件按日期放入但不参与冲突检测）；GX1002 检出：

```json
{"type": "order_violation", "record_id": "rec_GX1002",
 "expected": "filing <= grant",
 "observed": "filing(2019-06-04) 晚于 grant(2018-05-01)",
 "events": ["rec_GX1002-evt-01", "rec_GX1002-evt-03"],
 "resolution": "none — 未做任何静默修正，须人工回查来源原文。"}
```

OCR 错乱的公开日进入 `unplaced`（保留原文），不参与排序。

## 4. 观测同族优先权核查

```bash
python3 scripts/timeline_build.py --events $T/GX1001.json $T/GX1003.json --family -o $T/family.json
echo $?    # → 1：family_priority_conflict
```
```json
{"type": "family_priority_conflict",
 "distinct_priority_dates": ["2018-06-05", "2018-06-15"],
 "members": {"rec_GX1001": ["2018-06-05"], "rec_GX1003": ["2018-06-15"]},
 "resolution": "none — 未做任何静默取舍，须人工回查各成员原文。",
 "note": "观测链接不构成完整同族……本核查结论仅限所给观测成员，不外推。"}
```

## 5. 法定参考日期估算（护栏演示）

```bash
python3 scripts/term_estimate.py --request examples/fixtures/estimate_request.json -o $T/estimate.json
echo $?    # → 0
python3 scripts/term_estimate.py --earliest-filing 2019-06-03 --case-id X
echo $?    # → 1：ERROR: 必须显式声明 as_of……
python3 scripts/term_estimate.py --self-test
# → SELF-TEST PASS: estimate guardrails verified ...
```

`$T/estimate.json` 关键字段（示意，退出码 0）：

```json
{"case_id": "SYN-CHRON-001", "as_of": "2026-11-25",
 "is_estimate": true, "not_legal_status": true,
 "assumptions": ["保护期参考届满日以所给最早申请日为起算点按 20 年简单推算；……", "……"],
 "estimates": {
   "estimated_20y_term_end": {"value": "2039-06-03", "is_estimate": true, "not_legal_status": true},
   "us_maintenance_windows": [
     {"stage": "3.5y",  "window_open": "2025-04-12", "window_close": "2025-10-12"},
     {"stage": "7.5y",  "window_open": "2029-04-12", "window_close": "2029-10-12"},
     {"stage": "11.5y", "window_open": "2033-04-12", "window_close": "2033-10-12"}]},
 "warnings": ["official legal status unknown — 官方法律状态未知，本输出不断言任何状态。"]}
```

## 6. 汇总 result.json 骨架（评测环境纪律）

评测环境中应先写**诚实的部分骨架** `/app/output/result.json`（`status:"partial"`，
逐字段镜像 output_contract，未填为 `null` + uncertainty 说明），再随流水线推进
增量重写并追加 `change_records`。骨架示意：

```json
{"case_id": "SYN-CHRON-001", "status": "partial",
 "normalized_events": null, "timelines": null, "conflicts": null, "term_estimates": null,
 "sources": {}, "uncertainty": "骨架：流水线尚未运行；官方法律状态未知，须如实说明。",
 "change_records": [{"ts": "...", "change": "init skeleton"}]}
```

## 7. 自查

```bash
python3 scripts/selfcheck.py
# …
# SELFCHECK SUMMARY: 27/27 checks passed ...
```
