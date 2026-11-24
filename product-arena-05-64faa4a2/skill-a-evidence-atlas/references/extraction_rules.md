# 台账字段定义与提取规则说明（atlas_scan）

## 台账字段（atlas.json）

- `meta`：工具名/版本、输入目录、文件/参数/冲突计数、`notes`
  （结构化解析使用记录与降级声明）。
- `files[]`：`relpath`、`size_bytes`、`sha256`、`type`（按扩展名猜测）、
  `status`（parsed / unparsed）、`note`（截断、未解析原因等）、`lines`。
- `parameters[]`：
  - `id`：P001 起的稳定编号（按 文件→行→列→类别→名称 排序后赋值，
    同输入同编号）；
  - `name`：参数名；flag 类带 `flag:` 前缀；
  - `value`：取值字符串（拆分单位后）；
  - `unit`：单位（启发规则，可能为空）；
  - `kind`：parameter / flag / version / url / path；
  - `source`：`file` + `line`（1 起；结构化解析定位失败时为 0）；
  - `evidence`：原文行（截断至 240 字符）。
- `conflicts[]`：规范化后同名参数的多处不同取值及其全部 file:line。
  规范化规则：小写、`-` 与 `_` 互换等价。写法不同但语义相同的参数
  （lr / learning_rate）**不**自动归并。
- `unparsed[]`：未解析文件及原因。

## 会被提取的模式

1. **键值对**（kind=parameter）
   - 行内 `key=value`（含日志中段的 `seed=42`；键允许 `[\w.\-]`）；
   - 行首 `key: value`（yaml/ini/md 风格；键必须紧跟冒号与空白，
     以减少散文误提）。
   - 布尔词（true/false/yes/no/on/off/none/null）不作为参数提取。
2. **命令行 flag**（kind=flag）：`--name value`、`--name=value`、
   `-n value`；值以 `-` 开头或为空时跳过。
3. **版本号**（kind=version）
   - 已知软件名 + 版本：python/pytorch/torch/tensorflow/tf/cuda/cudnn/
     numpy/pandas/scipy/scikit-learn/sklearn/transformers/deepspeed/
     mmcv/apex/xgboost/lightgbm 后接 `x.y[.z]`（分隔符可为空格/=/-//）；
   - 独立 `v` 前缀版本：`v1.2.3`。
   - 普通小数（如 0.0003）**不会**被误判为版本号。
4. **URL**（kind=url）：`http(s)://…`。
5. **绝对路径**（kind=path）：`/a/b/c` 形式；URL 先抽取并掩蔽，
   不重复计入其路径部分。
6. **seed**：不单独设规则，由键值对/flag 模式自然覆盖。

## 单位启发规则

值为"数值 + 已知单位后缀"时拆出单位。已知单位：
`% ms s sec min h hr hrs B KB MB GB TB KiB MiB GiB Hz kHz MHz GHz W V G M`。
其余情况 `unit` 为空——空单位**不**表示无单位，只表示脚本无法判断。

## 结构化解析与降级行为

- **JSON**：用标准库 `json` 解析并打平为 dotted 键；行号通过在原文中
  同时匹配末段键名与值串定位，定位失败记 `line: 0`。解析失败降级为
  行解析并在 notes 注明。
- **YAML**：环境有 PyYAML 时用 `safe_load` 解析并同样打平定位，notes 注明
  "使用 PyYAML 结构化解析"；无 PyYAML 或解析失败时降级为行解析（仅行首
  `key: value`，嵌套结构可能丢失），notes 注明降级及原因。
- **INI/TOML(简)/log/txt/md/csv/代码**：一律行解析。CSV 不做列级语义解析，
  仅提取行内键值模式。
- **二进制/非 UTF-8/不支持扩展名**（含 PDF、图片、权重、压缩包）：
  不解析，记入 `unparsed` 并注明原因；哈希仍登记，可供完整性核对。
- **大文件**：超过 8MB 只解析前 8MB，files[].note 注明截断。

## 确定性保证

无时间戳、无随机数；文件按路径排序遍历，参数按键排序去重后按
（文件, 行, 列, 类别, 名称）排序赋 ID。同一输入目录在任何平台上
得到逐字节一致的 atlas.json 与 atlas.md。

## ledger_check 比对与排除规则（配合阅读）

- token 抽取：整数/小数/版本号式 `x.y.z`/科学计数法/百分号；
  左边界排除 `[\w.\-/]`，故 `ResNet-18`、`v1.2.3` 的尾段不会被拆出。
- 排除区域：台账 ID `[[P003]]`、file:line 引用（含 8:1:1 式比例）、
  URL、Markdown 标题行首的章节编号、裸 `P003`。
- 命中规则（满足其一即 BOUND）：与台账 value 字符串相等；浮点相等；
  百分号形式与台账小数的 ×100 等价（80% ↔ 0.8）；evidence 词边界命中
  且该参数自身数值与 token 一致（防止同行无关数字造成噪声命中）。
- 退出码：0 全部 BOUND；1 存在 UNSOURCED；2 运行错误。
