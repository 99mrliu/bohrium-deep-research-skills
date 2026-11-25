---
name: identity-reconciliation-court
description: 跨库文献去重与论文身份合并。当案例任务要求从多个文献数据库来源（Crossref/EuropePMC/OpenAlex/通用 JSON/JSONL/CSV）汇总语料、识别同一论文的预印本/会议版/期刊版/增补版版本谱系、处理同名不同文与同文不同名、交付带合并证据台账的干净候选清单时使用；输入 /input/case.json 与本地语料，输出 /app/output/result.json。
---

# Identity Reconciliation Court：跨库去重与论文身份合并

一条命令管线，三步跑完。第一步先做身份合并，第二步在合并后的实体图上扩展，第三步自查。

```bash
# 1) 解析语料 + 身份合并（产出 entities.jsonl / merge_ledger.json）
python3 scripts/identity_merge.py --roots /input --workdir /app/work

# 2) 实体图 1–2 层引用扩展 + 交付 result.json / merge_report.md
python3 scripts/run_case.py --case /input/case.json --workdir /app/work --out /app/output --layers 2

# 3) 自查：去重干净性 / 合并证据完整性 / 契约镜像（打印 ok=true/false，退出码 0=通过）
python3 scripts/audit_merge.py --case /input/case.json --workdir /app/work --out /app/output
```

## 运行契约（Harbor 契约）

- 原始输入：`/input/case.json`（含 `case_id`、`seed`、`output_contract`）与 `/input/task.md`；组织方材料可能在其子目录，由 `--roots` 递归发现（顺序：`--roots` > `/input` > `/app/work` > cwd）。
- 工作目录：`/app/work`；`identity_merge.py` 写入 `entities.jsonl` 与 `merge_ledger.json`；`run_case.py` 最终写入 `/app/output/result.json` 与 `/app/output/merge_report.md`。
- `result.json` 必须含 `case_id` 与 `output_contract` 的全部字段（逐字段镜像，不允许丢字段；填不了的字段给空值/空集合并写入 `uncertainty`）。脚本对未知契约字段自动填空并记 `uncertainty`，不会中断。
- 预算意识：全程零网络、零模型请求、秒级完成；Agent 只需按上面三条命令顺序调用，不要逐条手工整理文献。
- 诚实性：解析不出的引用目标保留为 stub（只带原始指针与 `{file, pointer}` 定位）；不补造作者/年份/标题；冲突、存疑、缺失写入 `status`/`uncertainty`。先存诚实 partial，再视自查结果迭代。

## 输入

- `case.json`：可为字符串/对象/列表形式的种子（DOI 或标题）；`output_contract` 为任意键集合，全部镜像进 `result.json`。
- 语料：`.json/.jsonl/.csv/.tsv/.bib`（`.edgelist` 登记来源但不产出记录）。识别 Crossref（`message.items`）、EuropePMC（`resultList.result`）、OpenAlex（`results`+`referenced_works`）、通用 JSON（`records/nodes/papers/items/data` 键或顶层列表/单条）。解析失败的文件记入来源注册表而不中断。

## 输出

- `/app/work/entities.jsonl`：每行一个合并后实体，含 `members`（每条成员记录的 `{file, pointer}` locator）、代表记录、版本谱系（`lineage`/`kind`）、冲突字段的 `merge_evidence`、`flags`（`version_chain` / `same_work_different_title` / `incomplete_record`）。
- `/app/work/merge_ledger.json`：合并台账——每组成员、成对打分、组件分、裁决理由、冲突字段、review_queue、distinct_same_title、same_work_different_title、来源注册表与统计。
- `/app/output/result.json`：`case_id` + `status`(ok/partial/failed) + `seed` + `candidates`（干净实体清单，含扩展层级）+ `edges`（含方向、`direction_restored`、来源定位）+ `merge_summary` + `sources` + `evidence_records` + `uncertainty` + `output_contract` 全字段镜像。
- `/app/output/merge_report.md`：人读合并台账（合并组明细、存疑队列、同名不同文、同文不同名、不确定性）。

## 关键方法（细节见 references/）

