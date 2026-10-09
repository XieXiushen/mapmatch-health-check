# -*- coding: utf-8 -*-
"""R44 数据迁移（一次性，幂等）：
  1) 用 T1 官方证据（temp/t1_evidence.json，只读）登记新来源 + 归档 raw/；
  2) 为 data/chips/*.json 的每个字段补 source_tier / last_verified（D2/D4）；
  3) 按官方证据提升寒武纪/昇腾字段到 T1（confidence=verified）；
  4) D2 硬规则：无 T1 来源的字段不得 verified → 降级 single-source；
  5) 输出 data/changelog.json（D4 字段变更记录）。
不联网、不改写 temp/t1_evidence.json。
"""
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tiers  # noqa: E402

SITE = os.path.dirname(HERE)
TEMP = os.path.join(SITE, "temp")
RAW = os.path.join(SITE, "raw")
CHIPS = os.path.join(SITE, "data", "chips")
SOURCES = os.path.join(HERE, "collect", "sources.json")

log = []


def P(*a):
    s = " ".join(str(x) for x in a)
    log.append(s)
    print(s)


# ---------- 0) 读证据 ----------
EV = json.load(open(os.path.join(TEMP, "t1_evidence.json"), encoding="utf-8"))
PROBES = EV["probes"]
P_A2, P_A3T, P_A3I, P_CAM = PROBES[0], PROBES[1], PROBES[2], PROBES[4]

NEW_SOURCES = [
    ("cambricon-mlu370x8-official", P_CAM, "寒武纪 思元MLU370-X8 产品规格页（官方）", "cambricon"),
    ("huawei-atlas800t-a2-whitepaper", P_A2, "Atlas 800T A2 训练服务器 技术白皮书（华为官方 PDF）", "huawei"),
    ("huawei-atlas800t-a3-whitepaper", P_A3T, "Atlas 800T A3 超节点 技术白皮书（华为官方 PDF）", "huawei"),
    ("huawei-atlas800i-a3-whitepaper", P_A3I, "Atlas 800I A3 超节点 技术白皮书（华为官方 PDF）", "huawei"),
]
NEW_SOURCES = [(s, p, t, v) for s, p, t, v in NEW_SOURCES]
for _s, _p, _t, _v in NEW_SOURCES:
    _p["title"], _p["vendor"] = _t, _v

# ---------- 1) sources.json（嵌套结构：{_note, sources:{slug:{kind,title,url,vendor}}}） ----------
SRC_DOC = json.load(open(SOURCES, encoding="utf-8"))
SRC_MAP = SRC_DOC["sources"]
P("sources.json before: %d" % len(SRC_MAP))
for slug, pr, _t, _v in NEW_SOURCES:
    if slug not in SRC_MAP or SRC_MAP[slug].get("url") != pr["url"]:
        SRC_MAP[slug] = {"kind": "spec", "title": pr["title"], "url": pr["url"], "vendor": pr["vendor"]}
        P("  + register source %s" % slug)
for slug, ent in SRC_MAP.items():
    ent["tier"] = tiers.tier_of(ent.get("url"))  # D2：来源级 tier 显式落盘
    ent.setdefault("last_verified", tiers.LAST_VERIFIED)
if not os.path.exists(RAW):
    os.makedirs(RAW)
for slug, pr, _t, _v in NEW_SOURCES:
    ap = pr.get("archive_path")
    if not ap or not os.path.exists(ap):
        raise SystemExit("MISSING ARCHIVE for %s: %s" % (slug, ap))
    ext = os.path.splitext(ap)[1].lower()
    dst = os.path.join(RAW, slug + ext)
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(ap):
        shutil.copyfile(ap, dst)
        P("  + archive raw/%s%s <- %s (%d bytes)" % (slug, ext, os.path.basename(ap), os.path.getsize(dst)))
SRC_DOC["_note"] = SRC_DOC.get("_note", "")
SRC_DOC["sources"] = {k: SRC_MAP[k] for k in sorted(SRC_MAP)}
json.dump(SRC_DOC, open(SOURCES, "w", encoding="utf-8"), ensure_ascii=False, indent=2, sort_keys=False)
open(SOURCES, "a", encoding="utf-8").write("\n")
P("sources.json after: %d" % len(SRC_MAP))
# URL → slug 反查（changelog 用 slug 标注来源，避免长 URL 截断歧义）
URL2SLUG = {}
for _s, _v in SRC_MAP.items():
    if _v.get("url"):
        URL2SLUG.setdefault(_v["url"], _s)


def slug_of(u):
    if not u:
        return ""
    return URL2SLUG.get(u, u if len(u) <= 64 else u[:61] + "…")


# ---------- 2) 官方提升表 ----------
def norm(v):
    return re.sub(r"\s*/\s*", "/", str(v)).strip()


def official_value(probe, key):
    f = (probe.get("fields") or {}).get(key) or {}
    v = f.get("value")
    return None if v is None else norm(v)


