"""assemble_result.py — 结果装配与 output_contract 强制校验。

契约：
- result.json 必须包含 case.json 中 output_contract 列出的全部字段；
- 任何缺失字段补 null，并把 status 降级为 "partial"；
- 存在未解析记录或材料异常时，同样诚实降级为 "partial"；
- 绝不编造字段值——补 null 是唯一合法的兜底。
"""


def assemble_result(case, chains, alerts, unresolved, anomalies, notes):
    contract = list(case.get("output_contract") or [])
    body = {
        "case_id": case.get("case_id"),
        "status": "complete",
        "window": case.get("window"),
        "chains": chains,
        "alerts": alerts,
        "unresolved": unresolved,
        "material_anomalies": anomalies,
        "notes": notes,
    }
    missing = [f for f in contract if f not in body]
    for f in missing:
        body[f] = None
    degraded = []
    if missing:
        degraded.append("contract fields filled with null: %s" % ", ".join(missing))
    if unresolved:
        degraded.append("%d chain(s) unresolved due to poor metadata"
                        % len(unresolved))
    if anomalies:
        degraded.append("%d material file(s) anomalous" % len(anomalies))
    if degraded:
        body["status"] = "partial"
        body.setdefault("notes", [])
        if isinstance(body["notes"], list):
            body["notes"] = list(body["notes"]) + [
                "status=partial: " + d for d in degraded]
    # 契约字段排序在前，其余随后，便于人工目检。
    ordered = {}
    for f in ["case_id", "status"] + [f for f in contract
                                      if f not in ("case_id", "status")]:
        if f in body:
            ordered[f] = body[f]
    for f, v in body.items():
        if f not in ordered:
            ordered[f] = v
    return ordered
