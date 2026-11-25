"""lifecycle.py — 生命周期状态裁决与窗口预警分类。

状态机（详见 references/lifecycle-state-machine.md）：
  preprint_only → published → revised
  任意状态 → corrected / expression_of_concern / retracted（终止态）

裁决优先级（高者优先，保证撤稿永远不会被"已发表"掩盖）：
  retracted > expression_of_concern > corrected > published > revised > preprint_only

预警分类（每条链至多产出一条预警 → 预印本与正式版绝不重复预警）：
  retraction_notice   (priority=critical)   — 链内含撤稿信号，最高优先级
  correction_notice   (priority=high)       — 链内含勘误/关注声明信号
  version_update      (priority=normal)     — 链内多条记录，属版本推进
  new_work            (priority=normal)     — 单记录链，窗口内全新成果

记录不足（无 DOI 且无 arXiv id、标题缺失等）的链进入 unresolved，
由上层如实标注并降级 status=partial，绝不硬凑成链。
"""

PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2}

RETRACTION_REL_TYPES = {"is-retraction-of", "has-retraction"}
CORRECTION_REL_TYPES = {"is-correction-of", "has-correction"}
EOC_REL_TYPES = {"is-expression-of-concern-of", "has-expression-of-concern"}


def _loc(rec):
    return {"file": rec["locator"]["file"], "pointer": rec["locator"]["pointer"]}


def detect_signals(records):
    """在链内记录上检测撤稿 / 勘误 / 关注声明信号，返回信号证据列表。"""
    signals = []
    for rec in records:
        if rec["kind"] == "retraction-notice":
            signals.append({"signal": "retraction", "via": "record-kind",
                            "locator": _loc(rec)})
        if rec["kind"] == "correction-notice":
            signals.append({"signal": "correction", "via": "record-kind",
                            "locator": _loc(rec)})
        for rel in rec.get("relations", []):
            ptr = {"file": rec["locator"]["file"],
                   "pointer": rec["locator"]["pointer"] + rel["pointer"]}
            if rel["type"] in RETRACTION_REL_TYPES:
                signals.append({"signal": "retraction",
                                "via": "relation(%s)" % rel["type"],
                                "locator": ptr})
            elif rel["type"] in CORRECTION_REL_TYPES:
                signals.append({"signal": "correction",
                                "via": "relation(%s)" % rel["type"],
                                "locator": ptr})
            elif rel["type"] in EOC_REL_TYPES:
                signals.append({"signal": "expression_of_concern",
                                "via": "relation(%s)" % rel["type"],
                                "locator": ptr})
        for upd in rec.get("update_to", []):
            ptr = {"file": rec["locator"]["file"],
                   "pointer": rec["locator"]["pointer"] + upd["pointer"]}
            if upd["type"] == "retraction":
                signals.append({"signal": "retraction",
                                "via": "update-to(retraction)", "locator": ptr})
            elif upd["type"] in ("correction", "erratum"):
                signals.append({"signal": "correction",
                                "via": "update-to(%s)" % upd["type"],
                                "locator": ptr})
        comment = (rec.get("comment") or "").lower()
        if "retract" in comment or "withdrawn" in comment:
            signals.append({"signal": "retraction",
                            "via": "version-comment", "locator": _loc(rec)})
    return signals


def adjudicate_state(records, signals):
    """裁决链的当前生命周期状态，返回 (state, evidence_locators)。"""
    kinds = {r["kind"] for r in records}
    sig_types = {s["signal"] for s in signals}
    sig_locs = [s["locator"] for s in signals]

    if "retraction" in sig_types:
        return "retracted", sig_locs
    if "expression_of_concern" in sig_types:
        return "expression_of_concern", sig_locs
    if "correction" in sig_types:
        return "corrected", sig_locs
    if "journal-article" in kinds:
        return "published", [_loc(r) for r in records
                             if r["kind"] == "journal-article"]
    versions = [r["arxiv_version"] for r in records
                if r.get("arxiv_version")]
    if "preprint" in kinds and versions and max(versions) > 1:
        return "revised", [_loc(r) for r in records if r["kind"] == "preprint"]
    if "preprint" in kinds:
        return "preprint_only", [_loc(r) for r in records
                                 if r["kind"] == "preprint"]
    return "other", [_loc(r) for r in records]


def is_metadata_poor(records):
    """链内记录是否标识符/标题贫乏，无法可靠验证版本关系。"""
    for rec in records:
        has_id = bool(rec.get("doi") or rec.get("arxiv_id"))
        has_title = bool(rec.get("title_norm"))
        if not (has_id and has_title):
            return True
    return False


def classify_alert(state, records, signals):
    """把链在窗口内的变化分类为预警语义，返回 (alert_type, priority, reason)。"""
    sig_types = {s["signal"] for s in signals}
    if state == "retracted" or "retraction" in sig_types:
        return ("retraction_notice", "critical",
                "链内检测到撤稿信号；撤稿预警不可被去重吞掉")
    if state in ("corrected", "expression_of_concern"):
        return ("correction_notice", "high",
                "链内检测到勘误/关注声明信号")
    if len(records) > 1:
        return ("version_update", "normal",
                "同一成果的版本推进（如预印本→正式版、v1→v2），不重复预警")
    return ("new_work", "normal", "单记录链，窗口内全新成果")


def evaluate_chains(chains, link_decisions):
    """对全部链做状态裁决 + 预警分类。

    返回 (evaluated_chains, alerts, unresolved)。
    evaluated_chains 中不含 member_records（避免重复大对象）。
    """
    evaluated, alerts, unresolved = [], [], []
    for chain in chains:
        records = chain["member_records"]
        signals = detect_signals(records)
        state, state_ev = adjudicate_state(records, signals)
        alert_type, priority, reason = classify_alert(state, records, signals)
        chain_decisions = [
            d for d in link_decisions
            if d["a"] in chain["members"] and d["b"] in chain["members"]
        ]
        representative = next(
            (r for r in records if r["kind"] == "journal-article"),
            max(records, key=lambda r: (r.get("arxiv_version") or 0)))
        entry = {
            "chain_id": chain["chain_id"],
            "members": chain["members"],
            "lifecycle_state": state,
            "state_evidence": state_ev,
            "representative_title": representative.get("title"),
            "representative_locator": _loc(representative),
            "link_decisions": chain_decisions,
            "signals": signals,
        }
        evaluated.append(entry)
        alerts.append({
            "alert_type": alert_type,
            "priority": priority,
            "chain_id": chain["chain_id"],
            "lifecycle_state": state,
            "title": representative.get("title"),
            "reason": reason,
            "evidence": [_loc(r) for r in records],
        })
        if is_metadata_poor(records):
            unresolved.append({
                "chain_id": chain["chain_id"],
                "members": chain["members"],
                "reason": "记录缺少 DOI/arXiv id 或标题，无法可靠验证版本关系；"
                          "按单记录链处理并诚实降级",
                "locators": [_loc(r) for r in records],
            })
    alerts.sort(key=lambda a: (PRIORITY_ORDER[a["priority"]], a["chain_id"]))
    return evaluated, alerts, unresolved
