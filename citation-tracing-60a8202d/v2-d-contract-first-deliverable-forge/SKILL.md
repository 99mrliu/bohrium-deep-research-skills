---
name: contract-first-deliverable-forge
description: 当任务给出 case.json（含 output_contract）并要求交付可复核的引文追踪结果时触发。契约优先：从 output_contract 生成 result.json 骨架并机器校验逐字段镜像填充，渲染人读证据包（证据表、CSV、引用网络预览图），适合需要"先跑确定性管线、再交机器校验交付物"的文献追踪/关联文献发现场景。默认离线。
---

# contract-first-deliverable-forge（契约优先交付锻造）

## 先跑哪条命令（30 秒内开始）

按以下顺序执行（所有脚本位置无关，`python3` + 标准库即可，默认离线）：

```bash
# 0. 生成契约骨架与填充计划（可选但推荐，便于人工核对契约字段）
python3 scripts/contract.py --skeleton --case /input/case.json --workdir /app/work
# 1. 先跑 pipeline.py：语料发现→解析→去重→引用扩展→按 output_contract 填充 result.json
python3 scripts/pipeline.py --case /input/case.json --out /app/output --workdir /app/work
# 2. 再跑 render_pack.py：渲染人读交付包（证据表/CSV/网络预览图）
python3 scripts/render_pack.py --result /app/output/result.json
# 3. 最后 contract.py --verify：逐字段机器校验，ok=true 且退出码 0 才算交付完成
python3 scripts/contract.py --verify --case /input/case.json --out /app/output
```

若第 3 步 `ok=false`：按打印的逐字段表修复（缺字段→补填充逻辑；空字段→填充或在
`uncertainty` 中点名说明），然后重跑 1→2→3。

## 用途与适用条件

围绕种子文献做前后向引文追踪时，本 Skill 负责**下游交付与渲染工程**：
把 `case.json` 中的 `output_contract` 当作机器可校验的交付契约，保证 `result.json`
逐字段镜像填充（不丢字段），并产出一套人读证据包供复核。适用于组织方材料位置与
格式未知、要求结果可回指复核、且预算有限（900 秒 / 64 次模型请求）的评测场景。

不适用：需要联网实时检索 API、需要全文内容理解、需要复杂成对相似度裁决的场景
（本 Skill 的身份合并是 DOI/标题双键基线，不做模糊打分）。

## 输入

- `/input/case.json`：含 `case_id`、`seed_paper`（doi/title）、`output_contract`。
- 语料：组织方材料，格式与位置未知；pipeline 递归扫描候选根
  （`--roots` 指定 > `/input` > `/app/work` > cwd），识别
  `.json/.jsonl/.csv/.tsv/.edgelist/.bib`，解析 Crossref（`message.items`/单条
  `message`）、EuropePMC（`resultList.result`）、OpenAlex 风格（`results`/
  `referenced_works`）、通用 JSON 节点（含 `references`/`citations`）与通用边表
  （`source`/`target` 列）。

## 输出

- `/app/output/result.json`：含 `case_id`、诚实 `status`（ok/partial/failed）、
  `seed`、`candidates`、`edges`、`sources`、`evidence_records`、`uncertainty`、
  `merge_log`，以及 **`output_contract` 全字段镜像**（自定义字段同样填充）。
- `/app/output/evidence_table.md`、`nodes.csv`、`edges.csv`、`preview_data.json`、
  `network_preview.png`（matplotlib 可用时）或 `network_preview.svg`（标准库降级）。
- `/app/work/result_skeleton.json`：契约骨架＋逐字段填充计划（第 0 步产物）。

## 运行契约

`/input/case.json` + `/input/task.md` → `/app/work`（骨架、中间产物）→
`/app/output/result.json`（含 `case_id`、镜像 `output_contract` 全字段、诚实
`status`/`uncertainty`、每条记录与每条边的来源定位 `{file, pointer}`）。
预算意识：900 秒 / 64 请求——**用一条命令跑完确定性 Python 管线**，模型只做参数
确认与结果解读，不逐条手工整理文献。管线在 ingest 完成后**先落盘一版 honest
partial** `result.json`（status=partial），扩展完成后再覆盖增强，中途被中断也有
可交付的诚实部分结果。

