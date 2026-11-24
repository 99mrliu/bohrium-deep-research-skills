---
name: process-qc-guard
description: 多数据库联合检索的"过程质量控制"技能。将全案例流水线(材料嗅探 intake → 规范化 normalize → 同一性判定 identity → 覆盖评估 coverage → 报告 report)封装于 QC 脚手架之中:预算感知运行计划(run_plan.json,64 次模型请求/900 秒包线内仅保留 1 次批量仲裁请求)、早期诚实 partial 骨架、逐阶段检查点(input_sha256/output_sha256/不变量)与逻辑序号账本(run_ledger.jsonl)、--resume 断点续跑(输入哈希未变则跳过、陈旧则级联重跑)、--replay 双跑字节级比对(STABLE/DRIFT),以及交付前自查门(qc-checklist.md 七项,任一 FAIL 即保持 partial)。唯一模型判断点为模糊重复对(Jaccard≥0.6)的单次批量仲裁;模糊对只入队、绝不自动合并。Python 3 标准库、离线、确定性、幂等。
---

# process-qc-guard:多数据库联合检索的过程质量控制

## 何时使用

当任务要求对 Crossref / EuropePMC / 出版方库等多个文献数据库的**离线响应材料**
做联合检索、去重合并并按 `output_contract` 交付时启用本技能。其适用判据为:
结果的可信度不仅取决于合并逻辑,更取决于**运行过程**是否可检查、可恢复、
预算安全、可重放一致。凡存在下列情形之一者必须使用:多源记录需去重且存在
模糊重复风险;执行预算受限(64 次模型请求 / 900 秒)须防超支;需要审计轨迹
(账本/检查点)支撑结论可复现;需要交付前的显式自查门以防"带错交付"。

## 固定运行方式

平台将本技能安装于 `/skills/weekly-skill`。标准命令(在任意工作目录执行):

```bash
python3 /skills/weekly-skill/scripts/qc_guard.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output
```

若安装路径不确定,回退定位:

```bash
find / -maxdepth 6 -name "qc_guard.py" 2>/dev/null
```

CLI 参数:`--case`(默认 `/input/case.json`)、`--task`(默认 `/input/task.md`)、
`--work`(默认 `/app/work`)、`--out`(默认 `/app/output`)、`--resume`、
`--replay`、`--help`。退出码:`0`=success;`2`=诚实降级 partial;`3`=input_error。

## 完整工作流

1. **(脚本)骨架先行**:读取任何输入之前,先写出 `/app/output/result.json`
   骨架(`status="partial"`),保证任何中断都留下诚实中间态。
2. **(脚本)运行计划**:在 `/app/work/run_plan.json` 登记五个阶段、逐阶段
   "脚本 vs 模型"分类与预算包线:上限 64 次模型请求 / 900 秒;全部脚本化
   阶段合并为一条 bash 命令;**唯一的模型判断点**是 identity 阶段模糊重复
   对的仲裁,且**至多 1 次批量请求**;其余 ≥60 次预算全部保留给编排与重试。
   预算数学详见 `references/budget-and-checkpoints.md`。
3. **(脚本)intake**:按结构嗅探分类每份材料(crossref/europepmc/publisher/
   reference_graph/unknown);不变量:所有发现的材料均被分类,无一静默丢弃。
4. **(脚本)normalize**:解析为通用记录,字段状态四态区分
   `ok / missing(键缺失) / unknown(值为空) / not_provided(源模式无此概念)`;
   不变量:各源计数之和 = 规范化总数。
5. **(脚本+模型)identity**:精确规则自动合并(规范化 DOI 精确、PMID 精确、
   规范化标题+年份+第一作者姓);标题 Jaccard≥0.6 且同年的模糊对**只写入
   `work/arbitration_queue.json`,绝不自动合并**;每一对判定均带 `reason_code`
   写入 `work/decision_log.json`。
