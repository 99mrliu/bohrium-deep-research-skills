# 证据账本结构

顶层字段：`title,synthetic,width,height,compartments,entities,edges,encodings,evidence`。

- `compartments[]`：`id,label,x,y,w,h,fill`。区室是位置，不是生物实体。
- `entities[]`：`id,label,kind,compartment,x,y,evidence_ids`；可选 `fill,stroke`。kind 至少区分 `gene,protein,complex,receptor,small_molecule,cell_type`。
- `edges[]`：`id,from,to,kind,evidence_ids`；受控 kind 为 `activates,inhibits,binds,phosphorylates,ubiquitinates,transports,recruits,uncertain`。from/to 是声明方向，不是视觉简化。
- `encodings[]`：`id,channel,field,scale,evidence_ids`；channel 例如 `fill,size,width`，scale 例如 `diverging,discrete,linear`。
- `evidence[]`：`id,file,locator,quote,evidence_type`。file 是输入根目录下实际文件，quote 为真实短引文。原始 PDF 无文本层时先合规解析到 /input 可访问的派生文本，或把派生文件放工作区后用相对可访问路径；不得伪造 quote_match。

坐标仅决定布局，不是生物学证据。引文通过只表明文本存在，不证明引文支撑主张；Agent 必须做语义核读。
