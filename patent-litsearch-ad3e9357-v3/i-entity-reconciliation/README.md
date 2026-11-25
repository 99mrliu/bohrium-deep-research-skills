# bibliographic-entity-reconciler

著录实体消歧与跨源对账(bibliographic entity resolution & cross-source reconciliation)。

面向"专利与技术文献检索"场景中的**实体层**问题:专利记录的申请人/受让人/发明人,
与对比论文的作者/机构,在跨来源对账时写法不一(大小写、标点、法律后缀、人名语序)。
本技能提供确定性、可审计的流水线:**规范化留痕 → 分档匹配 → 重叠对账(逐字锚点)**。

GitHub: 见 `GITHUB_URL.txt`。

## 设计要点

- **一切转换留痕**:每条名称输出 `applied_rules[]`,每项为 `{rule, raw, normalized}`。
- **阈值/权重声明在 policy JSON**,脚本零硬编码;改 policy 即改判定。
- **三档判定**:auto / candidate(歧义带,永远列全备选与特征分解,绝不静默合并)/ non_match。
- **安全降级 flag**:`order_variant`(如 "Zhang Wei" vs "Wei Zhang")、`suffix_conflict`
  (如 "Globex Ltd." vs "Globex GmbH")强制落入 candidate。
- **对账锚点可验证**:`quote == text[span]` 且 `sha256` 为源文件字节哈希;缺失一侧为 `null`,绝不推断。

## 目录结构

```
skill/
├── SKILL.md                     # 技能定义(用途/运行时契约/调用/异常/限制/自查)
├── README.md
├── GITHUB_URL.txt
├── scripts/                     # 纯 Python3 标准库;退出码 0 ok / 1 violation / 2 usage
│   ├── name_norm.py             # 规范化流水线 + 规则审计(R1..R5)
│   ├── entity_match.py          # blocking + 多特征打分 + 三档判定
│   ├── cross_ledger.py          # patent↔paper 重叠对账表(逐字锚点)
│   └── selfcheck.py             # 合成夹具自检(15 项断言,exit 0)
├── references/
│   ├── normalization_rules.md   # 规则目录 R1..R5 与匹配 flag 说明
│   ├── legal_suffix_table.json  # 法律后缀映射表(39 条,含法域注记)
│   ├── match_policy.md          # 三档、阈值、candidate 档存在的理由
│   └── transliteration_notes.md # CJK/罗马化姓名的边界(无佐证不静默等同)
└── examples/
    ├── example_walkthrough.md   # 合成示例 + 示意输出
    └── fixtures/                # 全部为合成数据,文件头已声明
        ├── case_fixture.json
        ├── rec_IX1001.txt  rec_IX1002.txt  paper_PX2001.txt
        ├── entities_patent.json  entities_paper.json
        └── match_policy.json
```

## 快速开始

```bash
python3 scripts/selfcheck.py   # 自检,应 exit 0

# 端到端示例(合成数据)
W=$(mktemp -d)
python3 scripts/name_norm.py --suffix-table references/legal_suffix_table.json \
  --input examples/fixtures/entities_patent.json --output $W/pat_norm.json
python3 scripts/name_norm.py --suffix-table references/legal_suffix_table.json \
  --input examples/fixtures/entities_paper.json --output $W/pap_norm.json
python3 scripts/entity_match.py --left $W/pat_norm.json --right $W/pap_norm.json \
  --policy examples/fixtures/match_policy.json --output $W/match_report.json
python3 scripts/cross_ledger.py --left $W/pat_norm.json --right $W/pap_norm.json \
  --left-sources examples/fixtures/rec_IX1001.txt examples/fixtures/rec_IX1002.txt \
  --right-sources examples/fixtures/paper_PX2001.txt \
  --policy examples/fixtures/match_policy.json --output $W/ledger.json
```

详细说明见 `SKILL.md` 与 `examples/example_walkthrough.md`。
