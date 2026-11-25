# 四项 source-conditioned benchmark-DRAFT 编写协议

## 目标与非目标

目标只有一个：让每道题的**源是谁、哪个递归节点、哪个参考答案元素、哪个原子、哪段精确引文**可复核，并诚实暴露缺口。不是建立通用 ledger/dashboard，不生成排名或虚构实验/DSH 成绩。组织方 revision2 的源是实际段落/表格文字，不是 PDF 像素 gold；像素坐标不得混充本协议的 node locator。

## 人工必须承担的语义工作

1. **确认源身份。** 只把 case 指定的真实材料作为事实边界；看清文件名、bytes SHA256、路径、段落/表行、实际可选 page。域名标签、文件名暗示和模型记忆都不是证据。若 case 提到的文件不在输入中，列缺失而不是编造。
2. **选择四道可从该源判读的任务。** 每题任务、输入范围、答案元素、0/1/2 规则要与源兼容。避免要求外部常识才能填写的事实，避免材料只能部分支持却写成完整事实。没有足够材料时宁可 partial。
3. **先拆答案元素，再写原子。** 元素是最小独立判分命题（对象+关系+值/属性+必要条件），不是随意切碎关键词，也不能把一个多命题段落压成一个“全覆盖”元素来绕过覆盖检查。每个实质元素至少一个 atom 显式指向它。
4. **每原子只承担一个断言。** 数字与单位保持同一关系，否定/未报告不能被改写为肯定或估算。需要两个段落共同支撑的结论拆为多个 atom，并把它们映射到同一答案元素；不得拼接跨节点 quote。
5. **人工裁决而非字符串联想。** `atom.reason` 解释元素—原子对应；`evidence.reason` 解释主语、谓语、对象、单位、条件、时间、否定、表格行与列范围为何相符。检查引文上下文是否被截去限定语。脚本无法判断这些理由是否真实。
6. **0/1/2 必须可执行。** 通常 0=核心任务未满足或证据失效；1=仅部分元素正确/可追证据，或存在明确限定缺口；2=所有实质元素正确、范围一致且原子证据完整。把真实差异写进 criterion，不在这三个字段里预填得分。
7. **诚实元数据。** `difficulty` 由推理步数、表格定位、限定条件等实际任务特点决定；`data_license` 只记录已知许可/来源条件，未知就写未知。`uncertainty` 记录语义裁决、冲突、缺页、未报告；`change_records` 说明真实改动，不能编出对照增益或分数。

## 原子证据循环

对每一项依次执行：

1. 读 task 与 scope，回到 source map 打开声明节点，并核对附近真实节点防止断章取义。
2. 写 reference answer elements，人工检查是否覆盖任务全部实质要求。
3. 为每个元素写 atom id/text/type 和 `answer_element_ids`，选择唯一证据 node。
4. 从该 node 复制连续 quote。若非空行/全宽字符造成表面差异，只能依靠 NFKC/空白折叠；如须改词、改数、换算、跨节点拼接，应重写原子或承认不支持。
5. 检查每个数字、百分号和标识符。默认数值规则故意保守：例如 atom 的 `0.50` 不因 quote 的 `50%` 自动通过，`18` 不自动满足 `18%`，`12 ms` 也不在只有 `9 ms` 的 quote 中通过。可由 agent 另写正确支持的 atom，不应轻易使用 warning 开关。
6. 填两层 reason，跑 gate，逐个修复 `uncovered_answer_element`、`orphan_answer_mapping`、`orphan_node`、`quote_not_in_declared_node`、`unsupported_numeric_atom`、`zero_atoms`。
7. 四项目都通过后，再对语义做人工/模型复查；有未解决疑点则保留 uncertainty，必要时 partial。通过后修改任何草稿/材料，都必须重新索引与跑 gate。

## 特殊边界

- **未报告：** 只有源明确陈述未报告时才能作为 absence 原子；若仅阅读者没找到，应写“当前所读节点未确认”，列 uncertainty，不能形成事实断言。
- **冲突：** 不应挑一个节点掩盖另一个。任务范围允许时每方拆 atom，答案与 uncertainty 保留冲突；单一 gate 不裁决谁更可信。
- **表格：** locator 指示行类型不自动重建复杂表头。合并单元格、跨行表头和 caption 需要 agent 读取实际 JSON 路径并写清裁决，必要时多 atom。
- **页码：** 只使用实际 page 字段；null 就保持无页声明，不能从索引顺序猜页。
- **空白/NFKC：** 是词法等价规则，不是标点、单位、同义词、数字精度或科学语义等价规则。
- **布尔/数值 JSON：** source map 不把它们伪造成文本字符串。如果任务必须引用这些值，应说明本工具边界并人工保留真实 path，不能造 quote。
- **不支持的材料：** PDF、二进制 Office、图片不进入此文本索引；若 case 必须依赖其内容，说明限制，不能声称已经索引所有材料。

## 部分完成的最小诚实输出

越早越好地保留原 case_id、全部合同字段和真实已有内容。partial 至少说明：

- 已完成到哪一 item/answer element/node，已发生的脚本退出码；
- 缺哪些材料、原子、人工语义复核或时间；
- 任何失败 quote/数字/哈希是否仍未修；
- `sources` 仅列真实读过或索引过的文件，`limits` 和 `uncertainty` 不空，`change_records` 记录因此保留 partial。

`--allow-partial` 不是通过开关：`success=false`，`status=partial`，已知 gate/合同失败写入 `limits`。最终 complete 的条件没有例外：恰好四项、每项覆盖完整且原子通过、当前字节新鲜、合同所有字段合格。

## 完全合成示例与可复核方式

`examples/case.json`、`task.md`、`materials.json`、`draft.json` 共同组成完整 SYNTHETIC 四项目，覆盖全宽数字、空白折叠、表格行、递归嵌套、有/无 page、未报告、多个答案元素。运行：

```bash
examples/run_example.sh [output-directory]
```

真实调用三个脚本，并制造改 quote 与删 atom 两个负例，要求特定错误码和退出 1；还检查负例 finalizer 不创建 result。所有结果留在调用方目录或 mktemp，技能包不含生成输出。技术通过仅证明该 synthetic fixture 的结构与词法行为，不证明科学正确、语义独立有效或 DSH 得分。
