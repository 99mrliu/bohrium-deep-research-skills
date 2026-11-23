#!/usr/bin/env python3
"""units.py — 单位代数库（单位解析 / 可换算判定 / 数值换算）。

仅标准库、无网络。所有单位被解析为:
    {"dimensions": {量纲符号: 指数}, "scale": 到 SI 的换算因子, "canonical": 规范写法}
量纲符号集: L(长度) M(质量) T(时间) A(电流) K(温度) N(物质的量) I(发光强度) DIM(无量纲计数)

规则:
  - 量纲向量不同 -> 不可换算 (convertible 返回 False)。
  - 量纲相同 -> scale 之比即换算因子; convert 返回 (新值, "derived")。
  - 无法解析的单位 -> None, 上层必须保留原单位原文、不换算、标记 unregistered。

用法（库）:
    from units import parse_unit, convertible, convert
用法（命令行自检）:
    python3 units.py --selftest
"""
import re
import sys

# ---- 词头表 -----------------------------------------------------------------
PREFIXES = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9,
    "M": 1e6, "k": 1e3, "h": 1e2, "da": 1e1,
    "d": 1e-1, "c": 1e-2, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
    "n": 1e-9, "p": 1e-12, "f": 1e-15,
}

# ---- 基础单位表: 单位符号 -> (量纲向量, 到 SI 的因子) ------------------------
# SI 基本单位: m, kg, s, A, K, mol, cd
BASE_UNITS = {
    # 长度
    "m": ({"L": 1}, 1.0),
    # 质量 (注意: SI 基本单位是 kg; g 的 scale 为 1e-3)
    "g": ({"M": 1}, 1e-3),
    "kg": ({"M": 1}, 1.0),
    "t": ({"M": 1}, 1e3),
    # 时间
    "s": ({"T": 1}, 1.0),
    "sec": ({"T": 1}, 1.0),
    "min": ({"T": 1}, 60.0),
    "h": ({"T": 1}, 3600.0),
    "hr": ({"T": 1}, 3600.0),
    "day": ({"T": 1}, 86400.0),
    "d_time": ({"T": 1}, 86400.0),  # 内部消歧, 不作为输入符号
    # 电流 / 温度 / 物质的量 / 发光强度
    "A": ({"A": 1}, 1.0),
    "K": ({"K": 1}, 1.0),
    "mol": ({"N": 1}, 1.0),
    "cd": ({"I": 1}, 1.0),
    # 体积
    "L": ({"L": 3}, 1e-3),
    "l": ({"L": 3}, 1e-3),
    # 浓度 / 其他复合常用单位的展开式在 parse 中按乘除处理;
    # 这里给出若干派生单位:
    "M_molar": ({"N": 1, "L": -3}, 1e3),  # 内部: mol/L = 1e3 mol/m^3
    "W": ({"M": 1, "L": 2, "T": -3}, 1.0),
    "V": ({"M": 1, "L": 2, "T": -3, "A": -1}, 1.0),
    "J": ({"M": 1, "L": 2, "T": -2}, 1.0),
    "eV": ({"M": 1, "L": 2, "T": -2}, 1.602176634e-19),
    "Pa": ({"M": 1, "L": -1, "T": -2}, 1.0),
    "Hz": ({"T": -1}, 1.0),
    "nm_explicit": ({"L": 1}, 1e-9),  # 供测试锚点; "nm" 走词头解析
    # 无量纲
    "%": ({"DIM": 1}, 0.01),
    "percent": ({"DIM": 1}, 0.01),
    "‰": ({"DIM": 1}, 1e-3),
    "ppm": ({"DIM": 1}, 1e-6),
    "ppb": ({"DIM": 1}, 1e-9),
    "1": ({"DIM": 1}, 1.0),
    "fraction": ({"DIM": 1}, 1.0),  # 登记用别名, 表示纯小数
    "unitless": ({"DIM": 1}, 1.0),
}

# 输入别名 -> 规范符号 (处理常见异体)
ALIASES = {
    "µg": "ug", "μg": "ug",
    "µL": "uL", "μL": "uL",
    "℃": "degC", "°C": "degC",
    "seconds": "s", "second": "s", "secs": "s",
    "minutes": "min", "minute": "min", "mins": "min",
    "hours": "h", "hour": "h", "hrs": "h",
    "days": "day",
    "litre": "L", "liter": "L", "litres": "L", "liters": "L",
    "gram": "g", "grams": "g",
    "percent": "%", "percentage": "%", "pct": "%",
}

# 温度特殊处理 (仿射换算, 不做乘法 scale)
AFFINE = {
    "degC": ({"K": 1}, 1.0, 273.15),  # K = C + 273.15
}

_DIM_KEYS = ("L", "M", "T", "A", "K", "N", "I", "DIM")


def _dims(**kw):
    return {k: v for k, v in kw.items() if v}