1. **Blocking**：DOI 规范化精确块；标题规范化（小写、去标点、去停用词、坍缩空白）前 40 字符块；第一作者姓+年份块。
2. **成对打分**：标题 token Jaccard 与包含度取大（含 0.50 权重）；作者姓集合 Jaccard（0.25）；年份差（0.10）；venue token Jaccard（0.10）；DOI 前缀类型信号（0.05）。作者完全矛盾时护栏压分。
3. **阈值裁决**：≥0.85 合并；0.6–0.85 存疑写入 `review_queue`（不自动合并）；<0.6 不合并。
4. **版本谱系**：preprint（DOI 前缀 10.48550/10.1101/10.2139 等、venue 含 arXiv/预印本、type=preprint）；conference（venue 含 proceedings/conference/workshop）；supplement（标题/relation 含 supplement/supp.）；journal（其余）。组合版本对组标 `version_chain`。
5. **特殊身份情形**：标题高度相似但作者/DOI 全不重叠 → `distinct_same_title`（同名不同文，绝不合并）；DOI 相同但标题差异大 → 强制合并并保留双标题（同文不同名）。
6. **实体图扩展**：references=citing→cited，citations=cited→citing；只给参考文献列表的数据源用全语料反向索引恢复前向边并标 `direction_restored: true`。

## 异常处理表

| 情形 | 处置 |
|---|---|
| 语料文件解析失败 | 记入来源注册表 `status=error` + `error` 原因；其余文件继续；`result.json` uncertainty 说明 |
| 种子在语料中解析不到 | 保留为 stub（`seed[].stub=true`），`status=partial`，uncertainty 记录 |
| 引用目标不在语料中 | 保留 stub 边（原始指针 + 定位），绝不补造元数据 |
| 记录缺 DOI 且缺年份/标题/作者 | 保持独立实体，`flags=[incomplete_record]`，uncertainty 交代，不参与自动合并 |
| 成对得分 0.6–0.85 | 不合并，入 `review_queue`，uncertainty 说明待人工复核 |
| 同名不同文 | 不合并，`distinct_same_title` 标注，audit 会校验标题键共享必须有台账标注 |
| 同文不同名 | 按 DOI 强制合并，双标题作为证据保留，不报"冲突丢失" |
| `output_contract` 含未知字段 | 自动填空值并在 `uncertainty` 说明，不中断 |
| 重复运行 | 输出确定性排序，重复运行结果一致 |

## 自查方法

`python3 scripts/audit_merge.py --case ... --workdir ... --out ...` 打印 JSON：五个检查（`unique_doi_and_title_keys`、`merge_evidence_complete`、`ledger_consistency`、`uncertainty_coverage`、`contract_mirror`）各给 ok=true/false，总 `ok`；全部通过退出码 0。若 `ok=false`，按 problems 修复后重跑（可只重跑 identity_merge.py → run_case.py 链）。

## 最小示例（合成数据）

`examples/` 内是**合成示例 / SYNTHETIC, not real papers, 非正式案例结果**：3 个跨库风格 JSON（8 条虚构记录，DOI 形如 `10.0000/synth.*`）+ `case.json` + `task.md`。运行：

```bash
python3 scripts/identity_merge.py --roots examples/corpus --workdir examples/run_out
python3 scripts/run_case.py --case examples/case.json --workdir examples/run_out --out examples/run_out --layers 2
python3 scripts/audit_merge.py --case examples/case.json --workdir examples/run_out --out examples/run_out
```

预期：6 实体；预印本+期刊版合并（version_chain，score≈0.87）；同名不同文不合并（0.55，distinct_same_title）；同文不同名合并并双标题留证；残缺记录独立且在 uncertainty 交代；audit 打印 ok=true。`examples/run_out/` 保留了一次真实端到端运行的产物（见 `examples/walkthrough.md`）。

## 限制

- 仅 Python 3 标准库、默认离线（不联网，无 `--allow-net` 实现：身份合并不需要远程查询）。
- 极简 BibTeX 解析仅覆盖 title/doi/author/year/journal 字段；复杂 TeX 语法不展开。
- 标题 token 打分对中文/无空格标题较弱（按整词切分）；跨语言同名判重慎用，此类记录通常落入 `review_queue`。
- 合并阈值为面向一般英文文献语料的保守默认值；如需调整只能改 `identity_merge.py` 顶部常量并重跑。
- 不做施引量/流行度计算与主题相关性排序——那是其他 bundle 的重心。
