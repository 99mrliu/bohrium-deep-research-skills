# 运行记录（synthetic-recall-cc-001）

本目录全部产物由**真实执行** `scripts/recall_estimator.py` 生成，非手工编写。
输入为合成教学数据（虚构，见 `examples/README.md` 与 case.json `_note`）。

## 实际执行的命令与退出码

```bash
B=<bundle 根目录>/bundle-d-recall-capture-recapture

# 1) 端到端（不同 cwd 下运行）
cd /tmp
python3 "$B/scripts/recall_estimator.py" run-all \
  --input "$B/examples/synthetic-input" \
  --work "$B/.example-work" \
  --output "$B/examples/synthetic-output" \
  --truth "$B/examples/synthetic-input/materials/truth.json"
# 退出码 = 0
# stdout: parse: 34 原始记录 → 15 簇，来源=crossref,europepmc,publisher
#         estimate: descriptive_only=False
#         report: recall_report.md 写出（99 行）
#         finalize: status=complete unresolved=0
#         selfcheck: 全部通过
```

同输入在 /tmp 下另跑两轮并 `diff -r`：**产物字节一致**（确定性与幂等验证通过）。

## 埋设结构 vs 检出结果对照

| 埋设（真值） | 管线检出 | 一致？ |
|---|---|---|
| 真实不同文献 20 篇 | （真值不进入管线；经 --truth 对照） | — |
| 三库合计捕获 15 簇 | S_obs = 15 | ✓ |
| 重叠模式 111×6, 110×3, 101×2, 010×1, 001×2, 100×1 | capture_histories.json 完全一致 | ✓ |
| 2 条库内重复（P01 大小写变体、PUB-0013 重复行） | 34 原始记录 → 15 簇，within_source_duplicate_records=2 | ✓ |
| 1 条跨源近似重复（P07 标题标点变体、无 DOI） | 归并为同一簇 C007，并显式标记 fuzzy_only_cross_source_clusters=["C007"] | ✓ |

## 估计 vs 真值（--truth 对照，仅合成示例可行）

| 量 | 估计 | 真值 | 误差 |
|---|---|---|---|
| 总相关数 N（Chao1） | 16.6000（95% CI [15.2171, 26.7916]） | 20 | −3.4000；真值落在 95% CI 内 |
| 未检出 unseen | 1.6000（95% CI [0.2171, 11.7916]） | 5 | −3.4000 |
| Chapman crossref×europepmc | 13.3000 [12.0760, 14.5240] | 20 | −6.7000 |
| Chapman crossref×publisher | 14.8889 [12.5596, 17.2182] | 20 | −5.1111 |
| Chapman europepmc×publisher | 16.2857 [11.9299, 20.6415] | 20 | −3.7143 |

读法：Chao1 是**下界**估计——低估真值 20 是预期行为，且真值落在 95%
置信区间内；三个成对 Chapman 中重叠最充分的 europepmc×publisher 最接近
真值。这正是本技能要求「点估计≠真实总数、必须与观测事实成对呈现」的原因。

## 数字可复算验证

独立一条 python 命令从 capture_histories.json 重算（详见评测记录）：
n_i = {crossref:12, europepmc:10, publisher:10}，m_ij = {ce:9, cp:8, ep:6}，
f1=4，f2=5 → Chapman 13.3000/14.8889/16.2857，Chao1 16.6000、
CI [15.2171, 26.7916]、unseen 1.6000 —— 与 recall_estimate.json 逐项一致；
`selfcheck` 子命令退出码 0。

## 中间产物

`$B/.example-work/`（capture_histories.json、clusters.json、
omission_statement_baseline.md、omission_statement.md 缺省）为中间产物，
已由 finalize 复制/消费进本目录；交付包中不保留该目录。
