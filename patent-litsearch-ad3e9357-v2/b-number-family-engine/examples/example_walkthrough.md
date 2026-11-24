# 端到端示例（合成示例 / 虚构数据）

以下命令均在 `skill/` 目录下真实执行过；输出为**示意输出（合成示例）**，
fixture 中所有号码与文献均为虚构（合成测试国别码 XX），不对应任何真实
专利。其中 `US 10,293,847 B2` 等真实格式仅用于格式解析演示。

## 1. 号码规范化（合法 / 歧义 / 非法）

```
$ python3 scripts/patent_numbers.py normalize "US 10,293,847 B2" "WO2019/123456 A1" "16123456" "NOT_A_NUMBER"
```

示意输出（合成示例，节选）：

```json
[
  {
    "input": "US 10,293,847 B2",
    "ok": true,
    "normalized": "US10293847B2",
    "kind": "grant",
    "country": "US",
    "number": "10293847",
    "kind_code": "B2",
    "warnings": [],
    "alternatives": []
  },
  {
    "input": "16123456",
    "ok": true,
    "normalized": "US16123456",
    "kind": "grant",
    "country": "US",
    "warnings": [
      "缺少国别码：按 US 授权号主解读，需人工核对",
      "AMBIGUOUS 歧义：存在 2 种合法解读，主解读为 US16123456（grant/US）；未静默二选一，其余解读见 alternatives"
    ],
    "alternatives": [
      {"normalized": "US16123456", "kind": "application", "country": "US",
       "reason": "US 申请序列号解读", "warnings": ["缺少国别码"], "number": "16123456", "kind_code": null}
    ]
  },
  {
    "input": "NOT_A_NUMBER",
    "ok": false,
    "normalized": null,
    "warnings": ["无法解析：不猜测、不构造号码，原文保留并记入 uncertainty"]
  }
]
```

## 2. OCR 粘连切分（唯一边界 vs 多解）

```
$ python3 scripts/patent_numbers.py split "WO2019/123456US10293847B2" "123456789123456"
```

示意输出（合成示例，节选）：

```json
[
  {
    "input": "WO2019/123456US10293847B2",
    "ok": true,
    "boundary": 13,
    "split": [
      {"input": "WO2019/123456", "normalized": "WO2019123456", "kind": "publication",
       "warnings": ["缺少种类代码：按公开文本处理，需人工核对"]},
      {"input": "US10293847B2", "normalized": "US10293847B2", "kind": "grant", "warnings": []}
    ],
    "warnings": ["唯一合法边界切分（boundary=13）"]
  },
  {
    "input": "123456789123456",
    "ok": false,
    "split": null,
    "kept": "123456789123456",
    "warnings": ["歧义切分：2 个边界均合法（boundary=7,8），按唯一边界规则不拆分，原文保留"],
    "candidate_boundaries": [7, 8]
  }
]
```

## 3. 语料索引与种类容忍查询

```
$ python3 scripts/corpus_scan.py index --roots examples/fixtures/corpus --out /tmp/pfe_walk/index.json
索引完成：4 文件，16 号码条目，0 不可用

$ python3 scripts/corpus_scan.py query --index /tmp/pfe_walk/index.json \
    --numbers "XX1000001B2" --keywords "示例催化剂ZX-1" --out /tmp/pfe_walk/hits.json
查询完成：1 号码，2 精确命中
```

示意输出（合成示例，整理后）：查询 `XX1000001B2`（授权号）——

```json
{
  "normalized": "XX1000001B2",
  "hits": [
    {"file": "rec_EX1001.txt", "line": 5, "raw": "XX1000001B2"},
    {"file": "rec_EX2001.txt", "line": 6, "raw": "XX1000001B2"}
  ],
  "related_hits": [
    {"file": "rec_EX1001.txt", "line": 4, "normalized": "XX1000001A1",
     "note": "同国别同号码但种类/种类代码不同：需核对书目字段确认是否同一文献族成员"},
    {"file": "rec_EX1002.txt", "line": 10, "normalized": "XX1000001A1",
     "note": "同国别同号码但种类/种类代码不同：需核对书目字段确认是否同一文献族成员"}
  ]
}
```

注意：`rec_EX2001.txt` 是**非专利论文**，其命中须与专利记录区分处理
（不进入族合并的 priorities 来源）；`related_hits` 演示了授权号查询
同时召回同号公开号 A1。关键词 `示例催化剂ZX-1` 命中 5 处（字面包含，
仅召回）。

## 4. 双口径族合并

先构造 records.json（真实案例中由命中上下文提取，此处直接给出）：

```
$ python3 - <<'EOF'
import json
records = [
  {"record_id": "EX1001", "numbers": ["XX1000001A1", "XX1000001B2"],
   "priorities": ["XX2018/000001", "XX2018/000002"],
   "source_locator": "examples/fixtures/corpus/rec_EX1001.txt"},
  {"record_id": "EX1002", "numbers": ["XX1000002A1", "XX1000002B2"],
   "priorities": ["XX2018/000002", "XX2018/000003"],
   "source_locator": "examples/fixtures/corpus/rec_EX1002.txt"},
  {"record_id": "EX1003", "numbers": ["XX1000003A1"],
   "priorities": ["XX2018/000003", "XX2018/000004"],
   "source_locator": "examples/fixtures/corpus/rec_EX1003.txt"},
  {"record_id": "EX2001", "numbers": ["XX1000001B2"], "priorities": [],
   "source_locator": "examples/fixtures/corpus/rec_EX2001.txt"}
]
json.dump(records, open("/tmp/pfe_walk/records.json", "w"), ensure_ascii=False, indent=2)
EOF

$ python3 scripts/family_merge.py --records /tmp/pfe_walk/records.json --out /tmp/pfe_walk/family.json
族合并完成：simple=3，extended=1，无优先权记录=1
```

示意输出（合成示例，整理后）：

```
simple:   SIMPLE-001=[EX1001]  SIMPLE-002=[EX1002]  SIMPLE-003=[EX1003]
extended: EXTENDED-001=[EX1001, EX1002, EX1003]
records_without_priorities: EX2001 — "族归属不确定，观察到的链接非完整同族"
```

三条专利记录通过链式共享优先权（…000002、…000003）构成 1 个扩展族，
但优先权集合两两不同，故分为 3 个简单族——两种口径差异清晰可见。

## 5. 骨架先行 + 增量填充

```
$ python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json --out /tmp/pfe_walk/output
已写出 /tmp/pfe_walk/output/result.json（status=partial）

$ python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json \
    --out /tmp/pfe_walk/output --fill /tmp/pfe_walk/fill.json --status partial
已写出 /tmp/pfe_walk/output/result.json（status=partial）
```

第一次运行即产出镜像 `case_fixture.json` 中 output_contract 的诚实骨架
（未填充字段为 null 且列入 uncertainty）；第二次深合并 fill.json 后，
`result.json` 含 `case_id=SYNTH-EXAMPLE-002`、`status=partial`、
`families={"simple_count": 3, "extended_count": 1, ...}`，
`change_records` 记录了每次操作。

## 6. 自查

```
$ python3 scripts/selfcheck.py
...
SELF-CHECK PASSED: 全部断言通过
```
（45 项断言，exit 0；完整输出见 README.md。）
