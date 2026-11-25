---
name: bibliographic-entity-reconciler
description: 当任务需要对专利著录实体(申请人/受让人/发明人)与对比论文实体(作者/机构)做确定性名称规范化留痕、分档匹配(auto/candidate/non-match)与跨源重叠对账(逐字引用锚点+置信档)时,使用本技能进行著录实体消歧与跨源对账。
---

# bibliographic-entity-reconciler — 著录实体消歧与跨源对账

## 用途与适用条件

本技能只做一件事:**著录实体的确定性消歧与跨源对账**。专利记录列出申请人/受让人/发明人;对比论文列出作者/机构。同一实体在两个来源中的写法往往不同(大小写、标点、法律后缀全简称、人名语序),本技能提供:

1. **确定性名称规范化,全程留痕**:每一次转换都记录为 `规则号 + raw → normalized`(大小写折叠 R2、标点剥离 R3、法律后缀规范化 R4 等;规则目录见 `references/normalization_rules.md`,后缀映射表见 `references/legal_suffix_table.json`)。人名语序按 family/given 处理并对 CJK 保持警觉:如 "Zhang Wei" 与 "Wei Zhang" 只标记为 order-variant 候选,**绝不静默等同**。
2. **确定性 blocking + 多特征打分**:规范化 token 键 blocking;特征含 exact-normalized、后缀剥离 core 相等、core 包含、token 集 Jaccard、首字母+姓。阈值与权重**全部声明在 policy JSON 中**,脚本内不硬编码。
3. **三档判定**:`auto`(≥high)、`candidate`(歧义带:永远连同全部备选与特征分解列出,**绝不静默合并**)、`non_match`(<low)。强制降级 flag:`order_variant`、`suffix_conflict`。
4. **跨源重叠对账表(ledger)**:patent↔paper(发明人 vs 作者、申请人 vs 机构)逐行对账,每行携带两侧**逐字引用锚点**(`path + sha256 + span + quote`)与置信档;缺失一侧(如未知机构)保持 `null`,**绝不推断**。

适用条件:输入为 UTF-8 文本/JSON;实体列表已抽取或可由你从源文件手工抽取;只需要实体级对账,不需要图像/版面/法律层面的分析。

## 运行时契约

- 评测方将本技能安装于 `/skills/weekly-skill`,运行官方 DeepSeek Harness,固定 3 个隐藏用例。
- 输入:`/input/case.json` + `/input/task.md` + 材料(6 条专利记录、3 份 USPTO 传真原件 PDF、对比论文;含号码/主题查询;源头定位的权利要求版本;官方法律状态未知——**如实声明**;观察到的链接并非完整专利族;WO 合并 OCR 边界保留)。**必须读取真实文件内容,绝不从文件名推断。**
- 工作目录 `/app/work`;交付物 `/app/output/result.json`,必须包含:
  - `case_id`(**逐字照抄**);
  - 诚实的 `status`(`ok`/`partial`/`failed`);
  - `sources`(每个来源:path + sha256);
  - `uncertainty`;
  - `change_records`;
  - **镜像 output_contract 的全部字段**(未填字段 → `null` + uncertainty 说明)。
- 预算:64 次请求 / 900 秒 / 16384 tokens。**先交付诚实的部分骨架(partial skeleton),再逐步改进**,每次改进追加 `change_records` 条目。
- **绝不编造**;部分结果必须指明其局限。

## 调用方式(有序流水线)

以下命令以技能根目录为基准(评测时为 `/skills/weekly-skill`):

```bash
cd /skills/weekly-skill

# 第 0 步:自检(可选但强烈建议先跑,确认环境可用)
python3 scripts/selfcheck.py

# 第 1 步:规范化两侧实体列表(输入为 JSON 列表:字符串或含 "raw" 字段的对象)
python3 scripts/name_norm.py \
  --suffix-table references/legal_suffix_table.json \
  --input /app/work/entities_patent_raw.json \
  --output /app/work/entities_patent_norm.json
python3 scripts/name_norm.py \
  --suffix-table references/legal_suffix_table.json \
  --input /app/work/entities_paper_raw.json \
  --output /app/work/entities_paper_norm.json

# 第 2 步:分档匹配(阈值/权重来自 policy JSON)
python3 scripts/entity_match.py \
  --left /app/work/entities_patent_norm.json \
  --right /app/work/entities_paper_norm.json \
  --policy /app/work/match_policy.json \
  --output /app/work/match_report.json

# 第 3 步:跨源重叠对账表(带逐字锚点;源文件为真实读取的文本)
python3 scripts/cross_ledger.py \
  --left /app/work/entities_patent_norm.json \
  --right /app/work/entities_paper_norm.json \
  --left-sources /app/work/src/patent_1.txt /app/work/src/patent_2.txt \
  --right-sources /app/work/src/paper_1.txt \
  --policy /app/work/match_policy.json \
  --output /app/work/ledger.json
```

