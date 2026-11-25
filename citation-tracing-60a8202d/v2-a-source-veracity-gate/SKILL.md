---
name: source-veracity-gate
description: 上游数据真实性与溯源门控的引文追踪 Skill。当任务要求从种子论文出发做引文追踪/关联文献发现，且组织方提供了本地语料（Crossref/EuropePMC/OpenAlex 响应缓存、边表、BibTeX 等）时触发。先审计全语料来源（sha1、格式判定、解析覆盖率、失败原因、字段冲突台账），再做带 locator 强制门禁的 1–2 层引用扩展，交付逐字段镜像 output_contract、每条记录与每条边可回指的 result.json。默认离线，仅用 Python 标准库。
---

# source-veracity-gate：先审计、后扩展的引文追踪门控

## 立刻执行：三条命令的固定顺序

**先跑审计，再跑构建，最后跑自查。不要颠倒顺序，不要跳步。**

```bash
# 第 1 步：来源审计（损坏文件只登记不中断；产物在 /app/work）
python3 /skills/weekly-skill/scripts/source_audit.py --workdir /app/work

# 第 2 步：构建结果（读 /app/work/records_norm.jsonl 与 /input/case.json）
python3 /skills/weekly-skill/scripts/build_result.py \
    --case /input/case.json --task /input/task.md \
    --out /app/output --workdir /app/work

# 第 3 步：交付自查（ok=true 且退出码 0 才算完成；有缺陷先修再交付）
python3 /skills/weekly-skill/scripts/selfcheck.py \
    --out /app/output --case /input/case.json
```

若第 2 步提示 `records_norm.jsonl 缺失`，说明第 1 步没跑或 workdir 不一致：
用同一个 `--workdir` 重跑第 1 步，或在第 2 步追加 `--roots /input` 让它自动先审计。

自查 `ok=false` 时：按缺陷清单修复（常见是 contract 字段缺失或 locator 断链），
修完必须重跑第 2、3 步。**先存 honest partial 再迭代**：即使种子没命中，
第 2 步也会写出 status=partial/failed 的 result.json，不要在它之前手工拼 JSON。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`seed_paper` 等种子字段、`output_contract`）
  与 `/input/task.md`；组织方语料（真实 Crossref/EuropePMC/出版方响应缓存、
  保留的引用图、增量导入状态等）按题目提供，可能在 `/input` 子目录。
- 工作目录 `/app/work`：审计产物 `records_norm.jsonl`、`source_registry.json`、
  `audit_report.md` 都写在这里。
- 最终结果 `/app/output/result.json`：必须含 `case_id`，并**逐字段镜像
  `output_contract` 的全部字段**（不允许丢字段；填不了的字段给诚实空值
  并在 `uncertainty` 说明）；`status` 取 ok/partial/failed 且与实际一致；
  每条 candidate、每条 edge 都带 `{file, pointer}` 来源定位。
- 人读产物 `/app/output/provenance_report.md` 一并交付。
- 预算意识：900 秒 / 64 次模型请求。三条命令是确定性管线，一条接一条跑完即可；
  不要用模型逐条手工整理文献，把请求预算留给缺陷修复与结果解读。
- 默认离线：脚本零网络调用；不提供也不接受联网开关，联网需求记入 uncertainty。

## 用途与适用条件

适用于：组织方提供本地引文语料、要求从种子论文出发做前向/后向引文追踪，
并要求每条结果可回指数据源的任务。本 Skill 的工程重心是**上游数据真实性与
溯源门控**：先建立全语料来源注册表（sha1、格式判定、解析覆盖率、失败原因、
冲突线索），再只允许带 locator 的记录进入结果。

不适用于：需要联网实时检索（无远程覆盖）、需要全文理解或引文语境细读、
纯关键词检索排序的任务。

## 输入

| 输入 | 位置 | 说明 |
|---|---|---|
| case.json | `--case`，默认 `/input/case.json` | 种子（seed_paper/seed/paper/doi/title）与 output_contract |
| task.md | `--task`，默认 `/input/task.md` | 任务文本；种子 DOI 正则兜底来源 |
| 语料文件 | 第 1 步 `--roots` 递归扫描；默认 `/input`、`/app/work`、cwd 中存在的 | 支持 .json/.jsonl/.csv/.tsv/.edgelist/.bib，格式判定见 `references/corpus_formats.md` |

## 调用方式（精确命令）

见开头"三条命令的固定顺序"。所有脚本 `python3 scripts/xxx.py` 可直接运行，
路径全部用 argparse 给定，脚本位置无关（pathlib 实现，不依赖 cwd），仅标准库。

本地合成示例的等价命令见下文"最小示例指引"与 `examples/walkthrough.md`。

## 输出

| 产物 | 位置 | 内容 |
|---|---|---|
| records_norm.jsonl | `<workdir>/` | 规范化文献/边记录，每行一条，每条带 `locator:{file,pointer}` |
| source_registry.json | `<workdir>/` | 全语料来源注册表：相对路径、sha1、字节数、判定格式、记录数、失败原因、冲突台账 |
| audit_report.md | `<workdir>/` | 人读审计报告：解析覆盖率、格式分布、逐文件登记、冲突线索 |
| result.json | `<out>/` | case_id、status、seed、candidates、edges、sources、evidence_records、uncertainty、stubs、output_contract 全字段镜像 |
| provenance_report.md | `<out>/` | 人读溯源报告：种子、候选清单（逐条定位）、边表（逐边定位）、不确定性 |

