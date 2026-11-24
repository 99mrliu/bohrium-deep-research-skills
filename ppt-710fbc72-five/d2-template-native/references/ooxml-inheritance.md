# OOXML 模板继承参考（template-native-deck）

本文档解释本 Skill 审计的 OOXML 结构、占位符语义、替代决策表与审计裁决含义。
面向需要在 `audit_inheritance.py` 失败时定位问题的 Agent。

## 1. slide → layout → master → theme 关系解剖

一个 .pptx 是 zip 包。继承链全部通过 **relationship 部件**（`.rels`）表达：

```
ppt/slides/slideN.xml
  └─ ppt/slides/_rels/slideN.xml.rels
       Relationship Type=".../slideLayout" Target="../slideLayouts/slideLayoutK.xml"
ppt/slideLayouts/slideLayoutK.xml
  └─ ppt/slideLayouts/_rels/slideLayoutK.xml.rels
       Relationship Type=".../slideMaster" Target="../slideMasters/slideMasterM.xml"
ppt/slideMasters/slideMasterM.xml
  └─ ppt/slideMasters/_rels/slideMasterM.xml.rels
       Relationship Type=".../theme" Target="../theme/themeM.xml"
```

- Target 是**相对路径**，相对拥有该 .rels 的部件所在目录解析。
- "链解析成功" = 每个 r:id 都有对应 Relationship、每个 Target 都真实存在于包内。
  悬空（dangling）目标 = 页面在 PowerPoint 里可能打开但版式静默回退，必须判失败。
- 页顺序不取文件名排序，而取 `ppt/presentation.xml` 中 `sldIdLst` 的 r:id 顺序，
  经 `ppt/_rels/presentation.xml.rels` 解析到 slide 部件。

## 2. 占位符 idx 语义

- 版式（slideLayout）中的每个占位符有 `<p:ph type="..." idx="..."/>`。
- **缺省值**：`idx` 缺省为 **0**（标题占位符 `type="title"` 通常不写 idx，
  即 idx=0）；`type` 缺省为 **body**。
- 页面上的占位符 sp 通过 idx 与版式占位符配对；**页面上出现版式里不存在的 idx
  即"发明占位符"**，会脱离母版体系（位置/字体不再受版式控制），审计判失败。
- 页面占位符 type 与版式同 idx 的 type 不完全一致时只记 warning：
  OOXML 允许页面侧以更具体的类型继承（如 body/subTitle 变体），idx 存在即可。
- 常见 idx 约定（python-pptx 默认模板）：0=title/ctrTitle，1=body/subtitle，
  10/11/12 等用于第二内容区；日期/页脚/页码为 dt/ftr/sldNum。

## 3. 主题指纹方法（theme fingerprint）

- 主题部件 `ppt/theme/themeN.xml` 内含 `a:fontScheme`（majorFont/minorFont 的
  latin/ea typeface）与 `a:clrScheme`（dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink）。
- **指纹 = 主题部件原始字节的 sha256**。逐字节比较，不做 XML 规范化：
  语义相同但字节不同即视为"主题未被原样保留"，因为任何字节差异都意味着
  构建过程重写了主题（字体/颜色可能在其中被换掉）。
- python-pptx 对未触碰的 XML 部件逐字节往返稳定（已验证），因此
  "从模板直接构建"的产物应通过指纹比对；引入外来模板的产物必然失败。
- inventory 同时解析出 major/minor 的 latin+ea 字体名与全部主题色，
  供人读与排障；但**裁决只看指纹**。

## 4. 版式/占位符替代决策表

计划要求的资源缺失时，按表处理并**全部记录进 build_report.json**：

| 情况 | 处理 | 记录 |
|---|---|---|
| 计划 layout 名不在模板 inventory | 按回退链 `Title and Content → Title Only → Blank → 第一个版式` 选最近版式 | substitution kind=`layout_fallback` |
| 版式无 title 占位符但页面有标题 | 在版式内容区上方加纯文本框（不设字体/颜色） | substitution kind=`title_textbox` |
| 版式无 body/object 占位符但有要点 | 在版式内容界内加纯文本框 | substitution kind=`body_textbox` |
| 版式无 picture 占位符但有图 | 在内容界内等比缩放插图（居中） | figures[].aspect_preserved=true |
| 图片文件缺失 | 跳过该图，记 missing_figures，状态降 partial | missing_figures |
| 起始稿自带旧页 | 全部删除（drop_rel + 从 sldIdLst 移除） | deleted_slides |

铁律：**绝不**退回"空白默认外观"（新建空白 Presentation 再贴文本框），
也**绝不**手设字体/颜色去模仿主题——要么继承，要么记录替代。

## 5. 审计裁决含义

`inheritance_report.json` 字段：

- `per_slide[].chain.layout_exists / master_exists / theme_exists`：
  (a) 关系链三段是否各自解析成功。
- `per_slide[].unknown_placeholder_idx`：(b) 页面上发明 idx 的列表，非空即失败。
- `per_slide[].layout_in_template_names`：(c) 版式名 ∈ 模板 inventory 名字集。
- `per_slide[].layout_is_template_part`：(f) 页面所用版式部件的 sha256
  ∈ 模板自身全部版式部件哈希集（捕捉"外来/被改写的版式"）。
- `per_slide[].chain.theme_matches_template`：(e) 该页链到的主题指纹匹配。
- `checks.slide_size.equal`：(d) `sldSz` 与模板一致。
- `theme_preserved`：deck 的 theme1.xml 指纹 == 模板 theme1.xml 指纹。
- `overall_pass` = 全部页 ok 且尺寸一致且主题保留且页数 > 0。

裁决处理：

| overall_pass | 含义 | 处置 |
|---|---|---|
| true | 模板被结构性真实继承 | 可交付（status=success 的前提之一） |
| false + theme_fingerprint_mismatch | 主题被替换/重建 | 检查构建基底是否真是该模板；不得交付 success |
| false + invented_placeholder_idx | 页面上出现版式外 idx | 回到 build_deck 的占位符填充逻辑修 |
| false + dangling_* / broken chain | 关系目标缺失 | 包损坏或手工删过部件；重建 |
| false + foreign_or_modified_layout_part | 版式不是模板的部件 | 构建基底被换过；用回真正模板 |

**审计不过不交付**：overall_pass=false 时 result.json 的 status 至多为
partial，并在 uncertainty 中列出 failures。