policy JSON 的最小形状(示例见 `examples/fixtures/match_policy.json`):

```json
{"thresholds": {"high": 0.9, "low": 0.2},
 "weights": {"exact_norm": 0.4, "core_eq": 0.15, "core_containment": 0.15,
             "token_jaccard": 0.1, "initial_surname": 0.2}}
```

## 输入输出解释

- `name_norm.py` 输入:JSON 列表(字符串或含 `raw` 的对象;其余字段原样透传)。输出:`{"count", "names":[...]}`,每条含 `raw / normalized / applied_rules[] / kind(org|person|unknown) / basis / tokens / core_tokens / core / canonical_suffix / cjk`。
- `entity_match.py` 输入:两侧 `name_norm.py` 产物 + policy JSON。输出 `match_report.json`:`policy`(回显)、`auto_matches[]`、`candidate_pairs[]`(按左侧实体分组,`alternatives[]` 含每个备选的 score、五维 features、flags)、`non_matches[]`(双侧)、`statistics`(由脚本重新统计)。
- `cross_ledger.py` 输入:两侧规范化实体 + 源文件路径列表 + policy JSON。输出 `ledger.json`:每个左侧实体一行——`entity_raw / role / band / matched_counterpart_raw(或 null)/ score / features / flags / alternatives / requires_review / anchors{left,right}`;锚点 `quote` 恒等于源文件文本的 `span` 切片,`sha256` 为文件字节哈希;另含 `unmatched_right_entities` 与 `statistics`。
- 退出码约定:**0 正常;1 数据违规;2 用法错误**(所有脚本一致)。

## 异常处理

- **空实体列表**:合法输入。`name_norm.py` 输出空结果并向 stderr 打印 warning,退出 0;下游 `entity_match.py`/`cross_ledger.py` 将全部实体记为 non-match(对账行 counterpart 为 `null`),退出 0。
- **全部不匹配(all-unmatched)**:非错误。报告/账本正常产出,`auto_matches` 为空、`non_matches` 为全集,退出 0;在 result.json 的 `uncertainty` 中如实说明。
- **policy 文件缺失或源文件/后缀表缺失**:退出 **2**,stderr 给出缺失路径。
- **输入非 UTF-8 JSON、实体条目缺少规范化字段(未先跑 name_norm)、policy 阈值非法(high≤low、权重引用未知特征)**:退出 **1**。
- **锚点找不到**:实体原文未逐字出现在任何源文件中 → 该侧锚点为 `null`,**不得**用近似串顶替。

## 限制

本技能**不做**以下事项(须如实声明,不得越界输出):

- 不做 **PDF 取证**(版面、印章、扫描质量、OCR 置信度分析);
- 不做 **日期时间线/优先权 chronology** 推理;
- 不做 **权利要求逐条 diff**(claim diffing);
- 不做 **检索式/查询设计**(retrieval query design);
- 不做 **法律状态** 判定(官方法律状态未知时如实声明)。

其他固有限制:

- 人名 order-variant 仅标记为 candidate;是否同一人需要外部佐证(见 `references/transliteration_notes.md`),罗马化 CJK 姓名在无佐证时绝不静默等同。
- `initial_surname` 等特征只提供候选信号;"P. Nair" 是否即 "Priya Nair" 由 candidate 档交人审。
- blocking 基于规范化 token;两侧零 token 交集的实体对不会被评分,直接 non-match。
- 仅标准库,确定性输出;同输入必同输出。

## 自查方法

1. 运行 `python3 scripts/selfcheck.py`,应退出 0 并打印全部 PASS 摘要。该自检断言:"Acme, Inc." ≡ "ACME INCORPORATED" 落在 auto 档;"Globex Ltd." vs "Globex GmbH" 为 candidate 且记录 `suffix_conflict`;"Zhang Wei" vs "Wei Zhang" 为 candidate 且记录 `order_variant`(绝不 auto);明显不匹配者保持 unmatched;ledger 锚点为源文件逐字子串(并含伪造锚点必失败的反向断言);阈值确实从 policy JSON 加载(篡改阈值后判定随之改变)。
2. 对照 `examples/example_walkthrough.md` 手工重跑一遍流水线,核对 `match_report.json` 与 `ledger.json` 与文中示意一致。
3. 抽查任一锚点:重新计算文件 sha256、按 span 切片,应逐字等于 `quote`。
