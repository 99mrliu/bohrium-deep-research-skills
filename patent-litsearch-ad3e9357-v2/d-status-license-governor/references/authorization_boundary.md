# 授权边界：绿/黄/红分级与能力降级

> 本文件是 `legal-status-license-governor` 技能的许可治理正文。所有示例均为合成示例 / 虚构。

## 1. 来源 license 字段

`sources.json` 中每个来源除 `tier` 外必须携带：

| 字段 | 取值 | 含义 |
|---|---|---|
| `access` | `public` / `registration` / `paid` / `restricted` | 获取门槛 |
| `display_scope` | `full` / `fields_only` / `citation_only` / `none` | 可展示范围 |
| `retention_days` | 非负整数 | 数据留存期限（天），0 表示不得留存 |
| `confidentiality_note` | 文本 | 保密要求 |

## 2. 绿/黄/红定义

- **绿 green**：`access=public` 且 `display_scope=full`。可全文检索、引用、展示。
- **黄 yellow**：`display_scope∈{fields_only, citation_only}` 或 `access=registration`；**license 字段缺失或无法识别的来源一律按黄级处理直至澄清**。
- **红 red**：`access∈{paid, restricted}`（含登录墙商业库）或 `display_scope=none`。

## 3. 各级能力边界

| 级别 | 可展示范围 | 留存 | 作为法律状态依据 |
|---|---|---|---|
| 绿 | 全文 | 按 `retention_days` | 仅当其 tier 同时为 register/official_gazette |
| 黄 fields_only | 仅许可字段（题录级），不展示原文全文 | 按 `retention_days` | 只能支撑「未核验」 |
| 黄 citation_only | 仅引述其存在与题录级信息 | 按 `retention_days` | 只能支撑「未核验」 |
| 红 | 不得展示任何内容 | 不留存 | 不得作为依据 |

注意：**颜色（许可）与 tier（证据层级）是两个正交维度**。一个公开的转载页是绿级或黄级许可，但其 tier=repost，仍然不能支撑法律状态断言。

## 4. 能力降级方案模板（由 `license_tiers.py plan` 自动生成）

- 红级 → `do_not_fetch`：不抓取、不登录；仅在结果中声明该来源存在并标注「无法访问」。
- 黄级 fields_only → `fields_only`：仅提取并展示许可字段，不展示原文全文。
- 黄级 citation_only → `cite_existence_only`：仅引用其存在与题录级信息。
- license 未知 → 按黄级处理直至澄清，并在 `uncertainty` 中声明。

交付时随 `result.json` 附能力降级 checklist（6 项，见 `degradation_plan.json` 的 `checklist` 字段），逐项核对后方可离场。

## 5. 禁止事项

1. **不绕付费墙/登录墙**：不使用他人账号、不利用漏洞、不抓取登录墙后的商业数据库内容；
2. **不上传受限数据**：不将红/黄级来源的受限原文上传到第三方服务（含外部 LLM、翻译、摘要接口）；
3. **不展示受限库原文**：红级来源的任何原文（含改写式转述其独有内容）不得出现在交付物中；
4. **不超期留存**：超过 `retention_days` 的缓存必须删除；
5. **不把黄/红级来源当作登记依据**：法律状态断言必须回溯到 register/official_gazette 级来源。
