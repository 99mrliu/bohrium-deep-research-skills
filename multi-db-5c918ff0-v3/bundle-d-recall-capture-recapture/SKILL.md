---
name: recall-capture-recapture
description: 多数据库联合检索的召回统计估计与遗漏量化技能。把多来源文献检索视为捕获-再捕获（capture–recapture）问题：对 /input 下离线材料（Crossref works 信封、EuropePMC resultList、出版商 JSON/JSONL/CSV）做嗅探规范化与最小身份归并，得到"簇 × 来源"捕获历史矩阵；据此计算成对 Chapman（Lincoln–Petersen 偏差校正版，含方差与 95% CI，m_ij=0 如实声明无定义）、多源 Chao1 下界估计（f1/f2 驱动，f2=0 用偏差校正形式，对数变换 CI）、各库独有贡献与条件覆盖矩阵、异质性警示，并生成带数字锚点的停止/遗漏陈述（"估计 N_unseen 条未检出，95% CI [a,b]；追加一个画像为 X 的来源预期独有贡献 ≤k"）。小样本（任一库检出<5 或总簇<10）自动降级为 descriptive-only；点估计≠真实总数，一切估计与观测事实成对呈现。产出 capture_histories.json、recall_estimate.json、recall_report.md、result.json（含 case_id 与全部 output_contract 字段，填不出→null+unresolved）。纯 Python 3 标准库、离线、确定性、幂等。
---

# Recall Capture–Recapture（召回的统计估计与遗漏量化）

多数据库联合检索场景中，本技能回答的不是「检到了什么、哪些字段缺失」，
而是「**按统计学估计，三个库合计漏了多少条？这个估计有多可靠？再查一个
库还值不值？**」。核心是把每个数据库看作一次「捕获」，把去重后的文献簇
在来源间的重叠模式（捕获历史）当作关于未检出簇数量的信息来源，用
Chapman / Chao1 估计量给出**点估计 + 置信区间 + 假设声明 + 小样本诚实
降级**，把含糊的「可能遗漏」换成可辩护的量化遗漏陈述。

## 适用场景与边界

适用：
- 案例要求多数据库联合检索，材料为离线响应文件，需要量化「漏检了多少」；
- 需要比较各来源的独有贡献与条件覆盖（库 A 检出的簇有多大比例也被库 B 检出）；
- 需要给出停止规则判断：追加来源的预期产出是否低于可接受阈值。

边界（第一类输出，与估计同等重要）：
- **明示假设**：估计基于「封闭总体 + 各库检出概率异质但重叠结构含信息 +
  无行为响应 + 身份归并正确」。假设不成立时（例如来源画像差异极端、
  捕获历史高度集中于单一模式），本技能**只报告观测重叠事实，不给点估计**；
- **小样本降级**：任一来源检出簇数 < 5 或总簇数 < 10 时，自动降级为
  descriptive-only——点估计被抑制（置 null 并标注
  `suppressed_descriptive_only`），只给出捕获历史普查；
- **点估计 ≠ 真实总数**：任何估计值必须与观测事实（S_obs、f1、f2、n_i）
  成对呈现；Chao1 是下界估计，真实遗漏可能更多；
- **不联网、不臆造检出**：所有数字来自本地材料的捕获历史矩阵或声明的公式；
- 本技能**不做**描述性覆盖制图（字段×数据库矩阵不是重心）、**不做**去重
  机制本身（只保留估计所需的最小身份归并）、**不做**相关性筛选判断。

## 运行环境

- 仅依赖 Python 3 标准库；无网络；无随机性；产出物不含墙钟时间；
- 技能安装路径：`/skills/weekly-skill`；若不确定，用
  `SKILL="${SKILL:-/skills/weekly-skill}"` 兜底，或先
  `find / -maxdepth 6 -name recall_estimator.py 2>/dev/null` 定位；
- 退出码：`0` 正常完成（分析性降级如 descriptive-only 体现在 status/flag，
  不影响退出码）；`2` 诚实降级（顶层异常被捕获，或存在无法填充的契约字段，
  仍写出诚实 result.json）；`3` 输入无效（case.json 缺失或不可解析）；