## 关键方法

1. **契约镜像填充**：`contract.py --skeleton` 解析 `output_contract` 生成骨架；
   `pipeline.py` 内置字段填充器注册表（FILLERS），契约里每个 key 都写入
   `result.json` 顶层；未注册字段给类型空值并在 `uncertainty` 点名。
2. **去重**：DOI 规范化（小写、去 `https://doi.org/` 前缀）精确键＋标题规范化
   （小写、去标点、坍缩空白）键；两键皆缺失的记录保持独立；合并记入 `merge_log`。
3. **方向语义**：reference 边 = citing→cited；citation 边 = cited→citing。数据源只给
   参考文献列表时，用全语料反向索引恢复前向边并标注 `direction_restored: true`。
4. **诚实 stub**：解析不出的引用目标保留为 stub（仅原始指针与 locator），绝不补造
   作者/年份/标题；stub 计入 `uncertainty` 并令 `status` 降为 partial。
5. **渲染**：`render_pack.py` 生成证据表与 CSV；预览图以种子为中心放射布局，节点
   按层着色（种子红/一层蓝/二层绿/stub 灰），reference 实线、恢复的 citation 边
   弯曲虚线，避免双向边重叠；`preview_data.json` 保留坐标与边数据供复核重绘。

## 异常处理表

| 异常 | 行为 | 出口 |
|------|------|------|
| case.json 缺失/非 JSON | 报错到 stderr | 退出码 2（contract）/抛错（pipeline） |
| case.json 无 output_contract | result.json 仅含最低字段集，uncertainty 记一条 | pipeline 继续，退出码按 status |
| 语料文件解析失败 | 记入 `sources[].status=failed/error`，不中断 | uncertainty 记录；status 降 partial |
| JSON 结构不识别 | 标记 `json(unsupported)` 跳过 | sources 注册表可见 |
| 种子未在语料中解析 | candidates 为空、seed.found=false | status=failed，pipeline 退出码 1 |
| 引用目标无法解析 | 建 stub（无元数据补造） | uncertainty 记录；status 降 partial |
| matplotlib 缺失 | render_pack 降级标准库手写 SVG | stderr 记一条，退出码仍 0 |
| `--allow-net` 被给定 | 仅记日志，不真正联网（离线优先） | uncertainty 记录 |
| verify 发现 missing/empty 字段 | 打印逐字段表＋PROBLEM 行 | ok=false，退出码 1 |

## 自查方法

1. `contract.py --verify` 退出码必须为 0、`ok=true`；逐字段表无 missing、无未豁免 empty。
2. `result.json.status` 与证据一致：有 stub 或解析失败时不许报 `ok`。
3. 随机抽 2 条边，用 `locator.file`+`pointer` 回原始语料核对引用关系真实存在。
4. `evidence_table.md` 候选数 == `result.json.candidates` 长度 == `nodes.csv` 行数 − 1。
5. 预览图真实生成（PNG 或 SVG 其一），且与 `preview_data.json` 的节点/边一致。

## 最小示例指引

`examples/` 内置**合成**迷你语料（5 篇虚构文献记录、DOI 形如 `10.0000/synth.*`，
SYNTHETIC 非真实文献），端到端运行方式与真实运行产物见 `examples/walkthrough.md`；
产物保留在 `examples/run_out/`。一条命令复现：

```bash
cd <skill 根目录>
python3 scripts/contract.py --skeleton --case examples/case.json --workdir examples/run_out/work
python3 scripts/pipeline.py --case examples/case.json --roots examples/corpus \
    --out examples/run_out/output --workdir examples/run_out/work
python3 scripts/render_pack.py --result examples/run_out/output/result.json --svg-only
python3 scripts/contract.py --verify --case examples/case.json --out examples/run_out/output
```

## 限制

- 默认零网络；`--allow-net` 当前版本仅记日志，不做任何远程请求。
- 身份合并是 DOI/标题双键精确基线，不做作者-年份模糊打分与版本谱系裁决。
- 引用扩展限 1–2 层（`--max-layers`），不做关键词相关性剪枝。
- 预览图为示意图（radial 布局），不替代正式可视化；大数据集上 SVG 标签可能重叠。
- 不负责关键词检索、全文阅读、引文内容语义理解。