## 关键方法

1. **来源注册与审计**：递归扫描候选根（顺序：`--roots` 指定 > `/input` >
   `/app/work` > cwd），逐文件计算 sha1 与字节数，判定格式并解析；解析失败
   的文件登记原因而不是中断管线。检出"同 DOI 不同标题""同标题不同 DOI"
   两类冲突线索，全部进台账。
2. **记录定位（locator）**：每条规范化记录、每条引用边都带
   `source:{file, pointer}`（pointer 为 JSON 路径或行号），保证可回指复核。
3. **locator 强制门禁**：任何没有 locator 的记录不得进入 candidates；
   被拦截的记录写入 `omissions` 与 `uncertainty`。
4. **身份合并基线**：DOI 规范化（小写、去 `https://doi.org/` 前缀）精确匹配
   ＋标题规范化（小写、去标点、坍缩空白）匹配；两键都缺失的记录保持独立；
   合并中的字段冲突保留多值与可回指定位。
5. **方向语义**：reference 边 = citing→cited；citation 边 = cited→citing；
   数据源只给参考文献列表时，用全语料反向索引恢复前向边，边上标
   `direction_restored: true`。
6. **诚实性**：解析不出的引用目标保留为 stub（只带原始指针与定位），绝不
   补造作者/年份/标题；无结果、冲突、权限问题一律写入 `status`/`uncertainty`。

详细规则见 `references/veracity_policy.md` 与 `references/corpus_formats.md`。

## 异常处理表

| 异常情况 | 脚本行为 | 结果体现 |
|---|---|---|
| 语料文件 JSON 损坏/格式不支持 | 第 1 步登记 `status=failed/unparsed` 与原因，继续扫描其余文件 | source_registry.json、audit_report.md；第 2 步 sources 中带状态 |
| 候选根不存在 | 跳过并记入 `roots_missing`；全部不存在时打印警告、产物为空审计 | registry/audit_report |
| records_norm.jsonl 缺失 | 第 2 步报 uncertainty；若给了 `--roots` 则自动先跑审计 | result.json `uncertainty`，status 多为 failed |
| case.json 缺失/损坏 | 继续运行，case_id 置 UNKNOWN，记 uncertainty | result.json |
| 种子解析不到（字段与正则均无） | seed.via=null，记 uncertainty，status=partial/failed | result.json |
| 种子在语料中无记录 | 不补造，candidates 为空，status=partial/failed | result.json、provenance_report.md |
| 引用目标在语料内无记录 | 保留 stub（原始指针＋定位），不进入 candidates | result.json `stubs`、`omissions` |
| 合并时字段冲突（同 DOI 不同标题等） | 保留多值与定位，记 uncertainty；审计阶段另进冲突台账 | result.json、audit_report.md |
| 真实性瑕疵（损坏文件/冲突/stub/门禁拦截/坏行） | status 由 ok 降级为 partial，瑕疵逐条写入 uncertainty 作为降级依据 | result.json `status`/`uncertainty` |
| output_contract 含未知语义字段 | 诚实置 null，逐字段在 uncertainty 注明 | result.json |
| selfcheck 检出缺陷 | 打印缺陷清单，退出码 1；修完重跑第 2、3 步 | 终端输出 |

## 自查方法

跑第 3 步 `selfcheck.py`：`ok=true` 且退出码 0 才可交付。它机器校验：
case_id 非空且与 case.json 一致；output_contract 全字段在场；每条 candidate
与每条 edge 都有 `{file, pointer}` locator；status 与实际内容一致
（ok 不得对应空 candidates 或未命中种子，failed 不得对应非空 candidates）；
每条 candidate 有对应 evidence_record。另有两个人读复核点：
`audit_report.md` 的冲突台账、`provenance_report.md` 的逐边定位表。

## 最小示例指引（合成示例 / SYNTHETIC）

`examples/` 内含一个完全虚构的迷你语料（5 篇虚构文献，DOI 形如
`10.0000/synth.*`，**非真实文献**）：2 个 Crossref 风格 JSON、1 个
EuropePMC 风格 JSON、1 个故意损坏的 JSON，以及 1 对"同 DOI 不同标题"冲突。
运行方式与预期输出要点见 `examples/walkthrough.md`；`examples/run_out/`
保留了该合成示例的真实运行产物（示意输出，非正式案例结果）。

## 限制

- 只做本地语料的审计与 1–2 层引用扩展；不联网、不补造、不做全文理解。
- 格式解析覆盖常见响应形态，但出版方字段变体可能被判为 `generic-*` 或
  `unknown`（会登记而非静默丢弃）；新形态需扩展 `source_audit.py` 的解析器。
- 身份合并是基线（DOI＋标题两键），不做作者-年份模糊 blocking 与版本谱系
  判定；疑似误合并以冲突台账形式暴露，由人复核。
- 扩展深度固定 1–2 层，不做分支剪枝与相关性排序；候选排序仅按深度与 id。
