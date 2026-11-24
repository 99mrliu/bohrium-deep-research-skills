# 引用相关报错速查（bibtex / biber / LaTeX 日志 → 根因 → 处置）

citebuild.py 每轮从 .log/.blg 提取的警告与本表对应。处置动作一律由 Agent 执行。

## LaTeX .log 警告

| 日志特征 | 根因 | 处置 |
| --- | --- | --- |
| `Citation 'X' on page N undefined` | ① 键拼写与 .bib 不一致；② .bib 无此条目；③ bibtex/biber 尚未运行或运行失败；④ \bibliography 路径错误 | 先用 citeaudit 报告第 1 节定位引用点与候选键；确认是拼写（改 \\cite 键）还是缺条目（核实后补条目）；若键与条目都在，看 .blg 报错 |
| `Reference 'X' on page N undefined` | \\label 缺失、拼写不一致，或 \\label 所在环境未编号 | 对照 citeaudit 第 2 节的候选 label；确认 \\label 放在编号环境内（章节/公式/图表 caption 内） |
| `Label 'X' multiply defined` | 同一 \\label 键定义多次（复制粘贴常见） | citeaudit 第 2 节列出全部定义点；保留一处、其余改名并同步 \\ref |
| `There were undefined references` | 上述任一类问题的汇总行 | 不单独处置，追踪上面的具体条目 |
| `Empty \thebibliography` / `Something's wrong--perhaps a missing \item` | .bbl 为空：没有任何 \\cite 成功解析，或 \\bibliography 指向错误文件 | 检查 \\bibliography 参数与 .bib 文件名；查看 .blg |
| `Package natbib Warning: Citation(s) may have changed` | 引用编号在变动，需要再跑一轮 latex | 正常现象，citebuild 会继续迭代直至警告集合稳定 |

## bibtex .blg（`Warning--` / 错误行）

| 日志特征 | 根因 | 处置 |
| --- | --- | --- |
| `Warning--I didn't find a database entry for "X"` | .bib 中确实没有键 X | citebuild 归类为「缺条目」；核实后补条目或修正 \\cite 键 |
| `Warning--empty journal in X`、`empty year in X` 等 | 条目 X 缺该样式必需的字段 | citebuild 归类为「缺字段」；对照 references/bib-field-rules.md 核实后补全 |
| `Repeated entry---X` | .bib 中键 X 出现两次（后一个被忽略） | citeaudit「.bib 重复键」一节列出两处；合并由 Agent 决定 |
| `I couldn't open database file X.bib` | \\bibliography{X} 找不到 X.bib（路径/拼写） | 确认 .bib 相对主文件的路径；镜像构建目录已复制全部 .bib，若仍报错多为文件名不一致 |
| `I was expecting a ',' or a '}'` | .bib 语法错误：字段缺逗号、括号不配对、值未加括号 | 按行号修复 .bib 语法；citeaudit 的「.bib 解析异常」可辅助定位 |
| `I found no \citation commands` / `I found no \bibdata command` | 先跑了 bibtex 但 .aux 里没有引用（顺序错或全文无 \\cite） | 顺序应为 latex → bibtex → latex × 2（citebuild 已内置）；全文无 \\cite 时考虑 \\nocite |
| `Warning--to sort, need author or key in X` | alpha 等样式需要排序键 | 补 author 或加 `key` 字段 |

## biber .blg（`WARN/ERROR -` 行）

| 日志特征 | 根因 | 处置 |
| --- | --- | --- |
| `WARN - I didn't find a database entry for 'X'` | 同 bibtex 缺条目 | 同上 |
| `ERROR - BibTeX subsystem: ... syntax error` | .bib 语法错误（biber 比 bibtex 更严格，如不允许多余逗号外的问题） | 按报出的行号修复 |
| `WARN - Duplicate entry key 'X'` | 键重复 | 同 Repeated entry |
| biber 缓存报错（`recreate cache` 类） | biber 缓存目录损坏 | 删除缓存（`biber --cache` 给出的路径）后重跑；属环境问题，非稿件问题 |

## 通用收敛问题

- **警告集合在两轮之间来回变化**：多为 \\label/\\ref 写在长度变化的文本里
  （如目录、页码引用）。citebuild 在达到轮次上限仍不收敛时会如实报告
  `converged=false`，需人工排查。
- **编译产物污染工程**：所有编译在独立构建目录进行；若必须在原工程跑，
  先清理 .aux/.bbl/.blg 再重来，陈旧 .aux 是「警告不消失」的常见原因。
