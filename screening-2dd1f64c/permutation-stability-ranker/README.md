# permutation-stability-ranker

文献筛选与智能排序任务的**过程质量控制** Skill：把排序稳定性作为一等交付物。一个对候选输入顺序或特征权重轻微扰动就会翻转的排序不值得信任——本引擎用固定种子的 N 次扰动运行（输入置乱 + 每个权重 ±10% 抖动）量化每条记录的名次极差与翻转次数，并计算 Kendall's W 和谐系数；名次不稳定（fragile）的记录带明确理由移入 pending_review 复核带，而不是被静默排除。

评分路径完全确定、可解释、无需模型调用；可选的一次批量模型语义判定只作为权重表中的一个普通特征注入。

## 文件

- `SKILL.md` — Skill 说明：用途与重心、适用条件、运行契约与预算纪律（≤2 次模型调用 + 纯脚本退化路径）、输入输出、异常处理、方法限制与自查。
- `scripts/stability_engine.py` — 全部逻辑，Python 3 标准库实现，无第三方依赖。子命令：
  - `featurize --case CASE.json --out features.json`：宽容定位候选池，产出可解释特征（定义写入 meta，可手工复算）。
  - `score --case CASE.json --features F.json --weights W.json [--judgments J.json] [--runs N] --out stability.json`：基准加权评分 + N 次播种扰动运行，逐条 rank min/max/mean、翻转计数、Kendall's W、stable/watch/fragile 分类。
  - `assemble --case CASE.json --stability S.json --out result.json`：fragile 移 pending_review 带、镜像 output_contract 全部字段、诚实 status/uncertainty/change_records；stability 缺失时产出全 pending 的 partial。
  - `validate --case CASE.json --result result.json`：case_id 回显、契约字段齐全、全记录恰好覆盖一次、final_rank 一致性、stability_report 合法性；PASS/FAIL + 退出码。
- `references/stability-method.md` — 方法学：特征定义、权重依据、扰动设计、Kendall's W 公式（含并列修正）、阈值、fragile 处置理由、平局协议、限制。
- `examples/minimal/` — 合成示例（case.example.json / weights.example.json / README.md）：含精确命令、预期输出与预期 fragile 记录说明。

## 运行要求

Python 3.6+，仅标准库（argparse/json/random/re/sys/pathlib）。无网络、无模型依赖即可跑通评分与交付全链路。

## 范围与限制

- 特征为词法/元数据代理：token overlap 度量词面相关，venue_tier 是标注了 `heuristic:true` 的字符串启发式；语义判断由可选 judgments 补充。
- 候选池是有限快照，不做快照外召回声明；不补造文献；案例中以 `fixture_note` 等字段标注的夹具仅作 provenance，不作为 ground truth。
- 稳定性结论以权重族为前提（扰动 ±10% 的权重值，而非特征设计本身）。
- 合成示例仅演示接口与流程，不冒充正式案例结果。
