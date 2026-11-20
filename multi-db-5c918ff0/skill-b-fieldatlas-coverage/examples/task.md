# 任务（合成示例，非真实案例）

> 本文件配合 `case.json` 使用，全部数据为虚构合成示例，仅用于 skill 自检。

对 `/input` 下三个来源（Crossref 原始响应、EuropePMC 原始响应、出版商原始响应）
的题录记录执行跨库字段标准化与覆盖缺口审计：

1. 按映射表把各来源记录归一化为字段卡片，区分 missing / unknown / not_provided
   三级缺失语义（不得混写）；
2. 输出库 × 字段覆盖矩阵，识别只在单一来源出现的文献（按 DOI 或归一题名+年份
   精确判定）与三个库均不提供的系统性缺口字段；
3. 建立失败/异常状态台账（零结果、schema 漂移、撤回标记、无法解析文件等），
   每类给出处置建议；
4. 与 `import_state.json` 做增量导入对账，输出 already_imported /
   new_candidates / conflicting_updates 三类清单；
5. 按 `case.json` 的 output_contract 生成 `/app/output/result.json`，附 coverage_report.md。

全程离线：不得声称执行任何真实联网查询。
