"""common_lib.py — 共享工具：JSON IO、Unicode 规范化、命中查找、配置加载。

仅使用 Python 标准库。所有脚本通过 `from common_lib import ...` 复用，
保证锚定 / 评分 / 扰动三步使用同一份规范化与查找实现，结果可复算。
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

_WS = re.compile(r"\s+")


def eprint(*args):
    """向 stderr 输出，避免污染 stdout 的管道结果。"""
    print(*args, file=sys.stderr)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    """幂等写 JSON：同输入永远产生同字节（无时间戳、键序固定）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def norm_text(s):
    """锚定规范化：NFKC → casefold → 折叠空白 → 去首尾空白。

    全角字符（如（）ＡＢＣ）经 NFKC 归一到半角；大小写经 casefold 抹平。
    命中校验一律在规范化后的文本上进行，见 references/anchoring_rules.md。
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.casefold()
    s = _WS.sub(" ", s)
    return s.strip()


def find_occurrences(hay, needle, cap=3):
    """在规范化文本 hay 中找 needle 的全部出现（上限 cap），返回 [(start, end), ...]。"""
    out = []
    if not needle:
        return out
    start = 0
    while len(out) < cap:
        i = hay.find(needle, start)
        if i < 0:
            break
        out.append((i, i + len(needle)))
        start = i + len(needle)
    return out


def make_snippet(hay, s, e, ctx=30):
    """从规范化文本截取命中片段（含上下文），两端越界时加省略号。"""
    a = max(0, s - ctx)
    b = min(len(hay), e + ctx)
    pre = "…" if a > 0 else ""
    post = "…" if b < len(hay) else ""
    return pre + hay[a:b] + post


def load_config(path):
    """加载并校验评分配置；facet 权重和必须为 1.0。"""
    cfg = load_json(path)
    fw = cfg.get("facet_weights")
    if not isinstance(fw, dict) or not fw:
        raise ValueError("config 缺少非空 facet_weights")
    total = sum(float(v) for v in fw.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"facet_weights 之和必须为 1.0，当前为 {total}")
    for k in ("coverage_points", "recency_points", "type_points", "tiers", "diversity"):
        if k not in cfg:
            raise ValueError(f"config 缺少必需键: {k}")
    return cfg


def default_config_path():
    """默认配置：bundle 内 config/scoring_config.json（可用 --config 覆盖）。"""
    return str(Path(__file__).resolve().parent.parent / "config" / "scoring_config.json")


def round_score(x, decimals):
    """统一舍入，避免伪精度小数；分档与并列判定都用舍入后的值。"""
    return round(float(x) + 0.0, int(decimals))
