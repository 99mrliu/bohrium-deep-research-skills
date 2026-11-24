# 遗漏与缺口报告（Omission & Gap Report）

- case_id：`synthetic-coverage-001`
- 备注：SYNTHETIC teaching data
- 期望数据库：crossref, europepmc, publisher
- 有材料的数据库：crossref, europepmc, publisher
- 缺席数据库：（无）
- 台账条目总数：16

每条目包含：类型、严重级、证据定位、影响陈述（「由于该缺口，用户无法得出什么结论」）。任何缺口均未被静默吞没。

## gap-0001 — field_systematic_gap（warning）

- 数据库：`crossref`
- 证据 db：`crossref`
- 证据 field：`pmcid`
- 证据 locator：`coverage_matrix cells[crossref][pmcid]=0 over 2 records`
- 影响：字段 pmcid 在 crossref 的 2 条记录中 0 次提供：跨库合并时该字段对 crossref 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0002 — field_systematic_gap（warning）

- 数据库：`crossref`
- 证据 db：`crossref`
- 证据 field：`pmid`
- 证据 locator：`coverage_matrix cells[crossref][pmid]=0 over 2 records`
- 影响：字段 pmid 在 crossref 的 2 条记录中 0 次提供：跨库合并时该字段对 crossref 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0003 — field_systematic_gap（warning）

- 数据库：`europepmc`
- 证据 db：`europepmc`
- 证据 field：`issue`
- 证据 locator：`coverage_matrix cells[europepmc][issue]=0 over 2 records`
- 影响：字段 issue 在 europepmc 的 2 条记录中 0 次提供：跨库合并时该字段对 europepmc 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0004 — field_systematic_gap（warning）

- 数据库：`europepmc`
- 证据 db：`europepmc`
- 证据 field：`pages`
- 证据 locator：`coverage_matrix cells[europepmc][pages]=0 over 2 records`
- 影响：字段 pages 在 europepmc 的 2 条记录中 0 次提供：跨库合并时该字段对 europepmc 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0005 — field_systematic_gap（warning）

- 数据库：`europepmc`
- 证据 db：`europepmc`
- 证据 field：`reference_list`
- 证据 locator：`coverage_matrix cells[europepmc][reference_list]=0 over 2 records`
- 影响：字段 reference_list 在 europepmc 的 2 条记录中 0 次提供：跨库合并时该字段对 europepmc 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0006 — field_systematic_gap（warning）

- 数据库：`europepmc`
- 证据 db：`europepmc`
- 证据 field：`volume`
- 证据 locator：`coverage_matrix cells[europepmc][volume]=0 over 2 records`
- 影响：字段 volume 在 europepmc 的 2 条记录中 0 次提供：跨库合并时该字段对 europepmc 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0007 — field_systematic_gap（warning）

- 数据库：`publisher`
- 证据 db：`publisher`
- 证据 field：`abstract`
- 证据 locator：`coverage_matrix cells[publisher][abstract]=0 over 1 records`
- 影响：字段 abstract 在 publisher 的 1 条记录中 0 次提供：跨库合并时该字段对 publisher 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0008 — field_systematic_gap（warning）

- 数据库：`publisher`
- 证据 db：`publisher`
- 证据 field：`pmcid`
- 证据 locator：`coverage_matrix cells[publisher][pmcid]=0 over 1 records`
- 影响：字段 pmcid 在 publisher 的 1 条记录中 0 次提供：跨库合并时该字段对 publisher 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0009 — field_systematic_gap（warning）

- 数据库：`publisher`
- 证据 db：`publisher`
- 证据 field：`pmid`
- 证据 locator：`coverage_matrix cells[publisher][pmid]=0 over 1 records`
- 影响：字段 pmid 在 publisher 的 1 条记录中 0 次提供：跨库合并时该字段对 publisher 系统性缺失，用户不能据此字段比较或筛选该库记录。

## gap-0010 — hitcount_mismatch（warning）

- 数据库：`crossref`
- 证据 file：`crossref_response.json`
- 证据 locator：`message.total-results=3 vs items=2`
- 影响：crossref 声明命中总数 3，实际返回 2 条，且无翻页/游标证据：未返回部分不可见，用户不能断言已覆盖全部命中。

## gap-0011 — identifier_conflict（warning）

- 数据库：`crossref,publisher`
- 证据 identifier：`doi:10.99955/syn.2021.0002`
- 证据 locator：`crossref_response.json,publisher_records.json`
- 影响：标识符 doi:10.99955/syn.2021.0002 在不同来源间元数据冲突（year: crossref=2021; publisher=2022）：已列出待仲裁、未静默合并；仲裁前用户不能确信其规范元数据。

## gap-0012 — import_state_gap（warning）

- 数据库：`multi`
- 证据 file：`import_state.json`
- 证据 identifier：`doi:10.99955/syn.2021.0777`
- 证据 locator：`imported_ids 中声明但检索响应中不存在`
- 影响：增量导入状态与检索响应不一致（claimed_not_in_responses：doi:10.99955/syn.2021.0777）：导入集与检索集存在偏差，用户不能断言二者一致。

## gap-0013 — mechanical_copy（warning）

- 数据库：`crossref,europepmc`
- 证据 dbs：`crossref,europepmc`
- 证据 locator：`task.md / case.json query evidence`
- 证据 query：`graph neural network catalyst screening`
- 影响：同一检索式被逐字发送至语法能力不同的数据库（crossref、europepmc）：各库的字段检索能力未被利用，召回可能系统性偏低或偏离预期。

## gap-0014 — query_evidence_missing（info）

- 数据库：`publisher`
- 证据 db：`publisher`
- 证据 locator：`no query string found in case.json / task.md / envelope`
- 影响：数据库 publisher 缺少检索式/请求参数证据：无法复核其检索编排是否合理，该库覆盖度无法归因，用户不能断言检索是按预期执行的。

## gap-0015 — referenced_not_retrieved（warning）

- 证据 file：`reference_graph.json`
- 证据 locator：`reference_graph.nodes (doi=10.99955/syn.2020.0999)`
- 证据 node：`n3`
- 影响：引用图节点 n3 未被任何来源检索到：引文追踪存在断点，被引/引用文献可能遗漏，用户不能断言引用网络已闭合。

## gap-0016 — single_source_only（info）

- 数据库：`europepmc`
- 证据 identity：`pmid:38000002`
- 证据 locator：`europepmc_response.json`
- 影响：文献 pmid:38000002 仅出现于 europepmc：无第二来源交叉验证，其存在性与元数据可信度依赖单一来源。

