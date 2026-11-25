# 动态输出契约与运行状态

## 1. 平台固定字段

最终 `/app/output/result.json` 必须保留原始 `case_id` 和：

- `status`：`success`、`partial` 或 `failed`，表示运行与契约完成度；
- `sources`：case/claims/task/paper 的逻辑相对路径、SHA-256、字节数；observations 内还有 quote/location；
- `uncertainty`：未读来源、定位问题、单位/方法限制、未完成任务或 SYNTHETIC 标记；
- `change_records`：early partial、复算、Agent 合并或错误的有序记录。

此外必须覆盖 `case.json` 中找到的 `output_contract` 全部声明字段。没有 verdict 的计算结果保持 partial；claim 的 null 是待 Agent 裁决，不得把它计作四级结论。

`success` 不要求所有 claim 都 supported。只要所有问题已由 Agent 覆盖、契约检查通过且没有未完成工作，含 contradicted/insufficient/partially_supported 的运行仍可为 success。

## 2. 支持形状

契约位置支持 `output_contract`、`outputContract`、`contract`、`output_schema` 等常见键及浅层嵌套；优先真实 case 中声明，不从 case 名称猜 schema。

- JSON Schema object：`type/properties/required/items/additionalProperties/enum/const` 和基本长度/数量/范围限制；
- 简单 dict：`{"claims":"list","status":"string","sources":"list"}`；`list/dict/str/int/float` 别名映射到 array/object/string/integer/number；
- 字段名 list：`["case_id","claims","status","sources","uncertainty","change_records"]`；
- descriptor list：`[{"name":"claims","type":"array"},...]`；
- 嵌套 properties/fields 会递归保留字段名。

claims/verdicts/results/answers/adjudications 等常见根字段名映射到完整 Agent claim records；声明 array 时输出 list，无固定 properties 的 dict/object 声明时输出以 claim_id 为键的字典。状态字段声明 object 时为 `{"state":...,"complete":...}`，string 时为状态字符串。

未知字段保持 null，出现在 verification 的 `unresolved_fields` 并触发 partial；不制造值来“适应”契约。自由文本契约不会被正则猜成字段。根 contract 非 object 时会包装并披露，因为平台仍要求 case_id/status/sources 等元数据。

closed schema (`additionalProperties:false`) 逐层报告额外字段。若 case 的 closed schema 漏掉平台强制字段，不会为通过 schema 而删除平台字段；contract error 会披露冲突。未实现的 JSON Schema keyword 以 warning 明说未校验，不声称完整 JSON Schema 实现。

## 3. Early partial 与错误路径

`run.py` 在校验 observation 前按动态契约写 result/verification/run-context/run-manifest。随后：

1. 读取 claims 与 observations，拒绝非法 n/events/CI/unit；
2. 计算 derived records、z 检验、Wilson CI，写 report 和 SVG；
3. 无 Agent verdict 时完成 partial draft；
4. 有 `--verdicts` 时做全 claim 合并与验证；
5. `finalize.py` 可在不重新计算的情况下合并后补 verdict。

缺少 observations 时 early partial 保留，`run.py` exit 1；没有 verdict 但 report 已完成时仍返回可读 partial。`build_report.py` 对非法输入 exit 1。正常完成与声明 partial 的 runner 可 exit 0，因此**必须读取 result 内 status，不能只信 shell exit code**。

所有计算是本地有界标准库操作；默认 soft budget 780 秒（参数允许1–850），为900秒总预算留余量。不会联网、安装包或启动模型请求。本流程遵循总64次模型请求预算，脚本本身不消耗模型请求。

## 4. 输出旁车

- `quantitative-report.json`：完整计算证据和统计方法边界；
- `effect-plot.svg`：从第一组实际比例检验派生的 Wilson 误差/效应图；
- `run-context.json`：finalize 所需 sources/uncertainty/change_records 和逻辑 artifact 名；
- `run-manifest.json`：状态、耗时、sources、artifacts、变化与 uncertainty；
- `verification.json`：动态契约、必需字段、claim 数、四级 verdict 与 Agent origin 检查。

这些旁车不替代 result 中的 case 要求字段。结构 pass 不是科学语义认证。最终 Agent 仍需读回 result，并核对关键原报值、分母、方向和独立复算。
