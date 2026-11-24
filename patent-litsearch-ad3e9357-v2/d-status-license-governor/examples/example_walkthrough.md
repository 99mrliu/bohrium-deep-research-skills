# 示例走查（合成示例 / 虚构）

以下命令均在 bundle 根目录（`skill/`）下真实执行；输出为**示意输出（合成示例）**，全部专利号、来源、域名均为虚构。

## 0. 端到端自查

```bash
python3 scripts/selfcheck.py
```

示意输出（合成示例）：

```
PASS: status_ok.jsonl 校验通过（rc=0） — rc=0
...（共 21 项，见 README）...
自查合计: 21 项，通过 21，失败 0
全部断言通过。
```

## 1. 骨架先行（scaffold）

```bash
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json --out /tmp/walk/output
```

示意输出（合成示例）：

```
[scaffold_result] 骨架已生成: /tmp/walk/output/result.json（status=partial，契约字段 10 个）
```

生成的 `result.json`（节选）：

```json
{
  "case_id": "SYNTH-EXAMPLE-004",
  "status": "partial",
  "legal_status": null,
  "license_report": null,
  "degradation_plan": null,
  "conflicts": null,
  "wording_check": null,
  "sources": [],
  "uncertainty": [
    "骨架先行：各契约字段待填充；任何未核验字段不得编造，法律状态未核验时一律声明 unknown。"
  ],
  "change_records": [
    {
      "ts": "2026-11-24T08:41:52+00:00",
      "action": "scaffold",
      "note": "预算纪律：先交付诚实 partial 骨架，再在剩余预算内逐字段改进。"
    }
  ]
}
```

## 2. 来源授权分级与能力降级（classify + plan）

```bash
python3 scripts/license_tiers.py classify --sources examples/fixtures/sources.json --out /tmp/walk/license_report.json
python3 scripts/license_tiers.py plan --sources examples/fixtures/sources.json --out /tmp/walk/degradation_plan.json
```

示意输出（合成示例）：

```
[license_tiers classify] 绿=2 黄=2 红=1 → /tmp/walk/license_report.json
[license_tiers plan] 降级规则 3 条，checklist 6 项 → /tmp/walk/degradation_plan.json
```

`license_report.json` 的分级结论（节选）：两个公开官方来源（登记簿、公报）为绿；聚合站（注册+字段级）与转载博客（仅引述）为黄；付费商业库（paid+禁止展示）为红：

```json
{"source_id": "PAID-GLOBALDB-FICT", "color": "red",
 "reason": "access='paid', display_scope='none'：付费/受限/登录墙或禁止展示，禁止抓取与原文展示"}
```

`degradation_plan.json` 中红级来源的降级规则：

```json
{"source_id": "PAID-GLOBALDB-FICT", "color": "red", "rule": "do_not_fetch",
 "action": "不抓取、不登录、不绕过付费墙/登录墙；仅在结果中声明该来源存在，并标注「无法访问」；不得展示、转述其任何受限原文。",
 "allowed_display": "none", "result_marker": "无法访问"}
```

## 3. 台账校验：合法台账（含诚实的 unknown）

```bash
python3 scripts/status_ledger.py validate --ledger examples/fixtures/status_ok.jsonl --sources examples/fixtures/sources.json --today 2026-11-24
```

示意输出（合成示例，节选；退出码 0）：

```json
{
  "ok": true,
  "violations": [],
  "headline_statuses": {
    "CN-FICT-100001A": {"status": "granted", "tier": "register", "conflict_disclosed": false},
    "CN-FICT-100002B": {"status": "expired", "tier": "official_gazette", "conflict_disclosed": false},
    "CN-FICT-100003C": {"status": "unknown", "tier": "aggregation", "conflict_disclosed": false}
  }
}
```

注意第三行：聚合页只能支撑 `unknown`，这是被协议接受的一等公民结论。

## 4. 台账校验：把聚合页当登记依据（S1 违规）

```bash
python3 scripts/status_ledger.py validate --ledger examples/fixtures/status_bad_aggregator.jsonl --sources examples/fixtures/sources.json --today 2026-11-24
```

示意输出（合成示例，节选；退出码 1）：

```json
{
  "ok": false,
  "violations": [
    {"rule": "S1", "line": 1, "patent_ref": "CN-FICT-200001A",
     "message": "来源 AGG-PATENTLENS-FICT 的 tier=aggregation，aggregation/repost/unknown 级来源只能支撑 'unknown'（未核验）声明，不得断言 'granted'"}
  ]
}
```

## 5. 台账校验：缺查询日期 + 非 ISO 生效日（S2 + S6）

```bash
python3 scripts/status_ledger.py validate --ledger examples/fixtures/status_bad_unknown.jsonl --sources examples/fixtures/sources.json --today 2026-11-24
```

示意输出（合成示例，节选；退出码 1）：

```json
{
  "ok": false,
  "violations": [
    {"rule": "S2", "line": 1, "patent_ref": "CN-FICT-300001A",
     "message": "缺少 query_date 或格式非法: None（每条断言必须带查询日期）"},
    {"rule": "S6", "line": 2, "patent_ref": "CN-FICT-300002B",
     "message": "status_effective_date='去年六月' 不是 ISO YYYY-MM-DD，也不是显式 null"}
  ]
}
```

## 6. 措辞守门：通过与被拦截

```bash
python3 scripts/wording_guard.py --conclusions examples/fixtures/conclusions_ok.md --ledger examples/fixtures/status_ok.jsonl --sources examples/fixtures/sources.json --out /tmp/walk/wg_ok.json
```

示意输出（合成示例，节选；退出码 0）：

```json
{"ok": true, "violations": [],
 "ledger_refs": {"CN-FICT-100003C": "unverified_or_unknown"}}
```

```bash
python3 scripts/wording_guard.py --conclusions examples/fixtures/conclusions_bad_wording.md --ledger examples/fixtures/status_ok.jsonl --sources examples/fixtures/sources.json --out /tmp/walk/wg_bad.json
```

示意输出（合成示例，节选；退出码 1，含行号）：

```json
{
  "ok": false,
  "violations": [
    {"line": 3, "phrase": "自由实施", "kind": "fto_out_of_scope",
     "text": "- CN-FICT-100003C 是有效专利，该专利仍有效，可自由实施。"},
    {"line": 3, "phrase": "有效专利", "kind": "definitive_on_unverified"},
    {"line": 3, "phrase": "仍有效", "kind": "definitive_on_unverified"},
    {"line": 4, "phrase": "不构成侵权", "kind": "fto_out_of_scope"},
    {"line": 4, "phrase": "可放心使用", "kind": "fto_out_of_scope"}
  ]
}
```

第 3 行对 unknown 状态的虚构专利使用确定性措辞并夹带 FTO 结论；第 4 行即使专利已经登记级核验，FTO/侵权结论仍一律越权禁止。

## 7. 冲突处置（登记级优先 + 双保留 + 披露）

对同一虚构专利，登记簿称 granted、公报称 expired（冲突用例由 `selfcheck.py` 临时构造）：

```json
"conflicts": [{
  "patent_ref": "CN-FICT-900001X",
  "assertions": [
    {"asserted_status": "granted", "source_id": "REG-CNIPA-FICT", "tier": "register"},
    {"asserted_status": "expired", "source_id": "GAZ-CN-FICT", "tier": "official_gazette"}
  ],
  "headline": {"asserted_status": "granted", "tier": "register"},
  "conflict_disclosed": true
}]
```

双方断言均保留，头条状态由登记级（register）来源胜出，冲突显式披露；校验退出码仍为 0。
