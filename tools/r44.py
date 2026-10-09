# -*- coding: utf-8 -*-
"""R44 站点增强层（P6–P10 / D1–D5），由 tools/build.py 在常规页面写完后调用 apply()。

  D1 对比页交互：<button id="do-compare">（初始 disabled，选 2–4 个后 enabled，点击出并排表 + 滚动定位）、
                  实时选中计数、差异字段底色高亮、缺失值「未公开」+ tier 徽标、移动端宽表横滚。
  D2 来源分级：字段级 source_tier（T1/T2/T3）徽标；/sources/ 按 tier 分组并可点回原文。
  D3 决策页：新增 /guide/（场景×约束×推荐×采购清单×验收证据，每场景 ≥3 型号 + tier）。
  D4 时效：每页顶部「数据截止 YYYY-MM-DD｜本页 N 字段：T1 a／T2 b／T3 c／未公开 d」+ 字段级 last_verified；
            新增 /changelog/（字段变更记录）；两页均进 sitemap。
  D5 视觉：主色 #0a63c2 + 语义色、KPI 卡片、关键数字 ≥28px、对比表 sticky 表头 + 斑马纹、
            正文「结论先行 + 折叠明细」。

纯静态（内联 <style>/<script>，零外部依赖）、无网络、无构建时间戳（静态日期来自 tools/tiers.py）。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiers as T  # noqa: E402

MARK = "<!-- r44-post -->"
UND = "未公开"
FOOTER_RE = re.compile(r"<hr><p class=\"muted\">构建:")

CSS = (
    "<style>/* R44/D5：主色 #0a63c2 + 语义色（绿=T1已证实 黄=来源冲突/差异 灰=未公开 红=风险） */\n"
    ":root{--r44-main:#0a63c2;--r44-t1:#0f7b3f;--r44-t1-bg:#e6f4ec;--r44-t2:#1f6fb2;--r44-t2-bg:#e8f1fa;"
    "--r44-t3:#6b7280;--r44-t3-bg:#f1f1f3;--r44-warn:#8a6d0b;--r44-warn-bg:#fdf6e3;--r44-risk:#b3261e;"
    "--r44-risk-bg:#fdecea}\n"
    ".r44-bar{margin:6px 0 14px;padding:7px 10px;border:1px solid #e3e3e6;border-left:3px solid var(--r44-main);"
    "border-radius:4px;background:#fafbfc;font-size:12.5px;color:#3d3d42}\n"
    ".r44-bar b{color:var(--r44-main)}\n"
    ".r44-lead{background:#f7fafd;border:1px solid #dde8f4;border-radius:6px;padding:10px 12px;margin:10px 0}\n"
    ".kpi{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 14px;padding:0;list-style:none}\n"
    ".kpi li{flex:1 1 150px;min-width:140px;border:1px solid #e6e6ea;border-radius:8px;padding:10px 12px;background:#fff}\n"
    ".kpi span{display:block;font-size:12px;color:#666}\n"
    ".kpi b{display:block;font-size:30px;line-height:1.15;color:var(--r44-main);font-weight:700}\n"
    ".kpi small{display:block;color:#666;font-size:11.5px}\n"
    ".big{font-size:30px;font-weight:700;color:var(--r44-main)}\n"
    ".tier{display:inline-block;font-size:11.5px;line-height:1.55;padding:0 6px;border-radius:9px;"
    "border:1px solid transparent;font-weight:600;white-space:nowrap}\n"
    ".tier.t1{color:var(--r44-t1);background:var(--r44-t1-bg);border-color:#b7dfc7}\n"
    ".tier.t2{color:var(--r44-t2);background:var(--r44-t2-bg);border-color:#c6dcf0}\n"
    ".tier.t3{color:var(--r44-t3);background:var(--r44-t3-bg);border-color:#dcdce1}\n"
    ".tier.t-und{color:#6b7280;background:#f6f6f8;border-color:#e2e2e6}\n"
    ".tier.t-warn{color:var(--r44-warn);background:var(--r44-warn-bg);border-color:#efdfae}\n"
    ".und{color:#6b7280;background:#f6f6f8;padding:0 5px;border-radius:3px}\n"
    "details.r44-detail{margin:10px 0}\n"
    "details.r44-detail>summary{cursor:pointer;font-weight:600;color:var(--r44-main);padding:5px 0}\n"
    "tbody tr:nth-child(even){background:#fafafb}\n"
    "th{background:#f5f5f7;position:sticky;top:0;z-index:2}\n"
    "tr.diff td{background:var(--r44-warn-bg)}\n"
    "td.hl{background:var(--r44-warn-bg)}\n"
    "#out table{min-width:520px}\n"
    "#out table th:first-child,#out table td:first-child{position:sticky;left:0;background:#fff;z-index:1}\n"
    "#out table tr.diff td:first-child,#out table tr.diff th:first-child{background:var(--r44-warn-bg)}\n"
    "#do-compare{font:inherit;padding:6px 14px;border-radius:6px;border:1px solid var(--r44-main);"
    "background:var(--r44-main);color:#fff;cursor:pointer}\n"
    "#do-compare[disabled]{background:#c9ccd2;border-color:#c9ccd2;cursor:not-allowed}\n"
    "#cnt{margin-left:8px;font-size:13px}\n"
    "@media(max-width:600px){.kpi b{font-size:28px}#out{overflow-x:auto}}\n"
    "</style>"
)


# ---------------- 数据读取 ----------------
def load_chips(site):
    d = os.path.join(site, "data", "chips")
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            C = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            C["_file"] = fn
            C["_slug"] = "%s-%s" % (C["vendor_slug"], C["model_slug"])
            out.append(C)
    return out


def load_sources(site):
    doc = json.load(open(os.path.join(site, "tools", "collect", "sources.json"), encoding="utf-8"))
    return doc.get("sources", {})


def stats_of(fields):
    st = {"total": 0, "T1": 0, "T2": 0, "T3": 0, UND: 0}
    for k, v in fields.items():
        st["total"] += 1
        val = str(v.get("value", "")).strip()
        if v.get("confidence") == "unverified" or val in (UND, ""):
            st[UND] += 1
        else:
            st[v.get("source_tier") or T.tier_of(v.get("source_url"))] += 1
    return st


def bar(st, scope="本页"):
    return ("数据截止 %s ｜ %s %d 字段：T1 %d／T2 %d／T3 %d／未公开 %d "
            "<span class=\"muted\">（字段级 last_verified %s）</span>"
            % (T.DATA_CUTOFF, scope, st["total"], st["T1"], st["T2"], st["T3"], st[UND], T.LAST_VERIFIED))


def badge(tier, text=None):
    cls = {"T1": "t1", "T2": "t2", "T3": "t3", None: "t-und", "": "t-und"}.get(tier, "t3")
    return '<span class="tier %s" title="%s">%s</span>' % (
        cls, T.TIER_DESC.get(tier, "未公开/未知来源"), text or (T.TIER_LABEL.get(tier, tier)))


def numval(f):
    """取字段值中的第一个数字（用于排序，不改写数据）。"""
    m = re.search(r"\d+(?:\.\d+)?", str((f or {}).get("value", "")))
    return float(m.group(0)) if m else -1.0


def cell(f):
    """字段值单元格：未公开 → 灰底 + 未公开徽标；否者值 + tier 徽标 + 核验日期。"""
    v = (f or {}).get("value", "")
    v = str(v).strip()
    if (not v) or v == UND or (f or {}).get("confidence") == "unverified":
        return ('<span class="und">%s</span> %s <small class="muted">last_verified %s</small>'
                % (UND, badge(UND, "未公开"), T.LAST_VERIFIED))
    unit = (f or {}).get("unit", "")
    unit = "" if unit in ("n/a", "-") else (" " + unit)
    return ("%s%s %s <small class=\"muted\">last_verified %s</small>"
            % (_esc(v), _esc(unit), badge((f or {}).get("source_tier")), T.LAST_VERIFIED))


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------- 页面后处理 ----------------
def _und_badge(html):
    """D1/D2：缺失值显「未公开」并带灰色徽标。"""
    return html.replace('<p>未公开</p>',
                        '<p><span class="und">未公开</span> <span class="tier t-und">未公开</span></p>')


def add_tier_column(html, by_slug):
    """D2：矩阵页（chips/stacks/operators）每行补「来源分级覆盖」列。"""
    def row(m):
        r = m.group(0)
        mm = re.search(r'chip/([A-Za-z0-9_\-]+)/', r)
        if mm and mm.group(1) in by_slug:
            s = stats_of(by_slug[mm.group(1)]["fields"])
            cov = " ".join([badge("T1", "T1 %d" % s["T1"]), badge("T2", "T2 %d" % s["T2"]),
                            badge("T3", "T3 %d" % s["T3"]), badge(UND, "未公开 %d" % s[UND])])
            return r[:-5] + "<td>%s</td></tr>" % cov if r.endswith("</tr>") else r
        if "<th" in r:
            return r[:-5] + "<th>来源分级覆盖</th></tr>" if r.endswith("</tr>") else r
        return r
    return re.sub(r"<tr[^>]*>.*?</tr>", row, html, flags=re.S)


def _fix_archive_names(site, html):
    def rep(m):
        slug = m.group(1)
        for f in sorted(os.listdir(os.path.join(site, "raw"))):
            if f == slug or f.startswith(slug + "."):
                return "<code>raw/%s</code>" % f
        return m.group(0)
    return re.sub(r"<code>raw/([A-Za-z0-9_\-]+)\.html</code>", rep, html)


def _add_tier_badges(html):
    """在字段来源行补 tier 徽标 + last_verified（D2/D4）。"""
    def rep(m):
        head, url, rest = m.group(1), m.group(2), m.group(3)
        tier = T.tier_of(url)
        return "%s%s · tier %s · last_verified %s</p>" % (head, rest, badge(tier), T.LAST_VERIFIED)
    return re.sub(r'(<p class="muted">来源: <a href="([^"]*)">)(.*?)(</p>)', rep, html, flags=re.S)


def _add_banner(html, text):
    if "</nav>" not in html:
        return html
    i = html.index("</nav>") + len("</nav>")
    return html[:i] + '\n<div class="r44-bar">%s</div>' % text + html[i:]


def enhance_chip(site, path, html, chip, st):
    """芯片页：KPI 卡片 + 结论先行 + 折叠明细。"""
    f = chip["fields"]
    fp16 = f.get("fp16_tflops", {})
    mem = f.get("memory_capacity", {})
    bw = f.get("memory_bandwidth", {})
    tdp = f.get("tdp", {})
    kpi = ["<ul class=\"kpi\">"]
    for lab, fld, unit in [("FP16 算力", fp16, "TFLOPS"), ("显存容量", mem, "GB"),
                           ("显存带宽", bw, "GB/s"), ("最大功耗", tdp, "W")]:
        val = str(fld.get("value", "")).strip()
        unit2 = str(fld.get("unit", "")).strip()
        shown = UND if (not val or val == UND) else val
        kpi.append("<li><span>%s</span><b>%s</b><small>%s %s</small></li>" % (
            lab, _esc(shown), _esc(unit2 or unit), badge(fld.get("source_tier") if val and val != UND else UND,
                                                         "公开" if val and val != UND else "未公开")))
    kpi.append("</ul>")
    und = [k for k, v in f.items() if str(v.get("value", "")).strip() in ("", UND)
           or v.get("confidence") == "unverified"]
    lead = ("<p class=\"r44-lead\">结论先行：<b>%s</b>（%s）——FP16 %s、显存 %s、带宽 %s；"
            "本卡 %d 字段中 T1 %d／T2 %d／T3 %d／未公开 %d，%s</p>" % (
                _esc(chip["model"]), _esc(str(f.get("category", {}).get("value", ""))),
                _esc(str(fp16.get("value", UND))), _esc(str(mem.get("value", UND))),
                _esc(str(bw.get("value", UND))), st["total"], st["T1"], st["T2"], st["T3"], st[UND],
                ("其中 %d 个字段公开口径未给出（未公开），采购/立项前需厂商书面确认。" % len(und))
                if und else "全部字段均有公开来源。"))
    h = html
    i = h.index("</h1>") + len("</h1>")
    h = h[:i] + "\n" + lead + "\n" + "".join(kpi) + \
        '<details class="r44-detail" open><summary>字段明细（%d 项，可折叠）</summary>' % st["total"] + h[i:]
    j = FOOTER_RE.search(h)
    if j:
        h = h[:j.start()] + "</details>\n" + h[j.start():]
    else:
        h = h.replace("</body>", "</details>\n</body>", 1)
    return h


def enhance_compare(site, html, chips):
    tier_map = {}
    for C in chips:
        tier_map[C["_slug"]] = {k: (v.get("source_tier") or T.tier_of(v.get("source_url")))
                                for k, v in C["fields"].items()}
    if '<button id="do-compare"' not in html:
        html = html.replace('<div id="out"></div>',
                            '<p><button id="do-compare" type="button" disabled>对比选中型号</button>'
                            '<span id="cnt" class="muted">已选 0 个</span></p>\n<div id="out"></div>', 1)
    js = (
        "<script>/* R44/D1 对比交互（纯前端，无外部依赖） */"
        "(function(){var TIER=%s,UND='未公开',LV='%s';"
        "function slugOf(u){var m=String(u||'').match(/chip\\/([^\\/]+)\\//);return m?m[1]:'';}"
        "function sel(){var bx=document.querySelectorAll('#sel input'),r=[];"
        "for(var i=0;i<bx.length;i++){if(bx[i].checked)r.push(+bx[i].value);}return r;}"
        "function badge(t,isUnd){if(isUnd)return '<span class=\"tier t-und\">未公开</span>';"
        "var c=(t==='T1')?'t1':(t==='T2')?'t2':'t3';return '<span class=\"tier '+c+'\">'+t+'</span>';}"
        "function setState(){var n=sel().length,btn=document.getElementById('do-compare'),"
        "c=document.getElementById('cnt'),h=document.getElementById('hint');"
        "if(c)c.textContent='已选 '+n+' 个';if(btn)btn.disabled=!(n>=2&&n<=4);"
        "if(h)h.textContent=(n>=2&&n<=4)?('已选 '+n+' 个型号，点击「对比选中型号」生成并排表。')"
        ":('请选择 2–4 个型号（当前 '+n+' 个）。');}"
        "window.upd=setState;"
        "function render(){var idx=sel();if(idx.length<2||idx.length>4)return;"
        "var out=document.getElementById('out'),x='<table><thead><tr><th>字段</th>';"
        "for(var j=0;j<idx.length;j++){x+='<th>'+esc(D[idx[j]].v+' '+D[idx[j]].m)+'</th>';}"
        "x+='</tr></thead><tbody>';"
        "for(var k=0;k<F.length;k++){var key=F[k][0],any=false,vals=[];"
        "for(var j2=0;j2<idx.length;j2++){var v=D[idx[j2]].f[key];if(v)any=true;"
        "vals.push((v===undefined||v===null||v===''||v==='—')?UND:String(v));}"
        "if(!any)continue;var same=true;for(j2=1;j2<vals.length;j2++){if(vals[j2]!==vals[0])same=false;}"
        "x+='<tr'+(same?'':' class=\"diff\"')+'><th>'+esc(F[k][1])+'</th>';"
        "for(j2=0;j2<idx.length;j2++){var val=vals[j2],isUnd=(val===UND),"
        "t=TIER[slugOf(D[idx[j2]].u)]||{},tv=t[key];"
        "x+='<td class=\"'+(same?'':'hl')+'\">'+(isUnd?'<span class=\"und\">未公开</span>':esc(val))"
        "+' '+badge(tv,isUnd)+' <small class=\"muted\">核验 '+LV+'</small></td>';}"
        "x+='</tr>';}x+='</tbody></table>';out.innerHTML=x;"
        "if(out.scrollIntoView)out.scrollIntoView({behavior:'smooth',block:'start'});}"
        "var b=document.getElementById('do-compare');if(b)b.addEventListener('click',render);"
        "var bx=document.querySelectorAll('#sel input');"
        "for(var i=0;i<bx.length;i++){bx[i].onchange=setState;}"
        "setState();})();</script>"
    ) % (json.dumps(tier_map, ensure_ascii=False, sort_keys=True).replace("</", "<\\/"), T.LAST_VERIFIED)
    if "R44/D1 对比交互" not in html:
        html = html.replace("</body>", js + "\n</body>", 1)
    return html


def rebuild_sources(site, html, srcs):
    """D2：/sources/ 按 tier 分组展示，可点回原文（URL）与归档文件。"""
    rows = {t: [] for t in ("T1", "T2", "T3")}
    for slug in sorted(srcs):
        ent = srcs[slug]
        url = ent.get("url", "") if isinstance(ent, dict) else str(ent)
        tier = (ent.get("tier") if isinstance(ent, dict) else None) or T.tier_of(url)
        arch = "-"
        for f in sorted(os.listdir(os.path.join(site, "raw"))):
            if f == slug or f.startswith(slug + "."):
                p = os.path.join(site, "raw", f)
                arch = "<code>raw/%s</code> <small>%d B</small>" % (f, os.path.getsize(p))
                break
        title = ent.get("title", "") if isinstance(ent, dict) else ""
        rows[tier].append("<tr><td>%s</td><td>%s</td><td><a href=\"%s\">%s</a></td><td>%s</td></tr>"
                          % (_esc(slug), _esc(title or "-"), _esc(url), _esc(url), arch))
    body = ["<p class=\"muted\">按来源分级（D2）分组；点 URL 回原文。"
            "T1=厂商官网/白皮书/官方文档，T2=工信安全认证/招投标/证券披露/vLLM·SGLang 官方文档，"
            "T3=mirrorfrog、flopper、个人博客等聚合二手。归档原文 <code>raw/</code> 仅存于工作副本、不随站点发布。</p>"]
    for t in ("T1", "T2", "T3"):
        body.append("<h2>%s %s<span class=\"muted\">（%d 条）</span></h2>" % (
            badge(t), _esc(T.TIER_DESC[t]), len(rows[t])))
        body.append("<table><tr><th>slug</th><th>标题</th><th>URL</th><th>归档</th></tr>%s</table>"
                    % "".join(rows[t]))
    body.append("<p class=\"muted\">字段级 <code>source_tier</code> 与 <code>last_verified</code> 见各卡片页；"
                "变更历史见 <a href=\"../changelog/\">变更记录</a>。</p>")
    new_body = "\n".join(body)
    h = html
    i = h.index("</h1>") + len("</h1>")
    j = FOOTER_RE.search(h)
    if j:
        h = h[:i] + "\n" + new_body + "\n" + h[j.start():]
    else:
        h = h[:i] + "\n" + new_body + "\n</body></html>"
    return h


def _rel(html, path):
    """按页面深度生成站内相对链接（与 build.py 的 R() 同规则）。"""
    m = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    depth = 0
    if m:
        tail = m.group(1).split("/mapmatch-health-check", 1)[-1].strip("/")
        depth = len([x for x in tail.split("/") if x])
    return ("./" if depth == 0 else "../" * depth) + path


# ---------------- 新增页面：/guide/、/changelog/ ----------------
def guide_body(chips, srcs):
    b = ["<h2>怎么用这一页</h2>",
         "<p class=\"muted\">按「场景 → 约束 → 推荐 → 采购清单 → 验收证据」五步给结论。"
         "所有结论由 <code>data/chips/*.json</code> 字段机械推出，不引入估算；"
         "每个型号后附该型号关键字段的来源分级（T1 厂商官方／T2 权威第三方／T3 聚合二手／未公开）。</p>"]
    scen = [
        ("训练（预训练/SFT 大吞吐）", "训练",
         lambda c: (-numval(c["fields"].get("fp16_tflops")), -numval(c["fields"].get("memory_bandwidth"))),
         "FP16/BF16 算力与卡间/显存带宽主导"),
        ("推理（在线服务/高并发）", "推理",
         lambda c: (-numval(c["fields"].get("int8_tops")), -numval(c["fields"].get("fp16_tflops"))),
         "INT8 吞吐与显存容量主导（量化部署）"),
        ("微调（LoRA/全参对齐）", "微调",
         lambda c: (-numval(c["fields"].get("memory_capacity")), -numval(c["fields"].get("memory_bandwidth"))),
         "显存容量与带宽主导"),
    ]
    for title, key, sk, why in scen:
        ranked = sorted(chips, key=sk)[:4]
        b.append("<h2>场景：%s</h2>" % _esc(title))
        b.append("<p class=\"muted\">约束口径：显存 / 带宽 / 生态 / 合规 / 功耗。%s。</p>" % _esc(why))
        b.append("<table><tr><th>推荐序</th><th>型号</th><th>关键字段（含来源分级）</th>"
                 "<th>可执行结论</th><th>采购清单要点</th><th>验收证据</th></tr>")
        for i, C in enumerate(ranked, 1):
            f = C["fields"]
            kf = " ".join(cell(f.get(k)) for k in ("fp16_tflops", "memory_capacity",
                                                   "memory_bandwidth", "tdp"))
            top = f.get("fp16_tflops" if key != "推理" else "int8_tops", {})
            _tf = "fp16_tflops" if key != "推理" else "int8_tops"
            _tierphr = ("来源分级 T1（厂商官方），可直接引用"
                        if top.get("source_tier") == "T1" else
                        "来源分级 %s（%s），采购前需书面复核"
                        % (top.get("source_tier") or "T3",
                           T.TIER_LABEL.get(top.get("source_tier"), UND)))
            concl = ("%s：<code>%s</code> 主导——%s；生态侧以 <code>%s</code> 起步，迁移路径见算子页。"
                     % ("首选" if i == 1 else "备选 %d" % i, _tf, _tierphr,
                        _esc(str(C["fields"].get("software_stack", {}).get("value", UND)))))
            buy = "要求厂商书面给出 %s 的最终值并注明整机/单卡口径（本卡当前 %s）。" % (
                _esc(why), badge(top.get("source_tier")))
            if numval(f.get("tdp")) < 0:
                buy += " 功耗未公开，需机房配电口径确认。"
            ev = "字段 <code>%s</code>／<code>%s</code> 须落到 T1 源（厂商白皮书/官网），" \
                 "并保留 raw/ 归档指纹；当前 T1 %d／T2 %d／T3 %d／未公开 %d。" % (
                     "fp16_tflops" if key != "推理" else "int8_tops", "memory_capacity",
                     stats_of(f)["T1"], stats_of(f)["T2"], stats_of(f)["T3"], stats_of(f)[UND])
            b.append("<tr><td>%d</td><td><b><a href=\"../chip/%s/\">%s</a></b><br><small>%s · %s</small></td>"
                     "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                     % (i, _esc(C["_slug"]), _esc(C["model"]), _esc(C["vendor"]), _esc(C["_slug"]),
                        kf, concl, buy, ev))
        b.append("</table>")
        b.append("<p class=\"muted\">采购清单要点（通用）：① 显存/带宽按单卡口径写明，整机口径单列；"
                 "② 要求 <code>raw/</code> 归档的官方白皮书页码或官网 URL；③ 生态项（算子库/CUDA 兼容层）"
                 "以官方文档版本号验收；④ 合规项以工信安全测评公告为准（T2）；⑤ 交付前复跑 "
                 "<code>python tools/validate.py</code> 全绿。</p>")
    b.append("<h2>口径与边界</h2><p class=\"muted\">本页不含价格、交期与商业判断；推荐序仅由入库字段排序得出，"
             "字段缺失（未公开）不参与排序，并在结论中显式标注。字段级来源分级与最近核验见对应型号卡片页。</p>")
    return "\n".join(b)


def _lbl(e, k):
    """变更前/后单元格：文本 + （若有）原文链接（外部绝对 URL）。"""
    s = _esc(e.get(k, ""))
    u = e.get(k + "_url")
    if u:
        s += ' <a href="%s" title="%s" rel="noopener">原文</a>' % (_esc(u), _esc(u))
    return s


def changelog_body(doc):
    b = ["<p class=\"muted\">记录字段级变更：官方证据提升（T1）、置信度降级、来源登记与分级落盘。"
         "日期为数据截止日（静态），非构建时间。</p>",
         "<p><b>数据截止</b>：%s</p>" % _esc(doc.get("date", T.DATA_CUTOFF))]
    ns = doc.get("new_sources", [])
    if ns:
        b.append("<h2>本轮新增官方来源（T1）</h2><table>"
                 "<tr><th>slug</th><th>tier</th><th>URL</th><th>归档字节</th></tr>%s</table>" % "".join(
                     "<tr><td>%s</td><td>%s</td><td><a href=\"%s\">%s</a></td><td>%s</td></tr>"
                     % (_esc(x["slug"]), badge(x.get("tier")), _esc(x["url"]), _esc(x["url"]), x.get("bytes"))
                     for x in ns))
    ent = doc.get("entries", [])
    by = {}
    for e in ent:
        by.setdefault(e.get("change", "-"), []).append(e)
    b.append("<h2>变更明细（%d 条）</h2>" % len(ent))
    b.append("<table><tr><th>日期</th><th>型号</th><th>字段</th><th>变更类型</th><th>变更前</th>"
             "<th>变更后</th><th>依据</th></tr>")
    for e in ent:
        b.append("<tr><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td>"
                 "<td class=\"muted\">%s</td></tr>" % (
                     _esc(e.get("date")), _esc(e.get("chip")), _esc(e.get("field", "-")),
                     _esc(e.get("change")), _lbl(e, "from"), _lbl(e, "to"),
                     _esc(e.get("reason", ""))))
    b.append("</table>")
    b.append("<p class=\"muted\">另：本轮为全部型号的每个字段补齐 <code>source_tier</code>（D2）"
             "与字段级 <code>last_verified</code>（D4），逐字段值见对应型号卡片页；"
             "缺失字段显「未公开」并保留来源分级。</p>")
    b.append("<h2>统计</h2><ul>%s</ul>" % "".join(
        "<li>%s：%d 条</li>" % (_esc(k), len(v)) for k, v in sorted(by.items())))
    return "\n".join(b)


# ---------------- 入口 ----------------
def apply(site, write, page, crumbs, e, R, ctx=None):
    ctx = ctx or {}
    chips = load_chips(site)
    srcs = load_sources(site)
    by_slug = {c["_slug"]: c for c in chips}
    total_fields = sum(len(c["fields"]) for c in chips)
    dst = {"total": 0, "T1": 0, "T2": 0, "T3": 0, UND: 0}
    for c in chips:
        s = stats_of(c["fields"])
        for k in dst:
            dst[k] += s[k]
    assert dst["total"] == total_fields

    # 1) 新增页面（D3 /guide/、D4 /changelog/）
    write("guide/index.html", page(
        "决策指南", guide_body(chips, srcs),
        "国产 AI 芯片决策指南：训练/推理/微调三类场景 × 显存/带宽/生态/合规/功耗约束 × 推荐配置 × "
        "采购清单要点 × 验收证据，每场景 ≥3 型号并标注来源分级 T1/T2/T3。",
        ["国产AI芯片", "决策指南", "选型", "训练", "推理", "微调", "采购清单", "来源分级"],
        1, crumbs(1, [("首页", ""), ("决策指南", None)]), "/guide/"))
    cl = json.load(open(os.path.join(site, "data", "changelog.json"), encoding="utf-8"))
    write("changelog/index.html", page(
        "变更记录", changelog_body(cl),
        "字段变更记录：官方证据(T1)提升、置信度降级、来源登记与来源分级落盘，含新增官方来源与归档字节。",
        ["变更记录", "changelog", "数据截止", "来源分级"],
        1, crumbs(1, [("首页", ""), ("变更记录", None)]), "/changelog/"))

    # 2) 全站后处理
    for root, dirs, files in os.walk(site):
        dirs[:] = [d for d in dirs if d not in ("raw", "temp", "tools", "data", ".git", "node_modules")]
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, site).replace("\\", "/")
            h = open(p, encoding="utf-8").read()
            if MARK in h:
                continue
            slug = rel.split("/")[0] == "chip" and rel.split("/")[1] if rel.startswith("chip/") else None
            st = stats_of(by_slug[slug]["fields"]) if slug in by_slug else dst
            scope = "本页" if slug in by_slug else "本页"
            h = _add_banner(h, bar(st, scope))
            h = _add_tier_badges(h)
            h = _und_badge(h)
            h = _fix_archive_names(site, h)
            if rel in ("chips/index.html", "stacks/index.html", "operators/index.html"):
                h = add_tier_column(h, by_slug)
            h = h.replace("</head>", CSS + "\n</head>", 1)
            if slug in by_slug:
                h = enhance_chip(site, rel, h, by_slug[slug], st)
            if rel == "compare/index.html":
                h = enhance_compare(site, h, chips)
            if rel == "sources/index.html":
                h = rebuild_sources(site, h, srcs)
            h = h.replace("</body>", MARK + "\n</body>", 1)
            open(p, "w", encoding="utf-8", newline="\n").write(h)
    return ["/guide/", "/changelog/"]
