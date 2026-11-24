# 字体安全策略

## 字体替换机制

PPTX 渲染时若找不到 run 指定的字体，查看器会静默替换（Windows 的 font
substitution 表、macOS 的 LastResort、LibreOffice 的替换表）。替换字体字宽不同，
最直接的表现是换行位置漂移、文本框溢出、表格列错位——换机"崩版"的头号来源。

## 白名单策略

- **主题字体优先**：不设置 `run.font.name`，文本继承模板 theme 的
  major/minor latin typeface。模板用 Office 默认主题时是 Calibri Light / Calibri，
  所有主流查看器都有度量兼容替代。
- **安全字体白名单**（edit_lint 内置）：Arial、Helvetica、Times New Roman、Times、
  Calibri(Light)、DejaVu Sans/Serif、Noto Sans/Serif（含 CJK SC）、PingFang SC、
  Microsoft YaHei、SimSun、Songti SC、Liberation Sans/Serif。
- 主题字体（从 `ppt/theme/themeN.xml` 解析）自动视为合法，不需要在白名单里。
- 任何显式字体不在（白名单 ∪ 主题字体）→ edit_lint error。

## font_probe 的角色

构建前探测环境：`fc-list` → 常见字体目录扫描 → honest `unknown`。
产出：安全字体可用/缺失清单、建议正文字体、风险列表（如"无 CJK 字体，中文
可能豆腐块"、"Arial 未检出，替换可能改变换行"）。风险写入 result.json 的
`uncertainties`，不假装环境可控。

## CJK 注意点

- 中西文混排时 CJK 字体缺失会让整行回退为豆腐块；font_probe 会单独检查 CJK。
- macOS 的 PingFang SC、Windows 的 Microsoft YaHei 互不通用——所以正文绝不
  硬编码它们，而是让主题字体 + 查看器 CJK 回退处理；必须显式时选 Noto Sans
  CJK SC（跨平台可安装）。

## 缺失处置

1. 发现缺失 → 不阻断构建，记风险。
2. 字号合规与字体无关，照常由 edit_lint 门禁。
3. 渲染验证（render_diff）用本机 soffice 实际渲染——字体替换后的真实样子会被
   PNG 度量（近空白页、渲染 hash）记录下来，作为换机前的底线证据。
