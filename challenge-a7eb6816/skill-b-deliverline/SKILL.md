---
name: deliverline-contract-render
description: >-
  科研成果转化写作任务的下游交付与渲染工程技能。触发场景：任务需要按 case 自带
  output_contract 交付结构化 result.json 与可编辑产物（如 Markdown 推介书、
  转化方案），并且需要把写作产物渲染成真实可检查的预览（自包含 HTML + 分页
  SVG）供人工或机器核验时。覆盖 output_contract 契约优先抽取与保底脚手架、
  纯标准库 HTML+SVG 预览渲染、交付前机械验收门（不过门不交付）。
  不负责事实核查、受众改写与上游写作本身。
---

# deliverline-contract-render：契约交付与预览渲染工程

## 重心与边界

**重心**：下游交付与渲染工程（deliverable engineering），解决「写完了却交不对」
这一类错位——result.json 缺字段、类型错（把 `1` 当 `true`）、引用的产物路径
不存在、`status=complete` 却挂着一串 limitations、交付物没人真正打开看过。

本技能提供三段式机械保障：

1. **契约优先**：先抽取 `output_contract` 生成 `contract_map.json` 与保底
   `result.json` 脚手架，任何时刻输出目录里都存在结构合法的 result.json；
2. **可检查预览**：把 Markdown 稿件渲染成自包含 HTML（内联 CSS、中文正常）与
   逐行分页 SVG，渲染失败如实报错退出，禁止假装成功；
3. **验收门**：交付前对照契约机械验收，不过门（退出码非 0）不交付。

**边界**（不做的事）：
- 不做事实性核查、数据真实性审计（属其他技能方向）；
- 不做受众分析、文案润色等上游写作；
- 不依赖任何第三方包（评测机只保证 Python 3 标准库）；
- 不预制答案：脚手架只给诚实占位值，内容由真实写作流程回填。

## 运行契约

平台运行环境：`/input/case.json` 与 `task.md` 为只读输入；工作目录
`/app/work`；最终产物写入 `/app/output`。

**result.json 契约**（`/app/output/result.json`）：
- 必须含 `case_id`，与 case.json 中的 `case_id` **逐字节一致**；
- 必须覆盖 case 自带 `output_contract` 声明的**全部字段**；
- 字段类型必须严格匹配：JSON 中 `true/false` 是 boolean，`1` 是 integer，
  **boolean 不可当 integer**，反之亦然；
- `status` 只能是 `complete` 或 `partial`；
- `status=complete` 时 `limitations` 必须为**空数组**；
- 引用的产物路径（deliverables 等）必须相对输出目录真实存在。

**诚实 partial**：写不完就交 `status=partial`，并在 `limitations` 中逐条说明
缺口（哪部分没写、为什么、缺什么输入）。禁止用 `complete` 掩盖未完成。

**契约字段缺失时的空值规则**：当某个契约字段暂无真实内容可填，使用该类型
允许的「最空」值占位——字符串用 `""`、integer 用 `0`、number 用 `0.0`、
boolean 用 `false`、array 用 `[]`、object 用 `{}`——并在 `notes` 中说明
占位原因。占位值配合 `status=partial` 使用；只有回填真实内容后才允许转
`complete`。

## 标准流程

技能安装路径为 `/skills/weekly-skill`，以下用 `$SK` 代指。若环境变量未设置，
用 fallback 定位：

```bash
SK="${SK:-/skills/weekly-skill}"
[ -f "$SK/scripts/contract_scaffold.py" ] || \
  SK="$(dirname "$(find / -maxdepth 6 -name contract_scaffold.py 2>/dev/null | head -1)")/.."
```

### 第 0 步：契约抽取与保底脚手架（最先做！）

```bash
python3 "$SK/scripts/contract_scaffold.py" --case /input/case.json --outdir /app/output
# 退出码：0=契约已定位；2=case.json 缺失/非法；3=未定位到契约（仍写出保底 result.json）；4=写出失败
```

产出 `/app/output/contract_map.json`（字段路径/类型/是否必填）与
`/app/output/result.json`（保底脚手架，status=partial）。**从这一刻起，
/app/output 中始终存在结构合法的 result.json**，后续流程崩溃也有兜底。