- 确定性幂等：同输入重跑产物字节一致。

## 运行契约

标准入口（`run_case.sh` 或等效）：

```bash
python3 "${SKILL:-/skills/weekly-skill}/scripts/recall_estimator.py" run-all \
  --input /input --work /app/work --output /app/output
```

也可分步执行：`parse → estimate → report → finalize → selfcheck`
（`--help` 及各子命令 `-h` 可用，退出码 0）。

- 输入：`/input/case.json`（case_id、source_dbs、materials、output_contract）
  + `/input/task.md` + 材料文件（可在 `/input` 根或 `/input/materials/`）；
- 中间产物：`/app/work/`（capture_histories.json、clusters.json、
  omission_statement_baseline.md）；
- 最终产物：`/app/output/`（result.json + capture_histories.json +
  clusters.json + recall_estimate.json + recall_report.md）；
- result.json 必含 `case_id`、`skill_name`、`status`、`products`、
  `sources`（含 sha256）、`uncertainty`、`change_records`、`counts`、
  `checks`，以及 case.json `output_contract` 声明的**每一个**字段：
  能填则按声明形状填充，填不出 → `null` + 登记
  `unresolved_contract_fields`（诚实 partial，绝不编造）；
- 不修改 `/input`；所有写入限于 `--work` 与 `--output`。

## 工作流程

0. **【模型判断】读案例**：读 `/input/task.md` 与 `/input/case.json`，确认
   研究问题、`source_dbs`、`output_contract` 字段与形状。
1. **【脚本 parse】解析+嗅探+规范化**：按 case.json materials 清单 + 目录
   扫描发现材料；按信封结构嗅探分类（crossref `message.items` /
   europepmc `resultList.result` / publisher JSON 数组、JSONL、CSV）；
   归一化 DOI、PMID、标题、年份、第一作者姓。
2. **【脚本 parse】最小身份归并**：并查集按键合并——DOI 精确、PMID 精确、
   规范化标题+年份+第一作者姓复合键；簇携带来源归属集合；写出
   `clusters.json` 与 `capture_histories.json`（簇×来源 0/1 矩阵 +
   模式计数，如 `"101"`）。仅由模糊键跨源连接的簇被显式标记
   （`fuzzy_only_cross_source_clusters`），作为不可验证身份披露。
3. **【脚本 estimate】重叠普查**：从捕获历史矩阵计数 n_i（各库检出簇数）、
   m_ij（两库共同检出）、S_obs、f1（恰 1 库）、f2（恰 2 库）。
4. **【脚本 estimate】估计阶段**：
   - 每个库对：Chapman N̂ = ((n_i+1)(n_j+1)/(m_ij+1)) − 1，Chapman(1951)
     方差，正态近似 95% CI（下界不低于 max(n_i,n_j)）；m_ij=0 →
     无定义并如实声明；
   - 多源：Chao1 = S_obs + f1²/(2f2)（f2=0 → 偏差校正式 f1(f1−1)/2），
     Chao(1987) 方差，对数变换 95% CI；unseen = max(0, N̂ − S_obs)；
   - 各库独有贡献（单例簇计数）与条件覆盖矩阵 P(在 j | 在 i) = m_ij/n_i；
   - 异质性警示：捕获历史集中于少数模式（≥70%）、估计量分歧
     （Chao1 与最大成对 Chapman 相对差 >50%）、模糊键跨源链接；
   - 小样本检查 → 触发则全部点估计抑制为 null（descriptive-only）。
   全部公式输入（n_i、m_ij、f1、f2）原样打印进 recall_estimate.json。
5. **【模型判断】复核假设 + 起草遗漏陈述（一次批量请求内完成）**：
   读 recall_estimate.json 的 `assumptions` 与 `heterogeneity_warnings`，
   结合案例材料判断假设是否成立；**引用具体数字**起草遗漏/停止陈述
   （模板见 references/interpretation-playbook.md），写入
   `/app/work/omission_statement.md`。若不写，finalize 自动采用脚本的
   确定性基线陈述并在 change_records 登记 `script_baseline`；若改写，
   登记 `model_authored_override`。陈述必须包含数字锚点，禁止「可能遗漏」
   式空话。注意预算：官方 Harness 约 64 次请求 / 900 秒，脚本一次运行
   即完成全部计算，本步骤只做一次复核+一次起草。