def _norm_dims(d):
    """去掉零指数, 返回规范化量纲向量。"""
    return {k: v for k, v in d.items() if abs(v) > 1e-12}


def _same_dims(d1, d2):
    return _norm_dims(d1) == _norm_dims(d2)


def _combine(d1, d2, sign=1):
    out = dict(d1)
    for k, v in d2.items():
        out[k] = out.get(k, 0) + sign * v
    return _norm_dims(out)


# ---- 解析 -------------------------------------------------------------------

def _strip_unicode(unit: str) -> str:
    """统一上标/异体写法: min⁻¹ -> min^-1, ⁻² -> ^-2, × -> *, · -> *, μ -> u 前缀保留。"""
    sup = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
           "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-"}
    out = []
    for ch in unit:
        if ch in sup:
            # 上标数字/负号前补 ^
            if ch in sup and (ch == "⁻" or not out or out[-1] not in "^-0123456789"):
                if out and out[-1] not in "^":
                    out.append("^")
            out.append(sup[ch])
        elif ch in "·⋅∙":
            out.append("*")
        elif ch in "×":
            out.append("*")
        elif ch in "⁄":
            out.append("/")
        elif ch == "−":
            out.append("-")
        else:
            out.append(ch)
    return "".join(out)


def _tokenize(unit: str):
    """把单位串切成 (因子符号, 指数) 列表, 符号 / * ^ 处理。

    支持: 'mg/L', 'mg L-1', 'mg*L^-1', 'min⁻¹'(已预处理), '1/min'(=min^-1),
    'per minute'(由调用方先规范), 'mg L^-1' 空格连接, 'g L-1' 等。
    返回 [(symbol, exponent)], exponent 带符号。
    """
    u = unit.strip()
    if not u:
        return None
    # 去掉两侧括号/引号
    u = u.strip("()[]")
    # 处理 '1/xxx' 与 'per xxx'
    m = re.fullmatch(r"1\s*/\s*(.+)", u)
    if m:
        inner = _tokenize(m.group(1))
        if inner is None:
            return None
        return [(s, -e) for s, e in inner]
    m = re.fullmatch(r"per\s+(\w+)", u, flags=re.IGNORECASE)
    if m:
        inner = _tokenize(m.group(1))
        if inner is None:
            return None
        return [(s, -e) for s, e in inner]

    # 分母只支持一个 '/'; 多个 '/' 视为非法(避免歧义)
    if u.count("/") > 1:
        return None
    if "/" in u:
        num, den = u.split("/", 1)
        den_tok = _tokenize(den)
        if den_tok is None:
            return None
        num_tok = _tokenize(num) if num.strip() and num.strip() != "1" else []
        if num_tok is None:
            return None
        return num_tok + [(s, -e) for s, e in den_tok]

    # 乘法与空格连接
    parts = re.split(r"[\*\s]+", u)
    toks = []
    for p in parts:
        if not p:
            continue
        m = re.fullmatch(r"([A-Za-zµμ%‰]+)\^?(-?\d+)?", p)
        if not m:
            return None
        sym = m.group(1)
        exp = int(m.group(2)) if m.group(2) else 1
        toks.append((sym, exp))
    if not toks:
        return None
    return toks


def _lookup_symbol(sym: str):
    """查 (量纲, scale): 先别名, 再直接表, 再词头+基础单位。"""
    if sym in AFFINE:
        dims, scale, _off = AFFINE[sym]
        return dict(dims), scale
    if sym in ALIASES:
        sym = ALIASES[sym]
        if sym in AFFINE:
            dims, scale, _off = AFFINE[sym]
            return dict(dims), scale
    if sym in BASE_UNITS:
        d, s = BASE_UNITS[sym]
        return dict(d), s
    # 摩尔浓度简写 'M' (mol/L) —— 与词头 M(兆) 冲突; 单写 'M' 判为摩尔浓度。
    if sym == "M":
        return {"N": 1, "L": -3}, 1e3
    if sym == "mM":
        return {"N": 1, "L": -3}, 1.0
    if sym == "uM":
        return {"N": 1, "L": -3}, 1e-3
    if sym == "nM":
        return {"N": 1, "L": -3}, 1e-6
    # 词头解析: 尝试最长词头匹配
    for plen in (2, 1):
        pre, base = sym[:plen], sym[plen:]
        if pre in PREFIXES and base in BASE_UNITS:
            d, s = BASE_UNITS[base]
            # 'kg' 已是基础单位, 不允许再加词头 (如 'mkg' 非法)
            if base == "kg":
                return None
            return dict(d), PREFIXES[pre] * s
    return None


