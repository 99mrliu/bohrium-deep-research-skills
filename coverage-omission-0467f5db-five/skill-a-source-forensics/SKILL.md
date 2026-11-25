---
name: source-forensics-denominator
description: 参考集上游数据真实性取证技能。用于"检索覆盖率与遗漏分析"类任务：先对全部输入材料建立 SHA-256 监管链（authenticity_manifest.json），再以案例本地留存的 Crossref/EuropePMC/出版商响应文件为唯一真值源逐条核验参考题录，处置撤稿、标识符冲突、重复与无全文记录，冻结带内容哈希的版本化分母，然后完成"算覆盖—列漏检—做补检"闭环。当任务包含综述参考文献、专家清单、留存 API 响应或参考图谱且需要可信覆盖率分母时使用。边界：不以检索结果并集充当分母，不做实时覆盖度或新颖性声明，不臆造本地响应中不存在的核验结论。
---

# 参考集上游数据真实性取证（source-forensics-denominator）

## 重心与适用条件

本技能的重心是**上游数据真实性**：覆盖率的常见造假点不在计算而在分母——题录可能撤稿、标识符可能张冠李戴、综述参考文献本身可能抄错。本技能在任何覆盖测量之前先建立证据链：

1. **监管链**：对每份输入材料计算 SHA-256 与字节数，生成 `authenticity_manifest.json`（含整体 manifest 哈希），后续所有证据指针都落到带哈希的文件上；
2. **真值源限定**：核验只使用案例本地留存的 Crossref / EuropePMC / 出版商响应文件（`references/truth_source_policy.md`），本地没有响应的记录标记 `unverified_no_local_response`，**绝不**凭印象补造核验结论，也不发起实时远程核验；
3. **逐条处置**：撤稿 `exclude_retracted`、标识符冲突 `identifier_conflict`、重复合并（台账记录）、无全文 `flag_keep_no_fulltext`、核验不足 `flag_keep_unverified`；
4. **冻结分母**：输出 `reference_set.json`（v1.0.0 + content_sha256），冻结后改动必须进 `change_log`。

随后用同一脚本完成闭环：覆盖测量（L1 标识符 / L2 标题+年份）、逐条漏检归因（查询词/字段/时间窗/来源/标识符五类探针）、定向补检建议、`result.json` 组装。

## 运行环境

- 输入：`/input/case.json` 与 `/task.md`；材料在 `/input` 下递归扫描。
- 工作目录 `/app/work`；交付物 `/app/output`。
- Python 3 标准库，零第三方依赖，不 pip install，默认不联网。
- 预算：≤64 次模型请求、≤900 秒；大多数阶段一次脚本调用即可完成，模型请求主要用于阅读本说明与核对产物。

## 调用方式（依序执行）

```bash
python3 /skills/weekly-skill/scripts/forensics_pipeline.py \
  --input /input --work /app/work --output /app/output
```

单条命令跑完全部阶段。退出码：`0` 完成；`2` 材料不足（诚实 partial，产物仍交付）；`3` result.json 缺 output_contract 字段（需人工查看 `/app/work` 日志）。技能脚本在其它安装路径下时相应替换前缀；先 `ls /skills/weekly-skill/scripts/` 确认。

## 产物（/app/output 与 /app/work）

| 产物 | 位置 | 内容 |
|---|---|---|
| result.json | /app/output | case_id、output_contract 全部字段、status、sources、uncertainty、change_log |
| reference_set.json | /app/output | 冻结参考集 v1.0.0：逐条 origin 指针、verification_status/source、disposition |
| coverage_report.md | /app/output | 覆盖率口径、逐条命中状态表、漏检归因、局限 |
| authenticity_manifest.json | /app/work | 全部输入材料的 SHA-256 监管链 |
| coverage.json / miss_attribution.json / supplement_log.json | /app/work | 机器可复算的中间台账 |

## result.json 契约

- `case_id` 与 case.json 一致；`output_contract` 声明的每个字段都出现（缺失填 null 并在 uncertainty 说明，绝不留空键）。
- `status`：complete / partial / failed，取全流程最弱环节。
- `coverage.denominator_source` 必须写明冻结参考集版本与内容哈希，供他人独立复算分母。
- `sources`：实际使用的每份材料路径 + SHA-256。
- `uncertainty`：仅凭标题近似匹配的记录、unverified 记录、单一渠道撤稿标记等。

## 异常处理

- 撤稿：本地响应含撤稿标记即 `usable=false` 并从分母排除，排除记录写入 exclusions；
- 标识符冲突：DOI/PMID 解析到的标题与原题录 Jaccard<0.5 时标记 `identifier_conflict`，不进入分母统计的可信命中；
- 重复：DOI/PMID 强键 + 标题相似度≥0.9 弱键合并，合并事件写 change_log，禁止静默丢弃；
- 材料缺失/解析失败：状态降 partial，change_log 记录事件，产物照常交付已有部分；
- 网络：默认不联网；本地无响应即 unverified。

## 最小调用示例（合成示例）

`examples/` 内含一组**合成**输入（12 条题录含 1 撤稿、1 重复、1 标识符冲突、1 无标识符；3 条查询的命中结果；2 份合成 Crossref/EuropePMC 响应）。运行：

```bash
python3 scripts/forensics_pipeline.py --input examples/input --work examples/run/work --output examples/run/output
cat examples/run/output/result.json
```

预期（合成示例，非正式案例结果）：分母 10 条（12 原始 −1 撤稿 −1 合并重复），命中 6，漏检 4，漏检分别归因到查询词缺失、时间窗截断、来源未覆盖、标识符异常四类。详见 examples/README.md。

## 自查方法

1. `result.json` 含 case_id 且 output_contract 字段齐全；
2. `coverage.denominator + excluded 数 = reference_set.json 记录数`；
3. 随机抽 1 条 miss，能在 miss_attribution.json 找到带证据的归因；
4. authenticity_manifest.json 中任一文件哈希可用 `shasum -a 256` 复算一致。
