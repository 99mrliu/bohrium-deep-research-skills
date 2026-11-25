# 合成示例端到端走查

> **合成示例 / SYNTHETIC, not real papers, 非正式案例结果。**
> 全部文献与 DOI（形如 `10.0000/synth.*`）均为虚构。`run_out/` 是作者在本机
> 真实运行三条命令后保留的产物，用于说明预期输出形态。

## 语料设计（8 条虚构记录，3 个跨库风格文件）

| 记录 | 文件 | 角色 |
|---|---|---|
| `10.0000/synth.a1`（2021 期刊版） | `corpus/crossref_export.json` | 种子；引用 `synth.found` 与 `synth.b1` |
| `10.0000/synth.arxiv.a1`（2020 arXiv 预印本，标题带副标题） | `corpus/openalex_dump.json` | 与种子同一论文，应合并为 version_chain |
| `10.0000/synth.s1`（Jia Chen, 2018） | `corpus/crossref_export.json` | 同名不同文 之一 |
| `10.0000/synth.s2`（Rao Iyer, 2021） | `corpus/europepmc_hits.json` | 同名不同文 之二；引用种子 |
| `10.0000/synth.m1`（期刊版标题 A） | `corpus/crossref_export.json` | 同文不同名 之一；引用 `synth.found` |
| `10.0000/synth.m1`（会议版标题 B，同 DOI） | `corpus/europepmc_hits.json` | 同文不同名 之二，应强制合并并双标题留证 |
| 无 DOI 无年份的 notes | `corpus/europepmc_hits.json` | 残缺记录，应保持独立并在 uncertainty 交代 |
| `10.0000/synth.found`（2015 奠基作） | `corpus/openalex_dump.json` | 被多条引用，反向扩展目标 |

## 运行命令与退出码（实际运行，macOS, python3，离线）

```
python3 scripts/identity_merge.py --roots examples/corpus --workdir examples/run_out   # 退出码 0
python3 scripts/run_case.py --case examples/case.json --workdir examples/run_out --out examples/run_out --layers 2   # 退出码 0
python3 scripts/audit_merge.py --case examples/case.json --workdir examples/run_out --out examples/run_out   # 退出码 0
```

## 实际运行结果要点

- `identity_merge.py` 输出：`entities=6, records=8, merged_groups=2, review_pairs=0, distinct_same_title_pairs=1, files_error=0`。
- 预印本+期刊版合并：E0001 由 `r00001`（Crossref 期刊版）+ `r00007`（OpenAlex arXiv 版）合并，得分 0.87，`flags=[version_chain]`，冲突字段（标题大小写/副标题、年份 2021 vs 2020、venue）保留在 `merge_evidence.conflicts`。
- 同文不同名合并：E0003 由 `r00003` + `r00005` 合并（同 DOI，得分 1.0），`flags=[version_chain, same_work_different_title]`，双标题均保留。
- 同名不同文未误并：E0002 与 E0004 得分 0.55（作者护栏压分），台账 `distinct_same_title` 标注。
- 残缺记录：E0005 保持独立，`flags=[incomplete_record]`，`result.json` 的 `uncertainty` 有交代。
- `run_case.py`：种子 `10.0000/synth.a1` 解析为 E0001；第 1 层得 E0004（前向，反向索引恢复，`direction_restored=true`）与 E0006（后向 references）；第 2 层得 E0003；`synth.b1` 不在语料中 → stub，uncertainty 记录；`result.json` 逐字段镜像 `output_contract` 全字段。
- `audit_merge.py`：五个检查全部 `ok=true`，总 `ok=true`。

## 产物清单（run_out/）

| 文件 | 说明 |
|---|---|
| `entities.jsonl` | 6 个合并后实体（含 members、locator、版本谱系、merge_evidence） |
| `merge_ledger.json` | 合并台账（成对打分、理由、冲突、distinct_same_title、same_work_different_title、来源注册表） |
| `result.json` | 交付结果（case_id + output_contract 全字段镜像） |
| `merge_report.md` | 人读合并台账 |
