# Provenance Chain(逐记录溯源链)

- case_id: `synthetic-render-forge-001`
- 链式记号: 来源库 → 材料工件 → 原始响应定位(JSON 路径) → 字段映射 → 去重判定 → 合并取值(逐字段来源标注)
- 合并优先级: publisher > crossref > europepmc(逐字段独立裁决)

## rec-0001 — 10.99988/synforge.2024.001

- 来源库 → 材料 → 定位:
  - publisher → `materials/publisher_records.json` @ `records[0]`
  - crossref → `materials/crossref_response.json` @ `message.items[0]`
  - europepmc → `materials/europepmc_response.json` @ `resultList.result[0]`
- 去重判定: cluster_size=3; match_basis: doi
- 合并取值(逐字段来源):

| field | merged value | source db | artifact | locator | state |
|---|---|---|---|---|---|
| doi | 10.99988/synforge.2024.001 | publisher | materials/publisher_records.json | records[0] | value |
| pmid | 39998801 | publisher | materials/publisher_records.json | records[0] | value |
| title | Synthetic Cobalt Porphyrin Catalysts for Selective Oxidation in Model Reactions | publisher | materials/publisher_records.json | records[0] | value |
| year | 2024 | publisher | materials/publisher_records.json | records[0] | value |
| first_author | Liu | publisher | materials/publisher_records.json | records[0] | value |
| authors | Liu, Hengshen; Chen, Yixin | publisher | materials/publisher_records.json | records[0] | value |
| journal | Journal of Synthetic Catalysis | publisher | materials/publisher_records.json | records[0] | value |
| volume | 12 | publisher | materials/publisher_records.json | records[0] | value |
| issue | 3 | publisher | materials/publisher_records.json | records[0] | value |
| pages | 201-215 | publisher | materials/publisher_records.json | records[0] | value |

- 跨来源冲突:
  - `authors`: 2 variants; per-field source priority: publisher
    - variant: ['Liu H', 'Chen Y']
    - variant: ['Liu, Hengshen', 'Chen, Yixin']
  - `journal`: 2 variants; per-field source priority: publisher
    - variant: J. Synth. Catal.
    - variant: Journal of Synthetic Catalysis
- 成员缺失字段(该来源记录中为空):
  - publisher @ `records[0]`: none
  - crossref @ `message.items[0]`: pmid
  - europepmc @ `resultList.result[0]`: issue, pages, volume

## rec-0002 — 10.99988/synforge.2023.014

- 来源库 → 材料 → 定位:
  - crossref → `materials/crossref_response.json` @ `message.items[1]`
  - europepmc → `materials/europepmc_response.json` @ `resultList.result[1]`
- 去重判定: cluster_size=2; match_basis: doi
- 合并取值(逐字段来源):

| field | merged value | source db | artifact | locator | state |
|---|---|---|---|---|---|
| doi | 10.99988/synforge.2023.014 | crossref | materials/crossref_response.json | message.items[1] | value |
| pmid | 39998814 | europepmc | materials/europepmc_response.json | resultList.result[1] | value |
| title | Synthetic Metal-Organic Framework Membranes for Gas Selectivity | crossref | materials/crossref_response.json | message.items[1] | value |
| year | 2023 | crossref | materials/crossref_response.json | message.items[1] | value |
| first_author | Okafor | crossref | materials/crossref_response.json | message.items[1] | value |
| authors | Okafor, Adaeze; Mueller, Klaus | crossref | materials/crossref_response.json | message.items[1] | value |
| journal | Synthetic Materials Today | crossref | materials/crossref_response.json | message.items[1] | value |
| volume | 7 | crossref | materials/crossref_response.json | message.items[1] | value |
| issue | 11 | crossref | materials/crossref_response.json | message.items[1] | value |
| pages | 1101-1112 | crossref | materials/crossref_response.json | message.items[1] | value |

- 跨来源冲突:
  - `authors`: 2 variants; per-field source priority: crossref
    - variant: ['Okafor A', 'Mueller K']
    - variant: ['Okafor, Adaeze', 'Mueller, Klaus']
- 成员缺失字段(该来源记录中为空):
  - crossref @ `message.items[1]`: pmid
  - europepmc @ `resultList.result[1]`: issue, pages, volume

## rec-0003 — 10.99988/synforge.2022.031

- 来源库 → 材料 → 定位:
  - crossref → `materials/crossref_response.json` @ `message.items[2]`
- 去重判定: cluster_size=1; match_basis: (singleton)
- 合并取值(逐字段来源):

| field | merged value | source db | artifact | locator | state |
|---|---|---|---|---|---|
| doi | 10.99988/synforge.2022.031 | crossref | materials/crossref_response.json | message.items[2] | value |
| pmid | — | — | — | — | not_provided_by_any_source |
| title | Synthetic Enzyme Mimics with Tailored Selectivity | crossref | materials/crossref_response.json | message.items[2] | value |
| year | 2022 | crossref | materials/crossref_response.json | message.items[2] | value |
| first_author | Novak | crossref | materials/crossref_response.json | message.items[2] | value |
| authors | Novak, Ivana | crossref | materials/crossref_response.json | message.items[2] | value |
| journal | SynLett Fictional | crossref | materials/crossref_response.json | message.items[2] | value |
| volume | 4 | crossref | materials/crossref_response.json | message.items[2] | value |
| issue | 2 | crossref | materials/crossref_response.json | message.items[2] | value |
| pages | 88-97 | crossref | materials/crossref_response.json | message.items[2] | value |

- 跨来源冲突: 无
- 成员缺失字段(该来源记录中为空):
  - crossref @ `message.items[2]`: pmid

## rec-0004 — 10.99988/synforge.2025.007

- 来源库 → 材料 → 定位:
  - publisher → `materials/publisher_records.json` @ `records[1]`
  - europepmc → `materials/europepmc_response.json` @ `resultList.result[2]`
- 去重判定: cluster_size=2; match_basis: title+year+first_author
- 合并取值(逐字段来源):

| field | merged value | source db | artifact | locator | state |
|---|---|---|---|---|---|
| doi | 10.99988/synforge.2025.007 | publisher | materials/publisher_records.json | records[1] | value |
| pmid | 39998877 | europepmc | materials/europepmc_response.json | resultList.result[2] | value |
| title | Synthetic Photoredox Methods in Fictional Batch Chemistry | publisher | materials/publisher_records.json | records[1] | value |
| year | 2025 | publisher | materials/publisher_records.json | records[1] | value |
| first_author | Zhao | publisher | materials/publisher_records.json | records[1] | value |
| authors | Zhao, Min; Park, Ji-woo | publisher | materials/publisher_records.json | records[1] | value |
| journal | Synthetic Chemistry Letters | publisher | materials/publisher_records.json | records[1] | value |
| volume | 8 | publisher | materials/publisher_records.json | records[1] | value |
| issue | 1 | publisher | materials/publisher_records.json | records[1] | value |
| pages | 44-59 | publisher | materials/publisher_records.json | records[1] | value |

- 跨来源冲突:
  - `authors`: 2 variants; per-field source priority: publisher
    - variant: ['Zhao M', 'Park J']
    - variant: ['Zhao, Min', 'Park, Ji-woo']
- 成员缺失字段(该来源记录中为空):
  - publisher @ `records[1]`: pmid
  - europepmc @ `resultList.result[2]`: doi, issue, pages, volume