### 第 1 步：写作（上游流程，本技能不接管）

在 `/app/work` 中完成稿件，如 `/app/work/manuscript.md`。写作中随时可用
`contract_map.json` 对照还需回填哪些字段。

### 第 2 步：渲染可检查预览

```bash
python3 "$SK/scripts/preview_render.py" --md /app/work/manuscript.md \
  --outdir /app/output --lines-per-page 40
# 退出码：0=成功；2=输入缺失；6=渲染/校验失败（见 /app/output/render_error.json）
```

产出 `preview.html`（自包含，双击即查）与 `preview_page1.svg …`（逐行分页
预览）。渲染器自带校验：稿件每个标题必须出现在产物中、产物非空；校验不过
以非零退出并写 `render_error.json`，**绝不假装成功**。

### 第 3 步：回填 result.json

把脚手架中的占位值替换为真实内容（可用编辑器或一段 Python 标准库脚本），
回填后把 `status` 改为 `complete`（仅当 limitations 为空）或保持 `partial`
并在 limitations 中列明缺口。保存为 `/app/output/result.json`。

### 第 4 步：交付前验收门（不过门不交付）

```bash
python3 "$SK/scripts/deliverable_gate.py" \
  --case /input/case.json \
  --contract-map /app/output/contract_map.json \
  --result /app/output/result.json \
  --base-dir /app/output --outdir /app/output
# 退出码：0=PASS 可交付；5=FAIL 列出全部失败项，禁止交付；
#         2=输入缺失；3=契约映射非法；4=result.json 非法；6=报告写出失败
```

退出码为 0 才允许宣布交付；为 5 时按 `gate_report.md` 逐项修复后重跑。

## 异常处理

| 异常 | 处置 |
|---|---|
| case.json 缺失/非法 JSON | scaffold 退出码 2，不产出任何文件；向上报告输入问题 |
| 找不到 output_contract | scaffold 退出码 3，**仍写出**最小保底 result.json（case_id+status=partial+notes 说明契约缺失）与空 contract_map.json；后续按平台默认契约（case_id/status/notes）手工补齐 |
| 契约为字符串/列表/嵌套等异常形态 | scaffold 内置多形态解析（JSON Schema / 扁平 dict / 描述列表 / 逐行字符串），解析结果与形态记录进 contract_map.json 的 `contract_shape`；解析不到字段时视同契约缺失处理并如实记录 |
| 渲染失败或校验不过 | preview_render 退出码 6，失败原因写入 `render_error.json`；修复稿件或参数后重跑，**禁止手写假 preview 充数** |
| 验收门 FAIL | 退出码 5，`gate_report.json/md` 列出**全部**失败项；逐项修复后重跑，不过门不交付 |
| 报告/文件写出失败 | 各脚本以退出码 4/6 报告，检查输出目录权限与磁盘 |

## 最小合成示例说明

`examples/` 内含一个完整合成示例（**非正式案例结果**）：
`case.json` 带嵌套 JSON-Schema 形态 `output_contract`（10 个字段，含
string/integer/number/boolean/array/enum），`manuscript.md` 为一篇合成的
成果转化推介书。`examples/expected/` 保存真实运行输出：契约映射、脚手架、
HTML/SVG 预览、回填后的 `result_final.json`、PASS 的验收报告，以及一个
负向测试（删必填字段 + 布尔写成 `1` + 引用不存在路径 → 验收门 FAIL，
退出码 5）。运行命令与结果见 `examples/README.md`。

## 局限

- Markdown 渲染只覆盖常用子集（标题/列表/表格/加粗/斜体/行内代码/代码块/
  引用/段落），不支持的语法按段落原样渲染，不报错也不保证美观；
- SVG 预览是逐行等宽文本排版，不是真实排版引擎，超长行截断显示；
- 契约字符串形态的解析基于启发式正则，极不规则的表述可能解析不到字段
  （此时如实降级为「契约缺失」而非猜测）；
- 验收门是机械检查：能保证结构、类型、路径、status 一致性，不能保证内容
  质量与事实正确性；
- 路径存在性检查依赖交付时刻的文件系统状态，跨机器搬运产物后需重新过门。