PROMOS = []  # (chip_file, field_key, new_value, new_note, url, extra_conflicts, overrides)
# 数值字段的单位口径（官方提升时强制落定，避免沿用旧 'n/a'）
UNIT_FIX = {"fp16_tflops": "TFLOPS", "bf16_tflops": "TFLOPS", "fp32_tflops": "TFLOPS",
            "int8_tops": "TOPS", "memory_capacity": "GB", "memory_bandwidth": "GB/s",
            "tdp": "W"}

# 寒武纪 思元MLU370-X8：9 字段（memory_type/process_node 为非数字值，原样保留口径）
CAM_FIELDS = ["fp16_tflops", "bf16_tflops", "int8_tops", "fp32_tflops",
              "memory_capacity", "memory_type", "memory_bandwidth", "tdp", "process_node"]
for k in CAM_FIELDS:
    v = official_value(P_CAM, k)
    if v is None:
        continue
    PROMOS.append(("cambricon-mlu370-x8.json", k, v,
                   "寒武纪官网产品页（catid=406，2026-10-09 复抓）", P_CAM["url"], [], {}))

# 昇腾910B（Atlas 800T A2，白皮书为单个AI处理器/NPU规格）
for k in ["fp16_tflops", "fp32_tflops", "memory_capacity", "memory_bandwidth", "tdp"]:
    v = official_value(P_A2, k)
    if v is None:
        continue
    PROMOS.append(("huawei-ascend-910b.json", k, v,
                   "Atlas 800T A2 训练服务器技术白皮书（e.huawei.com，单AI处理器/NPU规格）",
                   P_A2["url"], [], {}))

# 昇腾910C（Atlas 800T A3 超节点；单模组口径 + 推理整机(A3I)冲突登记）
CONF_910C = [
    {"source_url": P_A3I["url"], "value": "560", "unit": "TFLOPS",
     "note": "Atlas 800I A3 推理超节点白皮书口径（T1，整机级）"},
    {"source_url": P_A3I["url"], "value": "150", "unit": "TFLOPS",
     "note": "Atlas 800I A3 推理超节点白皮书口径（T1，整机级）"},
]
PROMOS.append(("huawei-ascend-910c.json", "fp16_tflops", "752/626",
               "Atlas 800T A3 超节点技术白皮书（整机级，训练）", P_A3T["url"],
               [CONF_910C[0]], {}))
PROMOS.append(("huawei-ascend-910c.json", "fp32_tflops", "198/165",
               "Atlas 800T A3 超节点技术白皮书（整机级，训练）", P_A3T["url"],
               [CONF_910C[1]], {}))
PROMOS.append(("huawei-ascend-910c.json", "memory_capacity", "128",
               "白皮书：整机片上内存 1024GB／单模组最大 128GB；本字段取单模组口径",
               P_A3T["url"],
               [{"source_url": P_A3T["url"], "value": "1024", "unit": "GB",
                 "note": "同一白皮书的超节点整机（满配）口径"},
                {"source_url": P_A3I["url"], "value": "1024", "unit": "GB",
                 "note": "Atlas 800I A3 推理超节点整机口径（T1）"}],
               {"unit": "GB"}))
PROMOS.append(("huawei-ascend-910c.json", "memory_bandwidth", "3200",
               "白皮书原文：带宽速率最大为 2*1600GB/s；本字段折算为 3200GB/s",
               P_A3T["url"], [], {"unit": "GB/s"}))


# ---------- 3) 逐卡迁移 ----------
changelog = []
files = sorted(f for f in os.listdir(CHIPS) if f.endswith(".json"))
promo_by_file = {}
for fn, k, v, note, url, extra, ov in PROMOS:
    promo_by_file.setdefault(fn, []).append((k, v, note, url, extra, ov))