6. **(模型,唯一判断点,至多 1 次请求)** 若仲裁队列非空:代理通读队列,
   对**全部**待决对给出 merge/distinct 及理由,**单次批量**写入
   `work/arbitration_decisions.json`,然后以 `--resume` 重跑(identity 输入
   哈希变化 → identity 及下游自动重跑,上游跳过)。
7. **(脚本)coverage**:由合并记录重算"数据库×字段"覆盖矩阵;不变量:
   矩阵计数可由合并记录独立重算复现。
8. **(脚本)report**:解析 `output_contract`(object/array/string 形状均支持),
   有确定性映射则填充,无则置 `null` 并列入 `unresolved_contract_fields`,
   **绝不捏造**;随后执行交付前自查门。
9. **(脚本)重放验证**:执行同一命令加 `--replay`,于两个全新目录各完整
   运行一次并逐字节比对,裁决 STABLE/DRIFT 写入 `work/replay_verdict.json`
   并刷新报告。
10. **(脚本)自查门交付**:按 `references/qc-checklist.md` 七项检查
    (契约完备、产物哈希、计数守恒、决策日志完备、仲裁队列空或显式待决、
    重放 STABLE、诚实 partial);任一 FAIL → 状态保持 `partial` 并在
    `uncertainty` 中给出精确原因;全部 PASS 且无任何待决事项方可交付
    `success`。报告:`/app/output/qc_report.md` 与 `/app/output/result.json`。

## 输出契约

`/app/output/result.json` 始终包含:`case_id`、`status`
(`success|partial|input_error`)、`sources`(逐输入文件 sha256)、
`uncertainty`、`change_records`(源自账本)、`artifacts`(path+sha256,
相对路径)、`unresolved_contract_fields`,以及 `case.json.output_contract`
声明的**每一个字段**。运行目录契约:输入只读 `/input`;中间产物、检查点、
账本、运行计划、仲裁队列与决定均置于 `/app/work`;交付物置于 `/app/output`。

## 状态语义

- `success`:契约全部填充、仲裁队列已决或为空、自查门七项全 PASS、重放 STABLE。
- `partial`:诚实降级——存在待决仲裁对、无法填充的契约字段、自查门 FAIL
  或运行中断;`uncertainty` 必须逐项给出精确原因。骨架 partial(运行刚开始)
  亦为合法中间态。
- `input_error`:`case.json` 缺失、不可解析或缺少 `case_id`;退出码 3。

## 规则边界和维护

- 本技能**不访问网络**,仅处理离线材料;不做任何超出材料证据的推断。
- 模糊重复对绝不自动合并;合并只依据精确规则或经模型仲裁的显式决定。
- 契约字段无法确定性填充时一律置 `null` 并登记,**禁止编造**。
- 合并采用按字段来源优先级(`case.json.source_dbs` 顺序)取值,并保留
  字段级溯源(`provenance.from_record / from_db / rule`)。
- 维护:修改判定阈值、优先级或契约映射时,必须同步更新
  `references/budget-and-checkpoints.md` 与本文件,并重跑合成示例验证
  `--replay` 仍为 STABLE。

## 确定性与自查

确定性来源:全部产物排序落盘、sha256 校验;账本使用**逻辑序号**而非墙钟;
路径一律相对;无随机性、无网络、无环境依赖(Python 3 标准库)。幂等性:
同一命令重复执行,`--resume` 下全部阶段记 `stage_skipped`,交付物不变。
自查即第 10 步之自查门,检查项以 `references/qc-checklist.md` 为唯一权威。

## 示例

`examples/synthetic-input/` 为**合成教学数据**(`case_id:
"synthetic-qc-guard-001"`,全部 DOI 为虚构的 `10.99977/...`,标题均为
"Synthetic ...",与现实文献无任何对应关系),含一对落入仲裁队列的近重复
记录。`examples/synthetic-output/` 为**真实运行**该脚本(含 `--resume` 与
`--replay`)得到的产物,复现步骤与重放裁决见
`examples/synthetic-output/run-record.md`。
