#!/usr/bin/env python3
"""共享工具：JSON IO、UTC 日期归一化、窗口包含判定。

仅使用 Python 3 标准库；永不发起网络请求。
所有日期统一归一化为 UTC 区间 [earliest, latest]（均为闭端点），
用区间宽度表达源日期的精度不确定（年/月/日/秒）。
"""
import datetime as dt
import json
import re

UTC = dt.timezone.utc
_DAY = dt.timedelta(days=1)
_US = dt.timedelta(microseconds=1)

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def iso_z(d):
    """datetime -> 'YYYY-MM-DDTHH:MM:SSZ'（UTC）。"""
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(s):
    """解析 ISO 时间戳（支持 Z 与 ±HH:MM 偏移；无时区则假定为 UTC）。

    返回 UTC datetime；无法解析返回 None。
    """
    if not isinstance(s, str):
        return None
    ss = s.strip()
    if not ss:
        return None
    if ss.endswith(("Z", "z")):
        ss = ss[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(ss)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC)


def _from_date_parts(parts, raw):
    """Crossref date-parts：只有 [年] / [年,月] / [年,月,日] 三种精度。"""
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], int):
        return None
    y = parts[0]
    m = parts[1] if len(parts) > 1 else None
    d = parts[2] if len(parts) > 2 else None
    try:
        if m is None:
            start = dt.datetime(y, 1, 1, tzinfo=UTC)
            end = dt.datetime(y + 1, 1, 1, tzinfo=UTC)
            prec = "year"
        elif d is None:
            start = dt.datetime(y, m, 1, tzinfo=UTC)
            end = dt.datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=UTC)
            prec = "month"
        else:
            start = dt.datetime(y, m, d, tzinfo=UTC)
            end = start + _DAY
            prec = "day"
    except ValueError:
        return None
    return {
        "earliest": iso_z(start),
        "latest": iso_z(end - _US),
        "precision": prec,
        "raw": raw,
    }


def normalize_date_value(value):
    """把源数据中的日期值归一化为 UTC 区间。

    支持：Crossref {"date-parts": [[y,m,d]]}、裸 date-parts 列表、
    ISO 日期（YYYY-MM-DD）、ISO 时间戳（Z 或 ±HH:MM 偏移）。
    返回 dict{earliest, latest, precision, raw[, assumed_timezone]} 或 None。
    """
    if value is None:
        return None
    if isinstance(value, dict) and "date-parts" in value:
        try:
            parts = value["date-parts"][0]
        except (IndexError, TypeError, KeyError):
            return None
        return _from_date_parts(parts, raw=value)
    if isinstance(value, list):
        try:
            return _from_date_parts(value[0], raw=value)
        except (IndexError, TypeError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if _DATE_ONLY.match(s):
            try:
                start = dt.datetime(int(s[:4]), int(s[5:7]), int(s[8:10]), tzinfo=UTC)
            except ValueError:
                return None
            return {
                "earliest": iso_z(start),
                "latest": iso_z(start + _DAY - _US),
                "precision": "day",
                "raw": value,
            }
        inst = parse_instant(s)
        if inst is None:
            return None
        out = {
            "earliest": iso_z(inst),
            "latest": iso_z(inst),
            "precision": "second",
            "raw": value,
        }
        # 时间部分不含任何时区标记 -> 记录时区假设
        tail = s[10:]
        if ("+" not in tail) and ("-" not in tail) and not s.endswith(("Z", "z")):
            out["assumed_timezone"] = "UTC"
        return out
    return None


def find_window(chain, instant):
    """按左闭右开 [start, end) 返回包含 instant 的窗口 dict；不在任何窗口内返回 None。"""
    for w in chain:
        s = parse_instant(w.get("start"))
        e = parse_instant(w.get("end"))
        if s is None or e is None:
            continue
        if s <= instant < e:
            return w
    return None


def rel_locator(path, *json_path):
    """生成 locator 字符串：文件路径 + #/json/pointer 风格路径。"""
    suffix = "/".join(str(p) for p in json_path)
    return path + "#/" + suffix if suffix else path + "#"
