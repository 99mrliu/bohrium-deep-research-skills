# Artifact and scientific-boundary audits

## 通用动态合同

对 `asset_paths` 的每个键，从当前 output 根解析文件并检查存在、非零字节和 SHA-256。result 中对应路径值必须一致，case_id 和 result pointer 必须对应当前 case。静态字符串“result.json 存在”不是动态合同验收。

`run_manifest` 在 checkpoint 时写入，会在随后 phases 继续更新，因此 audit 内的 self/input hashes：checkpoint 主要用于阶段 evidence；最终 manifest 另做交付存在性和一致性检查。审计 JSON 不在自身内部嵌入可自指的一致 hash。交付文件的实际 SHA-256 由验证器/后续交付报告重算。

## SVG 回读

- 禁止 DOCTYPE/ENTITY；所有元素 ID 非空唯一。
- `data-kind=entity` 集合必须等于 specification 的 entity ID/label map，不能多一个、少一个或截断。
- `data-kind=edge` 的 ID/source/target/relation/uncertain 必须与 specification 完全相同。由此可以验证 feedback 没有丢失、uncertain 没被静默改成确定关系。
- `data-kind=legend-entry` 的 relation/text/uncertain 与 legend 一致。

这些是结构和来源一致性检查。脚本没有BioNER、因果推断或专家知识，不自动判生物学。原生 scientific review 必须显式覆盖所有 entity ID、feedback、uncertain edges，并含 observations/limitations；review 不通过 exit 4。

## PNG 像素

实际用 PyMuPDF 打开 PNG，要求单图、尺寸至少 100×100、samples 非空，并在确定性抽样中检测非白像素。这样能发现空文件、打不开和全白图；不能发现错字、轻微遮挡、配色不够或机制错误。

## PDF 页面和文字

要求单页并提取文本。title、所有 entity label、edge label 和 legend label 必须出现；验收记录 page_count 和 text。若需要更严格视觉验收，将 PDF 页面重新渲染成图像，由 Agent 实际查看。PDF 文本存在仍不证明位置不重叠或方向可信。

## 原生视觉交付

视觉 review 需独立 JSON：status=passed、reviewer、具体 observations/limitations、当前 png_sha256/pdf_sha256。runner 在交付时重算 hash，任何变化都是合同失败。不要提交模板中的占位观察，也不要缓存旧图 hash。

## Native review checklist

- source → specification：实体术语、source/target、feedback、uncertainty 与数据一致。
- specification → SVG → PDF：实体/边/图例一致，源/目标方向可回读。
- PNG/PDF：标签不溢出，feedback 与 uncertain 文字清晰，线不遮住标签，图例不缺失。
- 如实说明 dash/marker 的 viewer-specific 表现、字体替代、合成数据限制。
- 只有通过所有机器审计和 hash-bound 视觉检查才 delivered/complete；否则 partial 或 failed。
