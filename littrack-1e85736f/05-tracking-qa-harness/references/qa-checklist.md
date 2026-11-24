# QA 检查清单（tracking-qa-harness）

本清单定义一次文献追踪运行产出（result.json）在**交付前**必须通过的机器可复核
质量门禁。执行顺序固定：契约 → 证据 → 新鲜度 → 指标 → 汇总。任一门禁 fail 即阻断
交付，修复后**从头重跑全部四个门禁**（修复可能引入新错误）。

## 门禁 1：输出契约校验（contract_validate.py）

- [ ] `case_id` 存在、非空白，且与 case.json 的 `case_id` 完全一致
- [ ] `output_contract` 列出的每个字段都存在且非 null（缺字段即 fail 并逐个列出）
- [ ] 字段类型符合期望（case_id:str / window:dict / new_items,sources,uncertainty,
      change_records:list / metrics,qa:dict）
- [ ] 字符串字段非空白；`status` ∈ {complete, partial, failed}
- [ ] sources / uncertainty / change_records 即使不在契约中，也建议存在（缺失记 warn）

## 门禁 2：证据 locator 抽查（evidence_spotcheck.py）

对 `new_items` 的**每一条**：

- [ ] `locator` 形如 `相对路径#/json/pointer` 且可解析（文件存在、指针不越界、
      不越出案例目录）——不可解析即 fail
- [ ] DOI 归一化后与源记录完全一致（大小写、doi.org 前缀差异不视为差异）
- [ ] 标题归一化后一致（子串近似记 warn，不一致记 fail）
- [ ] `published_date` 与源记录任一日期字段完全一致（同年月/同年记 warn）
- [ ] 首作者 family name 出现在源记录作者列表中（缺失记 warn）

## 门禁 3：新鲜度与防旧文重报（freshness_check.py）

- [ ] 每条 `published_date` 落在 case.json `window.start ~ window.end` 闭区间内；
      窗口外条目必须带 `"backfill": true`（降级为 warn，且应在 change_records 说明）
- [ ] 每条 DOI 不在 previous_snapshot 中（出现即 fail：旧文重报）
- [ ] result 内部无重复 DOI（fail）
- [ ] `result.window` 与 `case.window` 一致（不一致记 warn）
- [ ] previous_snapshot 缺失时记 warn 并如实披露"去重检查未执行"

## 门禁 4：质量指标（metrics.py）

- [ ] 计算 window_coverage / dedup_rate / alert_precision / quarantine_rate /
      locator_resolvability（定义见 metrics-definition.md）
- [ ] 不可计算的指标输出 null 并写清原因，**不得编造数字**
- [ ] 指标异常（如覆盖率 < 1、隔离率 > 0）必须在 qa_report 与 result.uncertainty
      中如实说明原因

## 收口：qa_report.py

- [ ] overall_status = fail 时，blocking_items 逐条列出（tool / id / message / locator）
- [ ] 全部 warn 与不可计算项进入 uncertainty，诚实披露
- [ ] QA 结论（含报告路径）写入 result.json 的 `change_records`（或专门 qa 字段）

## 通用纪律

- 全程离线：任何脚本不得发起网络请求；所有字段值必须来自案例材料；
- 每个断言必须能经 locator（文件 + JSON 路径）回溯复核；
- 修复循环：fail → 修复 result.json → 重跑全部门禁 → 直至 pass；
  无法修复的阻断项 → `status: "partial"` + 在 uncertainty 说明限制，**不得硬交付**。
