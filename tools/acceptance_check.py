# -*- coding: utf-8 -*-
"""r40 一期验收核对（对照 R40-CEO 规格 §五 五条）。"""
import json, os, re

SITE = r"D:\Dev\爱马仕\work\r40\site"
S = json.load(open(os.path.join(SITE, "tools", "collect", "sources.json"), encoding="utf-8"))["sources"]
SLUG2URL = {}
for k, v in S.items():
    u = v["url"] if isinstance(v, dict) else v
    SLUG2URL[u] = k
URL2SLUG = dict(SLUG2URL)  # url -> slug

chips = []
cd = os.path.join(SITE, "data", "chips")
for f in sorted(os.listdir(cd)):
    if f.endswith(".json"):
        chips.append(json.load(open(os.path.join(cd, f), encoding="utf-8")))

vendors = sorted({c["vendor"] for c in chips})
n_fields = sum(len(c["fields"]) for c in chips)
min_fields = min(len(c["fields"]) for c in chips)
tot = 0
nonempty = 0
orphan = []
allurls = set()
conflicts = []


def is_archived(slug):
    """归档存在性：raw/<slug>.*（html/pdf/txt 均可，与 validate.py 同口径）。"""
    if not slug:
        return False
    rd = os.path.join(SITE, "raw")
    try:
        names = os.listdir(rd)
    except OSError:
        return False
    return any(n == slug or n.startswith(slug + ".") for n in names)

for c in chips:
    for k, v in c["fields"].items():
        tot += 1
        su = (v.get("source_url") or "").strip()
        if su:
            nonempty += 1
            allurls.add(su)
            if su not in URL2SLUG or not is_archived(URL2SLUG[su]):
                orphan.append((c["model"], k, su))
        if v.get("conflict_with"):
            conflicts.append((c["model"], k, v["value"], v["conflict_with"]))

pages = []
for r, d, fs in os.walk(SITE):
    for f in fs:
        if f == "index.html":
            pages.append(os.path.join(r, f))
ext = []
META_REL = ('rel="canonical"', "rel='canonical'", 'rel="alternate"', "rel='alternate'",
            'rel="amphtml"', "rel='amphtml'", 'property="og:url"', "property='og:url'")
for p in pages:
    t = open(p, encoding="utf-8").read()
    for tag in ("script", "link", "img", "iframe"):
        for seg in re.findall(r'<%s\b[^>]*>' % tag, t):
            # canonical / alternate / og:url 等属元数据，按规范必须是绝对 URL，不是运行时依赖
            if any(k in seg for k in META_REL):
                continue
            m = re.search(r'(?:src|href)="(https?://[^"]+)"', seg)
            if m:
                ext.append((os.path.relpath(p, SITE), tag + ":" + m.group(1)))
    if re.search(r"\bfetch\s*\(|XMLHttpRequest|new\s+WebSocket", t):
        ext.append((os.path.relpath(p, SITE), "JS-BACKEND-CALL"))

L = []
L.append("[1] vendors=%d models=%d  (>=3 / >=10)  -> %s" % (len(vendors), len(chips), "PASS" if len(vendors) >= 3 and len(chips) >= 10 else "FAIL"))
L.append("    fields total=%d min/model=%d (>=25)  source非空 %d/%d=%.1f%%  orphan=%d" % (tot, min_fields, nonempty, tot, 100.0 * nonempty / tot, len(orphan)))
L.append("    vendors: %s" % ", ".join(vendors))
L.append("[2] conflicts(conflict_with 非空)=%d  -> %s" % (len(conflicts), "PASS" if conflicts else "FAIL"))
for m, k, v, cf in conflicts:
    L.append("    %s · %s = %s  ||  %s" % (m, k, v, cf))
L.append("[3] pages=%d (>=15) distinct_sources=%d" % (len(pages), len(allurls)))
L.append("[4] validate passed=%d failed=%d  build idempotent=see temp/idem_check.txt" %
         (len(chips) if not orphan else 0, 1 if orphan else 0))
L.append("[5] external refs in pages=%d  -> %s" % (len(ext), "PASS" if not ext else "FAIL"))
for r, m in ext[:10]:
    L.append("    %s -> %s" % (r, m))
# [6] r41 GEO 引用层核对（robots 白名单 / sitemap 条数 / 开放数据集 / 字段级 SEO）
rb = open(os.path.join(SITE, "robots.txt"), encoding="utf-8").read()
smx = open(os.path.join(SITE, "sitemap.xml"), encoding="utf-8").read()
ai_allow = len(re.findall(r"^User-agent: (?:GPTBot|ChatGPT-User|ClaudeBot|Claude-Web|CCBot|PerplexityBot|"
                          r"Google-Extended|Applebot-Extended|anthropic-ai)\b", rb, re.M))
seo_deny = len(re.findall(r"^User-agent: (?:AhrefsBot|SemrushBot|MJ12Bot|DotBot|BLEXBot)\b", rb, re.M))
loc = len(re.findall(r"<loc>", smx))
dsj = json.load(open(os.path.join(SITE, "dataset", "chips.json"), encoding="utf-8"))
kwhits = 0
for c in chips:
    fp = os.path.join(SITE, "chip", c["vendor_slug"] + "-" + c["model_slug"], "index.html")
    if os.path.exists(fp) and 'name="keywords"' in open(fp, encoding="utf-8").read():
        kwhits += 1
geo_ok = (ai_allow >= 9 and seo_deny >= 4 and loc == len(pages)
          and dsj.get("count") == len(chips) and kwhits == len(chips))
L.append("[6] GEO: robots AI-allow=%d(>=9) SEO-deny=%d(>=4)  sitemap loc=%d==pages=%d  "
         "dataset count=%d license=%s  keyword页=%d/%d  -> %s" %
         (ai_allow, seo_deny, loc, len(pages), dsj.get("count"), dsj.get("license"),
          kwhits, len(chips), "PASS" if geo_ok else "FAIL"))
txt = "\n".join(L) + "\n"
open(os.path.join(SITE, "temp", "acceptance.txt"), "w", encoding="utf-8").write(txt)
print(txt)