6. **【脚本 finalize】落盘**：recall_estimate.json、recall_report.md、
   result.json（含全部契约字段、来源 sha256、uncertainty（假设风险 +
   不可验证身份 + 小样本警示）、change_records、counts）。
7. **【脚本 selfcheck】自查**：契约键齐全；用 capture_histories.json 重算
   每个估计的输入与结果并比对；CI 满足 lower ≤ point ≤ upper（或被显式
   抑制）；矩阵行和与模式位数一致；exit 0/1。

## 输出合同映射表

| case.json output_contract 字段（按名称匹配） | 填充来源 |
|---|---|
| 含 `candidate` | 簇列表（cluster_id、pattern、sources、代表元数据） |
| 含 `recall`/`estimate`/`unseen` | Chao1 摘要 dict（S_obs/f1/f2/N̂/CI/unseen/descriptive_only） |
| 含 `omission`/`stopping` | 遗漏陈述（Agent 改写版优先，否则脚本基线） |
| 含 `uncertainty` | 不确定性陈述字符串 |
| 含 `change` | change_records 列表 |
| 含 `source` 且形状 list | 材料文件清单 |
| 含 `summary` | counts + descriptive_only 摘要 |
| 其余未知名 | null + unresolved_contract_fields 登记 |

## 异常处理表

| 异常 | 行为 | 退出码 |
|---|---|---|
| case.json 缺失/不可解析 | 写最小 result.json（status=failed） | 3 |
| 材料文件缺失/不可读/未识别 | notes 记录，跳过，继续其余材料 | 0 |
| 声明库无材料 | 该来源不进捕获历史；若只剩 <2 个来源，Chapman 表为空并说明 | 0 |
| 任一来源检出 <5 或总簇 <10 | descriptive-only：点估计置 null + 理由 | 0（status=partial） |
| 库对 m_ij=0 | 该对 Chapman 标 `undefined_zero_overlap` | 0（status=partial） |
| f2=0 | Chao1 自动切换偏差校正形式并标注 variant | 0 |
| 契约字段无法填充 | null + unresolved_contract_fields | 2（status=partial） |
| 顶层未捕获异常 | 写诚实 result.json（status=failed + error） | 2 |

## 合成最小示例

`examples/synthetic-input/` 为**虚构**教学案例 `synthetic-recall-cc-001`
（DOI 前缀 10.99977，标题/作者均虚构）：真实不同文献共 20 篇，三个库
合计捕获 15 篇（重叠模式 111×6、110×3、101×2、010×1、001×2、100×1），
5 篇从未被捕获；另埋 2 条库内重复与 1 条跨源近似重复（标题标点变体）
以演练身份归并。`materials/truth.json` 为合成示例专用真值，经
`--truth` 显式传入时报告估计-真值对照（Chao1 N̂=16.6 vs 真值 20，
误差 −3.4，真值落在 95% CI [15.2171, 26.7916] 内——直观展示 Chao1
的下界性质）。`examples/synthetic-output/` 为对输入**真实运行脚本**
得到的产物，`run-record.md` 记录命令与退出码。

## 诚实声明

- 本技能的估计**不是**真实总数：是带明示假设的统计推断；假设部分只能
  论证不能验证（封闭总体、归并正确等），全部列入 result.json 的
  `uncertainty`；
- Chao1 是**下界**：说「至少漏了约 k 条」比说「漏了 k 条」更接近事实；
- 小样本时本技能主动**放弃**点估计而不是给出漂亮但不可靠的数字；
- 仅由模糊键连接的跨源簇被显式披露为不可验证身份；
- 公式仅按方法名称/年份归属（Lincoln–Petersen；Chapman 1951；Chao 1987），
  不编造文献细节；精确公式与适用条件见 `references/estimators.md`。
