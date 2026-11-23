# -*- coding: utf-8 -*-
"""确定性规范化：名称候选键、定义性属性、数值与单位（仅标准库）。

原则：规范化只用于生成“候选”，绝不单独构成合并依据。
是否合并由 identity_gate.py 依据属性签名与冲突证据裁决。
"""
import re
import unicodedata

_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "μ": "mu", "λ": "lambda", "σ": "sigma", "κ": "kappa",
}

_WS_RE = re.compile(r"\s+")
_KEEP_RE = re.compile(r"[^0-9a-z一-鿿./]+")

# 定义性属性：用于判断“是否为同一对象/实例”的身份属性。
# 注意：doi/source_id 等来源信息绝不属于定义性属性（不同 DOI 不是阻断项）。
DEFINING_KEYS = frozenset([
    "chemical_formula", "composition", "cas_number", "identifier",
    "architecture", "principle", "algorithm",
    "dataset_version", "version", "model_version",
    "sample_id", "batch", "instrument", "conditions",
])

# 强身份键：通用术语只有在强身份键一致时才允许合并（否则至多 UNDECIDED）。
STRONG_KEYS = frozenset(["cas_number", "identifier", "sample_id", "instrument"])

_UNIT_ALIASES = {
    "°c": "c", "℃": "c", "sec": "s", "second": "s", "seconds": "s",
    "hour": "h", "hours": "h", "hr": "h",
    "dimensionless": "1", "none": "1", "": "1",
}


def normalize_surface(text):
    """表面形规范化：NFKC、小写、希腊字母展开、连字符/下划线归一、去标点、压空白。"""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).strip().lower()
    for k, v in _GREEK.items():
        s = s.replace(k, v)
    s = s.replace("-", " ").replace("_", " ")
    s = _KEEP_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def candidate_keys(mention):
    """由一个提及记录的 surface 与 aliases 生成全部候选键（排序后返回）。"""
    keys = set()
    surf = normalize_surface(mention.get("surface", ""))
    if surf:
        keys.add(surf)
    for alias in mention.get("aliases") or []:
        a = normalize_surface(alias)
        if a:
            keys.add(a)
    return sorted(keys)


def normalize_value(value):
    """定义性属性值规范化（与表面形同规则）。"""
    return normalize_surface(value)


def normalize_unit(unit):
    """单位规范化：小写、去空白、少量别名映射。未知差异按不一致处理（保守）。"""
    if unit is None:
        return "1"
    u = unicodedata.normalize("NFKC", str(unit)).strip().lower()
    u = u.replace(" ", "").replace("·", "").replace("*", "")
    u = u.replace("^-1", "/").replace("−1", "/")
    return _UNIT_ALIASES.get(u, u)


def parse_number(value):
    """把数值解析为 float；支持 '3.2e-4'、'1,200' 等形式；失败返回 None。"""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", s)
        return float(m.group(0)) if m else None


def numbers_equal(a, b, rel_tol=1e-12):
    """数值一致性判定（近精确相等；任何真实差异都视为冲突）。"""
    fa, fb = parse_number(a), parse_number(b)
    if fa is None or fb is None:
        return None  # 无法解析：不判等也不判冲突
    return abs(fa - fb) <= rel_tol * max(1.0, abs(fa), abs(fb))


def defining_attrs(mention):
    """提取提及记录 properties 中属于定义性属性的键值对。"""
    props = mention.get("properties") or {}
    return {k: v for k, v in props.items() if k in DEFINING_KEYS and v not in (None, "")}


def measured_attrs(mention):
    """提取提及记录 numbers 中的测量属性列表（name/value/unit）。"""
    out = []
    for n in mention.get("numbers") or []:
        if isinstance(n, dict) and n.get("name"):
            out.append(n)
    return out
