#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_entities.py — 设备/物料/样本实体名归一。

用法: python3 normalize_entities.py [--alias alias_table.json] <requirements.json> <out.json>

归一规则（需求侧与库存/合同侧共用同一套函数，保证口径一致）:
  1. casefold  2. 去除空白与分隔符 (- _ / ( ) （ ） · , ，、)  3. 统一温度符号
  4. 查 references/alias_table.json 别名表，命中则合并到规范名。
解析不到别名的名称: 保留原字符串，标记 alias_resolved=false / is_new_entity=true，
绝不静默合并。原始字符串始终保留在各条目的 name/resource 字段。

本模块同时被 match_resources.py / check_booking.py / check_samples.py import，
作为唯一的归一入口（库存行、合同行走同一函数）。

退出码: 0 正常; 2 用法错误; 3 输入不可读。
"""
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ALIAS = SCRIPT_DIR.parent / "references" / "alias_table.json"

SEPARATORS = re.compile(r"[\s\-_()/（）·,，、]+")


def clean_name(s):
    """机械归一: 小写、去分隔符与空白、统一温度符号。"""
    return SEPARATORS.sub("", str(s).casefold().replace("°", "").replace("℃", "c"))


def load_alias_index(path=None):
    """加载别名表，返回 {clean(别名或规范名): 规范名}。文件缺失时返回空表。"""
    p = Path(path) if path else DEFAULT_ALIAS
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    idx = {}
    for alias, canon in (data.get("aliases") or {}).items():
        idx[clean_name(alias)] = canon
        idx[clean_name(canon)] = canon
    return idx


def normalize_name(name, idx):
    """返回 (规范名, 是否命中别名表)。未命中 → 原串 strip 后返回，不合并。"""
    key = clean_name(name)
    if key in idx:
        return idx[key], True
    return str(name).strip(), False


NAME_FIELDS = {
    "equipment": ["name"],
    "materials": ["name"],
    "samples": ["name"],
    "booking_needs": ["resource"],
}


def normalize_requirements(req, idx):
    out = json.loads(json.dumps(req, ensure_ascii=False))
    for section, fields in NAME_FIELDS.items():
        for entry in out.get(section) or []:
            if not isinstance(entry, dict):
                continue
            for f in fields:
                if f in entry:
                    norm, resolved = normalize_name(entry[f], idx)
                    entry["normalized_name" if f == "name" else "normalized_resource"] = norm
                    entry["alias_resolved"] = resolved
                    entry["is_new_entity"] = not resolved
    out["normalization"] = {
        "alias_table": str(DEFAULT_ALIAS),
        "rule": "casefold + 去分隔符 + 别名表; 未命中别名的标记 is_new_entity，绝不静默合并",
    }
    return out


def main(argv):
    args = argv[1:]
    alias_path = None
    if "--alias" in args:
        i = args.index("--alias")
        try:
            alias_path = args[i + 1]
        except IndexError:
            print("ERROR: --alias 缺少参数", file=sys.stderr)
            return 2
        del args[i:i + 2]
    if len(args) != 2:
        print("用法: python3 normalize_entities.py [--alias alias_table.json] "
              "<requirements.json> <out.json>", file=sys.stderr)
        return 2
    try:
        req = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("ERROR: 无法读取输入 {}: {}".format(args[0], e), file=sys.stderr)
        return 3
    idx = load_alias_index(alias_path)
    out = normalize_requirements(req, idx)
    Path(args[1]).parent.mkdir(parents=True, exist_ok=True)
    Path(args[1]).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("normalize_entities: 写入 {}".format(args[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
