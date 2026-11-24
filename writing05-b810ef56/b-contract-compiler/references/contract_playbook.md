# 交付契约手册（Contract Playbook）

## 1. 键名与 case_id 纪律

- 契约键集合的唯一来源是 `contract_inspect.py` 的输出，禁止凭记忆
  默写；键名区分大小写，原样使用（包括其中的点号、下划线）。
- `case_id` 原样复制，不做任何规范化；case.json 无该字段时填
  `"unknown"` 并在 limits 记录，不得自拟一个 id。

## 2. 部件目录约定（result_parts/）

| 文件 | 去向 | 说明 |
|---|---|---|
| `<契约键>.md` / `.json` / `.txt` | result[契约键] | 每键一个部件；`.json` 解析为对象，其余为字符串 |
| `status.txt` | result.status | complete / partial / failed 单行；缺省时自动判定 |
| `uncertainty.md` | result.uncertainty | 不确定性与待人工确认项 |
| `change_log.md` | result.change_log | 修改记录 |
| `limits.md` | result.limits | 材料缺口、降级、边界 |
| `sources.json` | result.sources | 来源清单（含可回溯标识） |

部件是**唯一内容来源**：组装器不生成任何文字，契约键没有部件文件
就填 null。想表达"此键无法完成"，写 limits，不写空字符串冒充。

## 3. 契约缺失时的通用键兜底

case.json 无 output_contract 时（inspect 退出码 1），result.json
按通用键交付：`deliverable`（成稿）、`sources`、`uncertainty`、
`change_log`、`limits`、`status`，并在 limits 首行写明"case.json
未声明 output_contract，按通用键交付"。

## 4. 终验修复矩阵

| FAIL 项 | 原因 | 修复 |
|---|---|---|
| result.json 存在/可解析 | 未组装或手写 JSON 出错 | 一律重跑 assemble_result.py，不手工改 result.json |
| case_id 一致 | 抄写走样 | 重跑 contract_inspect.py 后重新组装 |
| 契约键存在 | 键名拼错/漏键 | 对照 contract.json 的 contract_keys 逐键核对部件文件名 |
| 契约键非空 | status=complete 但有空值键 | 补齐部件重组装，或改 status=partial 并写 limits |
| partial 有 limits 说明 | limits 为空 | 在 limits.md 逐项写：缺什么、为什么、如何补齐 |
| 引用文件存在 | result.json 引用了不存在的路径 | 复制文件到 /app/output 或改为内联文本 |
| 存在可编辑交付物 | /app/output 只有 result.json | 把成稿/证据表等可编辑文件放入 /app/output |

## 5. 增量交付节奏（900 秒预算下）

1. 步骤 0 之后立即组装一次：得到全键、多处 null 的合法 partial
   result.json —— 这是"保底交付"；
2. 每完成一个契约键就重跑步骤 2–3（秒级）；
3. 任何时刻中断，/app/output 都是可评的合法状态；
4. 时间充裕时最后再过一遍 required 键的 missing 列表。