def parse_unit(unit: str):
    """解析单位字符串 -> {"dimensions": {...}, "scale": float, "canonical": str} 或 None。"""
    if unit is None:
        return None
    raw = str(unit).strip()
    if raw == "":
        return {"dimensions": {"DIM": 1}, "scale": 1.0, "canonical": "1"}
    u = _strip_unicode(raw)
    toks = _tokenize(u)
    if toks is None:
        return None
    dims = {}
    scale = 1.0
    canon = []
    for sym, exp in toks:
        look = _lookup_symbol(sym)
        if look is None:
            return None
        d, s = look
        dims = _combine(dims, {k: v * exp for k, v in d.items()})
        scale *= s ** exp
        canon.append(sym + ("" if exp == 1 else "^" + str(exp)))
    if not dims:
        dims = {"DIM": 1}
    return {"dimensions": _norm_dims(dims), "scale": scale,
            "canonical": "*".join(canon) if canon else "1"}


def convertible(u1: str, u2: str) -> bool:
    """两单位是否可换算 (量纲向量一致)。任一不可解析 -> False。"""
    p1, p2 = parse_unit(u1), parse_unit(u2)
    if p1 is None or p2 is None:
        return False
    return _same_dims(p1["dimensions"], p2["dimensions"])


def convert(value, u1: str, u2: str):
    """把 value 从 u1 换算到 u2。

    返回 {"value": float, "unit": u2, "status": "derived"} 或 None(不可换算/不可解析)。
    温度 degC<->K 走仿射换算。
    """
    if u1 in AFFINE or u2 in AFFINE:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if u1 in AFFINE and u2 == "K":
            _, _, off = AFFINE[u1]
            return {"value": v + off, "unit": "K", "status": "derived"}
        if u1 == "K" and u2 in AFFINE:
            _, _, off = AFFINE[u2]
            return {"value": v - off, "unit": u2, "status": "derived"}
        if u1 in AFFINE and u2 in AFFINE:
            return {"value": v, "unit": u2, "status": "derived"}
        return None
    p1, p2 = parse_unit(u1), parse_unit(u2)
    if p1 is None or p2 is None:
        return None
    if not _same_dims(p1["dimensions"], p2["dimensions"]):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    new_v = v * p1["scale"] / p2["scale"]
    return {"value": new_v, "unit": u2, "status": "derived"}


def dims_label(dimensions) -> str:
    """量纲向量的可读标签, 如 L^3·M^-1。"""
    if not dimensions or set(dimensions) == {"DIM"}:
        return "1(无量纲)"
    parts = []
    for k in ("L", "M", "T", "A", "K", "N", "I", "DIM"):
        v = dimensions.get(k, 0)
        if v:
            parts.append(k if v == 1 else f"{k}^{v}")
    return "·".join(parts)


# ---- 自检 -------------------------------------------------------------------

def _selftest():
    cases_ok = []
    # 解析正确性
    p = parse_unit("mg/L")
    assert p and p["dimensions"] == {"M": 1, "L": -3}, p
    p = parse_unit("g/L")
    assert p and abs(p["scale"] - 1.0) < 1e-12, p  # g/L = 1e-3/1e-3
    p = parse_unit("min⁻¹")
    assert p and p["dimensions"] == {"T": -1} and abs(p["scale"] - 1 / 60) < 1e-12, p
    p = parse_unit("min^-1")
    assert p and p["dimensions"] == {"T": -1}, p
    p = parse_unit("1/min")
    assert p and p["dimensions"] == {"T": -1}, p
    p = parse_unit("per minute")
    assert p and p["dimensions"] == {"T": -1}, p
    p = parse_unit("%")
    assert p and p["dimensions"] == {"DIM": 1} and abs(p["scale"] - 0.01) < 1e-15, p
    p = parse_unit("nm")
    assert p and p["dimensions"] == {"L": 1} and abs(p["scale"] - 1e-9) < 1e-20, p
    p = parse_unit("W")
    assert p and p["dimensions"] == {"M": 1, "L": 2, "T": -3}, p
    assert parse_unit("furlong") is None
    # 可换算判定
    assert convertible("%", "fraction")
    assert convertible("mg/L", "g/L")
    assert convertible("min⁻¹", "s^-1")
    assert not convertible("mg/L", "%")
    assert not convertible("mg/L", "min^-1")
    # 换算值
    r = convert(0.92, "fraction", "%")
    assert r and abs(r["value"] - 92.0) < 1e-9 and r["status"] == "derived", r
    r = convert(96, "%", "fraction")
    assert r and abs(r["value"] - 0.96) < 1e-12, r
    r = convert(500, "mg/L", "g/L")
    assert r and abs(r["value"] - 0.5) < 1e-12, r
    r = convert(1.0, "g/L", "mg/L")
    assert r and abs(r["value"] - 1000.0) < 1e-9, r
    r = convert(0.031, "min⁻¹", "s^-1")
    assert r and abs(r["value"] - 0.031 / 60) < 1e-12, r
    r = convert(20, "degC", "K")
    assert r and abs(r["value"] - 293.15) < 1e-9, r
    assert convert(5, "mg/L", "%") is None
    print("units.py selftest: ALL OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("用法: from units import parse_unit, convertible, convert ; 或 python3 units.py --selftest")
