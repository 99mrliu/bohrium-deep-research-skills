# 宏包冲突对与加载顺序规则表

本文件同时供人阅读与脚本解析：`scripts/pkgconflict.py` 直接读取下面两张
markdown 表（列名固定，改动列名需同步改脚本）。规则只覆盖高置信度的常见
情形；拿不准时宁可只写进 uncertainty，不要臆断。

## 加载顺序规则（机器可读表）

`constraint` 取值：`last_except`（应最后加载，peers 为例外）、
`after`（须在 peers 之后）、`before`（须在 peers 之前）。

| package | constraint | peers | note |
| --- | --- | --- | --- |
| hyperref | last_except | cleveref | hyperref 重定义大量内部命令，应在稿件显式加载的宏包中最后出现；cleveref 是公认的少数例外 |
| cleveref | after | hyperref | cleveref 挂钩 hyperref 的引用机制，必须先有 hyperref |
| cleveref | after | amsmath | 同时使用 amsmath 时，cleveref 应在其后加载以正确接管公式编号 |
| geometry | before | hyperref | 先定页面尺寸再加载 hyperref，避免链接锚点位置错误 |
| caption | after | hyperref | caption 与 hyperref 的锚点补丁要求在 hyperref 之后 |
| bookmark | after | hyperref | bookmark 是 hyperref 书签机制的增强，必须在其后 |

## 已知冲突对（机器可读表）

| package_a | package_b | severity | advice |
| --- | --- | --- | --- |
| natbib | cite | error | 两套引用压缩/排序机制互斥，按模板指定二选一；模板带 \\bibliographystyle 约定时以模板为准 |
| subfigure | subcaption | error | 二者都接管子浮动体定义且互不兼容，迁移到现代模板一律改用 subcaption |
| subfig | subcaption | error | subfig 与 subcaption 定义同名命令 \\subfloat，二选一（推荐 subcaption） |
| amsthm | ntheorem | warning | 两套定理环境机制重叠，保留模板指定的一套 |
| mathptmx | newtxtext | warning | 旧 Times 字体方案与 newtx 叠加会重复改字体，保留 newtx 系列 |
| geometry | fullpage | error | 二者都直接改写页面尺寸参数，删除 fullpage，统一交给 geometry |
| enumerate | enumitem | warning | enumerate 的旧式标签语法与 enumitem 部分冲突，迁移时统一到 enumitem |

## 使用要点

- 顺序规则只针对稿件导言区**显式** `\usepackage` 的相对顺序；模板类内部
  的 `\RequirePackage` 不参与排序判定，但参与"与模板类重复"判定。
- "与模板类重复"分两级：选项一致只是冗余（warning，建议删除稿件侧）；
  选项不一致在迁移后会触发 `Option clash for package ...`（error 级，
  必须处理，可用 `\PassOptionsToPackage` 过渡）。
- 模板禁用宏包的判定依赖类文件中的 `\@ifpackageloaded{...}{\ClassError...}`
  模式；检出后处置建议一律是"移除并改用模板自带机制"，不得绕道保留。
- 本表不穷举。未覆盖的组合不意味安全；脚本没报的问题由 Agent 在编译
  日志与版式目检中兜底。