stats = {"promoted": 0, "downgraded": 0, "tier_set": 0, "conflict_tier": 0}
FILE_MAP = {}
for fn in files:
    path = os.path.join(CHIPS, fn)
    C = json.load(open(path, encoding="utf-8"))
    FILE_MAP[fn] = C
    applied = promo_by_file.get(fn, [])

    if applied:
        changelog.append({"date": tiers.DATA_CUTOFF, "chip": C["model"], "scope": "card",
                          "change": "t1-promotion",
                          "from": "字段主来源为聚合源(T3)",
                          "to": "字段主来源改为厂商官方来源(T1)：%s" % slug_of(applied[0][3]),
                          "to_url": applied[0][3],
                          "reason": "R44/D2：T1 官方证据到位，verified 仅可由 T1 支撑"})

    for k, f in C["fields"].items():
        old_tier = tiers.tier_of(f.get("source_url"))
        f["source_tier"] = old_tier
        f["last_verified"] = tiers.LAST_VERIFIED
        stats["tier_set"] += 1
        for cf in (f.get("conflict_with") or []):
            cf["source_tier"] = tiers.tier_of(cf.get("source_url"))
            cf.setdefault("last_verified", tiers.LAST_VERIFIED)
            stats["conflict_tier"] += 1

        # 官方提升
        for pk, pv, pnote, purl, extra, ov in applied:
            if pk != k:
                continue
            old_val, old_src, old_unit = f.get("value"), f.get("source_url"), f.get("unit", "")
            if old_val != pv or old_src != purl:
                if old_val not in (pv, None) and old_src and old_src != purl:
                    f.setdefault("conflict_with", [])
                    if not [c for c in f["conflict_with"] if c.get("source_url") == old_src and c.get("value") == old_val]:
                        f["conflict_with"].append({
                            "source_url": old_src, "value": old_val, "unit": old_unit,
                            "source_date": f.get("source_date", tiers.DATA_CUTOFF),
                            "note": "r40 原入库口径（%s）；保留用于追溯" % old_tier,
                            "source_tier": old_tier, "last_verified": tiers.LAST_VERIFIED})
                changelog.append({
                    "date": tiers.DATA_CUTOFF, "chip": C["model"], "field": k,
                    "change": "value/source",
                    "from": "%s（%s，%s）" % (old_val, old_tier, slug_of(old_src)),
                    "from_url": old_src,
                    "to": "%s（T1，%s）" % (pv, slug_of(purl)), "to_url": purl,
                    "reason": pnote})
                f["value"] = pv
            for cf in extra:
                f.setdefault("conflict_with", [])
                if not [c for c in f["conflict_with"] if c.get("source_url") == cf["source_url"] and c.get("value") == cf["value"] and c.get("unit") == cf.get("unit")]:
                    cf = dict(cf)
                    cf.setdefault("source_date", tiers.DATA_CUTOFF)
                    cf["source_tier"] = tiers.tier_of(cf["source_url"])
                    cf["last_verified"] = tiers.LAST_VERIFIED
                    f["conflict_with"].append(cf)
            for kk, vv in ov.items():
                f[kk] = vv
            if k in UNIT_FIX:
                f["unit"] = UNIT_FIX[k]
            f["source_url"] = purl
            f["source_date"] = tiers.DATA_CUTOFF
            f["confidence"] = "verified"
            f["source_tier"] = tiers.T1
            f["note"] = pnote
            stats["promoted"] += 1

        # 重新计算 tier（冲突也可能含 T1）
        all_src = [f.get("source_url")] + [c.get("source_url") for c in (f.get("conflict_with") or [])]
        has_t1 = any(tiers.tier_of(u) == tiers.T1 for u in all_src if u)
        f["source_tier"] = tiers.tier_of(f.get("source_url"))

        # D2 硬规则：无 T1 → 不得 verified
        if f.get("confidence") == "verified" and not has_t1:
            f["confidence"] = "single-source"
            stats["downgraded"] += 1
            changelog.append({
                "date": tiers.DATA_CUTOFF, "chip": C["model"], "field": k,
                "change": "confidence",
                "from": "verified", "to": "single-source",
                "reason": "R44/D2 硬规则：该字段无 T1（厂商官方）来源，verified 不成立"})

    json.dump(C, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(path, "a", encoding="utf-8").write("\n")

P("files migrated: %d" % len(files))
P("promoted=%d downgraded=%d tier_set=%d conflict_tier=%d" %
  (stats["promoted"], stats["downgraded"], stats["tier_set"], stats["conflict_tier"]))
P("unknown hosts (no explicit DOMAIN_RULES match): %s" % (sorted(tiers.UNKNOWN_HOSTS) or "none"))

# ---------- 4) 校验 + 变更记录落盘 ----------
dist = {}
for C in FILE_MAP.values():
    for k, f in C["fields"].items():
        dist[f.get("source_tier")] = dist.get(f.get("source_tier"), 0) + 1
P("source_tier distribution (by primary source): %s" % json.dumps(dist, ensure_ascii=False, sort_keys=True))

changelog.sort(key=lambda e: (e["chip"], e.get("field", ""), e["change"]))
CL = {
    "date": tiers.DATA_CUTOFF,
    "note": "R44/P6-P10 字段级变更记录：来源分级(D2)、T1 官方证据提升、置信度降级、登记新增官方来源。",
    "new_sources": [{"slug": s, "url": pr["url"], "tier": tiers.T1, "bytes": pr.get("bytes")}
                    for s, pr, _t, _v in NEW_SOURCES],
    "entries": changelog,
}
json.dump(CL, open(os.path.join(SITE, "data", "changelog.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, sort_keys=False)
open(os.path.join(SITE, "data", "changelog.json"), "a", encoding="utf-8").write("\n")
P("changelog entries: %d" % len(changelog))
open(os.path.join(TEMP, "r44c_migrate_report.txt"), "w", encoding="utf-8").write("\n".join(log) + "\n")
P("wrote temp/r44c_migrate_report.txt")
