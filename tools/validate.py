# -*- coding: utf-8 -*-
"""r40 数据校验器（校验通过才入库；build.py 只渲染通过校验的卡片）。

运行: python tools/validate.py            # 人读报告
     python tools/validate.py --json      # 仅输出 data/validation.json 路径

规则（任一不满足即该卡判失败、不得入库）:
 R1 结构: 每卡 fields >= 25；每字段必须含 value/unit/source_url/source_date/confidence/conflict_with 六个键。
 R2 非空: value/unit/source_url/source_date 均不得为空（"无来源不入库"）。
 R3 日期: source_date 形如 YYYY-MM-DD。
 R4 置信: confidence ∈ {verified, single-source, unverified}。
 R5 可追溯: source_url 必须命中 tools/collect/sources.json 且对应 raw/<slug>.* 已归档存在（支持 html/pdf/txt 等原始格式）。
 R8 分级: 每字段必须含 source_tier ∈ {T1,T2,T3}（D2：每字段必带来源分级），且与来源域名判定一致。
 R9 铁律: confidence=verified 的字段必须至少有一个 T1（厂商官方）来源（source_url 或 conflict_with 之一）。
 R10 时效: 每字段必须含 last_verified（YYYY-MM-DD 静态日期，禁构建时间戳）。
 R6 单位: 值为数字型（含 约/区间/分数）时 unit 必须为数字单位 {GB, GB/s, TFLOPS, TOPS, W}；
           unit 为数字单位时 value 必须含数字。
 R7 冲突登记: conflict_with 每项必须含 value/unit/source_url/source_date 且 source_url 可追溯；
           value 文本含冲突标记（冲突/存疑/口径不一）时 conflict_with 不得为空。
说明: 校验器只保证"已登记项的结构完整与来源可追溯"，不保证"冲突发现覆盖度"——后者依赖人工检索登记。
"""
import json, os, re, sys

SITE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SOURCES = os.path.join(SITE, "tools", "collect", "sources.json")
RAW = os.path.join(SITE, "raw")
CHIPS = os.path.join(SITE, "data", "chips")
CONF = {"verified", "single-source", "unverified"}
NUM_UNITS = {"GB", "GB/s", "TFLOPS", "TOPS", "W"}
NUMRE = re.compile(r"^(约)?\d+(\.\d+)?([\-/~](约)?\d+(\.\d+)?)+$|^(约)?\d+(\.\d+)?$")
DATERE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MARKERS = ("冲突", "存疑", "口径不一", "不一致")
FIELDS6 = ("value", "unit", "source_url", "source_date", "confidence", "conflict_with")
TIERSET = {"T1", "T2", "T3"}
LASTVERIF = re.compile(r"^\d{4}-\d{2}-\d{2}$")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiers  # noqa: E402  # 与 build/migrate 共用同一套域名分级口径


def is_archived(slug):
    """归档存在性：raw/<slug>.*（原始格式保留，html/pdf/txt 均可）。"""
    if not slug:
        return False
    try:
        names = os.listdir(RAW)
    except OSError:
        return False
    return any(n == slug or n.startswith(slug + ".") for n in names)


def load_sources():
    with open(SOURCES, encoding="utf-8") as f:
        d = json.load(f)["sources"]
    return {k: (v["url"] if isinstance(v, dict) else v) for k, v in d.items()}


def _numeric_value(v):
    s = re.sub(r"（[^）]*）", "", str(v)).strip()
    s = s.replace(",", "")
    if not s:
        return False
    if re.match(r"^\d{4}(-\d{2}){0,2}$", s):  # 日期/年月 不算数字值
        return False
    return bool(NUMRE.match(s))


