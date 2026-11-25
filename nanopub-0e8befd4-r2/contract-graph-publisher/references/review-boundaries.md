# 复核边界与失败判定

## 1. 本 Skill 实际复核什么

- 读取 `/input/case.json`、`/input/task.md` 和 resources；不从 task 散文发明字段。
- 原始 case_id 与 output_contract 保留，最终 result 从磁盘独立回读，顶层键按字段列表精确比较。
- JSON 拒绝重复键；manifest 不得额外声明字段；别名映射后仍检查引用。
- claim→evidence→source 和 publication→claim ID 完整，ID 不重复。
- 仅按 manifest 交付 JSON、JSONL 或 RDF；JSON 请求出现 RDF 文件属于交付失败。
- work 在规范化之前已有诚实 partial；完成前不把结果写成成功。非法契约没有安全 schema 可写 partial，故只留错误记录。
- RDF 时四个 named graphs 分离，Head 有三个 part links，provenance 引用 assertion，pubinfo 引用 publication。
- 负/条件/hedged claim 以 reified statement 表达，扫描所有图确保没有直接原 S-P-O 三元组。
- pubinfo 明示本地、未注册、非 Trusty；创建者/license/created 只来自明确输入。
- 20 条 SYNTHETIC RDF 示例验证 TriG/JSON-LD 模型回读和 graph/quad 计数；负例验证额外 EXACT 键被拒绝。

## 2. 不能据此声称什么

本工具**没有**运行完整 W3C TriG/JSON-LD conformance suite，也没有 `rdflib`、网络解析器、SHACL 引擎或独立第三方验证。其 TriG 和 JSON-LD 回读是只覆盖生成器输出子集的严格解析/结构检查。可以说“通过本地结构自检”，不能说“完整 W3C 验证通过”。

本地 URN 不是已注册 nanopublication URI，也不是 Trusty URI。未连接 nanopub 注册服务，未进行签名、可信时间戳、内容寻址、URI 解析验证。`validation-report.json` 中 `network_requests=0` 与资源上限 64 requests / 900 sec 不矛盾：64 是上限而非必须消耗量。

合成 claim、example.org IRI 和 synthetic locator 只用于测试；不能包装成真实文献结论。此 Skill 也不判断 claim 是否真实，不做文献抽取质量评分、覆盖矩阵、数值演算或竞赛裁决。

当前输入适配边界是文档化的扁平规范化 claim/evidence/source 形状和顶层字段映射。复杂 JSON Schema 条件、嵌套任意转换、复杂 RDF 词法形式、blank nodes 和多 nanopub 聚合没有通用解析保证；遇到这类要求应明确报告，而不是静默降级或宣称支持。

## 3. 发布前人工复核清单

1. 当前目录确实是要发布的 `contract-graph-publisher`，没有读取其他 bundle 的 schema 或样例。
2. `SKILL.md` frontmatter 只有 name/description，name 等于目录名；description 明确触发和不触发。
3. 平台命令只使用 `/input`、`environment/resources.yaml`、`/app/work`、`/app/output` 或相对样例路径，无个人绝对路径。
4. 原 schema 未被辅助字段污染；负例输出目录为空，错误报告可读。
5. JSON 示例 expected 与 actual 相同，且没有 RDF；RDF 示例确实由显式请求生成。
6. RDF 至少逐图查看 Head、一个 qualified statement、provenance 链和 pubinfo 状态，并阅读验证限制。
7. 创建者、license 和日期没有由工具自动补入。样例中未提供它们，故 pubinfo 只有 publication 引用和两项本地状态。
8. 所有文档和产物均 UTF-8 文本，无符号链接/二进制，文件数、单文件和总大小满足限制；运行语法检查不产生 `__pycache__`。
9. 测试报告记录真实命令、退出码、计数和限制，不将“退出 0”扩大解释为外部注册或语义真实性。
10. 不执行 git commit/push。
