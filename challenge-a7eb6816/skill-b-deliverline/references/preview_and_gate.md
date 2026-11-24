# 预览渲染与验收门设计

本文说明 deliverline-contract-render 技能中 `scripts/preview_render.py` 与
`scripts/deliverable_gate.py` 的设计与常见失败处置。

## 1. 为什么需要可检查预览

写作产物（Markdown）交付后，评审/用户需要「真正看到它」。裸 Markdown 在
很多环境里不会渲染；而引入第三方渲染器在评测机上不被允许。因此本技能用
**纯 Python 3 标准库**产出两种互补预览：

- **preview.html**：自包含（内联 CSS、无外部资源），`lang="zh-CN"`，双击
  即可在浏览器检查成稿样貌；
- **preview_pageN.svg**：逐行等宽文本 + 固定行数分页，用于快速核对「稿件
  的每一行确实进入了交付物」，且 SVG 本身是文本，可被 diff/审查。

## 2. 渲染器支持的 Markdown 子集

| 语法 | 渲染 |
|---|---|
| `#`–`######` 标题 | `<h1>`–`<h6>`，标题纯文本记入校验清单 |
| `- ` / `* ` 无序列表、`1. ` 有序列表 | `<ul>` / `<ol>`（连续行聚合） |
| 管道表格（含 `|---|` 分隔行） | `<table>`，首行为 `<th>` |
| `**加粗**`、`*斜体*`、`` `代码` `` | `<strong>` / `<em>` / `<code>` |
| `> ` 引用 | `<blockquote>` |
| ` ``` ` 代码块 | `<pre><code>`，原样转义 |
| 其余 | 段落 `<p>` |

**设计取舍**：不支持的语法按段落原样输出，不报错、不崩溃——预览的目标是
「可检查」，不是完美排版。中文无需特殊处理：全程 UTF-8，HTML 声明
`charset="utf-8"`，CSS 字体栈含 PingFang SC / Microsoft YaHei / Noto Sans
CJK SC。

## 3. 渲染校验（防「假装成功」）

渲染完成不等于渲染正确。脚本在退出前做三项机械校验：

1. `preview.html` 存在且 ≥ 200 字节；
2. 稿件中**每个标题的纯文本**必须出现在 HTML 产物中（防解析器吞内容）；
3. 每个 `preview_pageN.svg` 存在且 ≥ 100 字节。

任一失败：写 `<outdir>/render_error.json`（含全部失败原因），退出码 6。
**禁止**在渲染失败后手写一个假 preview 充数——验收门只查存在性，查不出
内容真假，造假只能靠流程纪律杜绝。

### 常见渲染失败与处置

| 失败 | 原因 | 处置 |
|---|---|---|
| 退出码 2 | `--md` 路径错 | 检查稿件实际位置（默认约定 `/app/work/manuscript.md`） |
| 标题未出现在产物中 | 标题行内格式异常（如 `# **加粗**标题` 中 strip 逻辑未覆盖的记号） | 简化标题行内格式后重跑 |
| preview.html 体积过小 | 稿件为空或全是空行 | 检查写作流程是否真的产出了内容 |
| 退出码 6 且 render_error.json 缺失 | 输出目录不可写 | 检查 /app/output 权限 |

## 4. 验收门检查项（deliverable_gate.py）

按 `contract_map.json` 逐项机械检查，**不在第一个失败处停下**，报告列全部
失败项：

1. `case_id_match`：result 的 `case_id` 与 case.json 逐字节一致；
2. `field_present:*`：契约字段全覆盖（点分嵌套路径逐层下钻）；
3. `field_type:*`：严格类型——`isinstance(True, int)` 在 Python 中为真，
   因此显式排除：boolean 值不能通过 integer/number 检查，JSON `1` 也不能
   通过 boolean 检查；
4. `required_nonempty:*`：必填字符串去空白后非空；必填数组非空
   （`limitations` 例外，其空/非空由第 7 项管辖）；
5. `field_enum:*`：值在枚举内（如 `status ∈ {complete, partial}`）；
6. `artifact_exists:*`：deliverables/files/paths/artifacts/outputs 类字段
   中的每个字符串路径，相对 `--base-dir` 解析后真实存在；
7. `status_limitations_consistency`：`complete` ⇒ `limitations == []`；
   `partial` + 空 limitations 只记警告不判 FAIL。

退出码：**0=PASS，5=FAIL**；2=输入缺失，3=契约映射非法，4=result.json
非法，6=报告写出失败。

## 5. 常见 FAIL 与处置

| FAIL 项 | 典型原因 | 处置 |
|---|---|---|
| `case_id_match` | 回填时手敲 case_id、大小写/连字符错 | 从 case.json 程序化复制 |
| `field_present:title` | 回填脚本漏写字段 | 对照 contract_map 逐字段核对 |
| `field_type:reviewed` | 布尔写成 `1` 或 `"true"` | 改为 JSON `true/false` |
| `field_type:word_count` | 写成 `1200.0` 或 `"约1200字"` | integer 必须是 JSON 整数 |
| `required_nonempty:summary` | 占位空串忘记回填 | 回到写作流程补内容；补不了就 partial |
| `artifact_exists:*` | 预览渲染到了别的目录 / 搬运后路径失效 | 统一输出到 /app/output，过门前 `ls` 核对 |
| `status_limitations_consistency` | `complete` 但 limitations 没清空 | 解决 limitations 中的问题后清空；解决不了就改回 partial |

## 6. 确定性说明

三个脚本的输出均不含时间戳、随机数、绝对环境路径（报告中的路径来自命令
行参数本身），同一输入多次运行字节级一致，可直接纳入版本库做回归对比。