def validate_chip(obj, url2slug):
    errs = []
    fields = obj.get("fields") or {}
    if len(fields) < 25:
        errs.append("R1 字段数 %d < 25" % len(fields))
    for k, v in fields.items():
        if not isinstance(v, dict):
            errs.append("R1 %s 非对象" % k)
            continue
        for key in FIELDS6:
            if key not in v:
                errs.append("R1 %s 缺键 %s" % (k, key))
        if not str(v.get("value", "")).strip():
            errs.append("R2 %s value 为空" % k)
        if not str(v.get("unit", "")).strip():
            errs.append("R2 %s unit 为空" % k)
        u = v.get("source_url", "")
        if not str(u).strip():
            errs.append("R2 %s source_url 为空" % k)
        if not str(v.get("source_date", "")).strip():
            errs.append("R2 %s source_date 为空" % k)
        elif not DATERE.match(str(v["source_date"])):
            errs.append("R3 %s source_date 非法: %r" % (k, v["source_date"]))
        if v.get("confidence") not in CONF:
            errs.append("R4 %s confidence 非法: %r" % (k, v.get("confidence")))
        if u and str(u).strip():
            if u not in url2slug:
                errs.append("R5 %s source_url 未在 sources.json 登记" % k)
            elif not is_archived(url2slug[u]):
                errs.append("R5 %s 来源 raw/%s.* 未归档" % (k, url2slug[u]))
        unit = str(v.get("unit", ""))
        if _numeric_value(v.get("value", "")) and unit not in NUM_UNITS:
            errs.append("R6 %s 数字值 %r 单位非法: %r" % (k, v.get("value"), unit))
        if unit in NUM_UNITS and not re.search(r"\d", str(v.get("value", ""))):
            errs.append("R6 %s 单位 %s 但值无数字" % (k, unit))
        cw = v.get("conflict_with", [])
        if not isinstance(cw, list):
            errs.append("R7 %s conflict_with 非数组" % k)
            cw = []
        for j, c in enumerate(cw):
            if not isinstance(c, dict):
                errs.append("R7 %s conflict[%d] 非对象" % (k, j))
                continue
            for key in ("value", "unit", "source_url", "source_date"):
                if not str(c.get(key, "")).strip():
                    errs.append("R7 %s conflict[%d] 缺 %s" % (k, j, key))
            cu = c.get("source_url", "")
            if cu and cu not in url2slug:
                errs.append("R7 %s conflict[%d] source_url 未登记" % (k, j))
            elif cu and not is_archived(url2slug[cu]):
                errs.append("R7 %s conflict[%d] 来源未归档" % (k, j))
        if any(m in str(v.get("value", "")) for m in MARKERS) and not cw:
            errs.append("R7 %s 值含冲突标记但未登记 conflict_with" % k)
        # R8 来源分级（D2）：每字段必带 source_tier，且与来源域名判定一致
        st = v.get("source_tier")
        if st not in TIERSET:
            errs.append("R8 %s source_tier 缺失或非法: %r" % (k, st))
        else:
            exp = tiers.tier_of(u)
            if st != exp:
                errs.append("R8 %s source_tier=%s 与来源域名判定 %s 不一致" % (k, st, exp))
        # R9 铁律（D2）：verified 必须至少有一个 T1 官方来源
        if v.get("confidence") == "verified":
            cand = [u] + [c.get("source_url") for c in cw if isinstance(c, dict)]
            if not any(tiers.tier_of(x) == "T1" for x in cand if x):
                errs.append("R9 %s confidence=verified 但无任何 T1 官方来源" % k)
        # R10 时效（D4）：字段级 last_verified（静态日期）
        lv = str(v.get("last_verified") or "").strip()
        if not lv:
            errs.append("R10 %s last_verified 为空" % k)
        elif not LASTVERIF.match(lv):
            errs.append("R10 %s last_verified 非法: %r" % (k, lv))
    return errs


def run():
    srcs = load_sources()
    url2slug = {u: k for k, u in srcs.items()}
    archived = sorted(os.path.splitext(f)[0] for f in os.listdir(RAW) if not f.startswith("."))
    out = {"schema_version": "0.1", "validator": "tools/validate.py",
           "sources_registered": len(srcs), "archived_raw": len(archived),
           "archived_bytes": sum(os.path.getsize(os.path.join(RAW, f))
                                 for f in os.listdir(RAW) if not f.startswith(".")),
           "orphan_sources": sorted(set(srcs) - set(archived)),
           "chips": [], "passed": 0, "failed": 0}
    for fn in sorted(os.listdir(CHIPS)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(CHIPS, fn), encoding="utf-8") as f:
            obj = json.load(f)
        errs = validate_chip(obj, url2slug)
        rec = {"file": "data/chips/" + fn, "model": obj.get("model"),
               "vendor": obj.get("vendor"), "model_slug": obj.get("model_slug"),
               "vendor_slug": obj.get("vendor_slug"),
               "field_count": len(obj.get("fields") or {}),
               "ok": not errs, "errors": errs}
        out["chips"].append(rec)
        out["passed" if rec["ok"] else "failed"] += 1
    with open(os.path.join(SITE, "data", "validation.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def main():
    rep = run()
    print("r40 validate: sources=%d archived=%d bytes=%d" %
          (rep["sources_registered"], rep["archived_raw"], rep["archived_bytes"]))
    if rep["orphan_sources"]:
        print("WARN 已登记但未归档: %s" % ", ".join(rep["orphan_sources"]))
    for c in rep["chips"]:
        print("%-4s %-26s fields=%-3d %s" % ("OK" if c["ok"] else "FAIL",
              c["model_slug"], c["field_count"], "; ".join(c["errors"])[:300]))
    print("passed=%d failed=%d" % (rep["passed"], rep["failed"]))
    print("report: %s" % os.path.join(SITE, "data", "validation.json"))
    return 0 if rep["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
