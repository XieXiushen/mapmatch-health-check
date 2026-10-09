# -*- coding: utf-8 -*-
"""r40 静态站点构建器：把 data/chips/*.json 渲染为纯静态 HTML（无外部依赖、无网络、无时间戳）。
纪律:
 - 只渲染通过 tools/validate.py 校验的卡片（无来源/来源不可追溯者不入库）。
 - 输出确定性: 不使用构建时间戳、不依赖字典遍历随机性 → 两次构建产物 sha256 相同。
 - 页面路径: /  /chips/  /compare/  /chip/<厂商>-<型号>/  /stacks/  /operators/  /verdict/  /sources/  /method/  /dataset/
 - r42 修正: 站点是 GitHub Pages 项目站（前缀 /mapmatch-health-check/），所有站内 href/src 一律按
   「页面深度」生成相对链接（根页 './chips/'、chip/<slug>/ 页 '../chips/' …），构建产物 0 处根绝对链接；
   仅对外绝对 URL（canonical / sitemap <loc> / dataset 引用）使用全量前缀 SITE_URL。
用法: python tools/build.py
"""
import json, os, re, sys, html, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import validate as V  # noqa: E402

BUILD_ID = "r42-v0.3-relpath"
SITE_URL = "https://xiexiushen.github.io/mapmatch-health-check"
BASE = SITE_URL  # 对外绝对 URL 全量前缀（canonical / sitemap / dataset 引用）
LICENSE = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
YEAR = "2026"
# r41 GEO 引用层：显式放行的 AI/检索直取器（逐条 User-agent + Allow: /）
AI_BOTS = ["GPTBot", "ChatGPT-User", "ClaudeBot", "Claude-Web", "CCBot",
           "PerplexityBot", "Google-Extended", "Applebot-Extended", "anthropic-ai"]
# 明确拒绝的 SEO/反链采集器
SEO_BOTS = ["AhrefsBot", "SemrushBot", "MJ12Bot", "DotBot", "BLEXBot"]
# 站根相对路径（生成时按深度转相对链接）
NAV = [("", "首页"), ("chips/", "芯片卡片"), ("compare/", "型号对比"), ("stacks/", "软件栈"),
       ("operators/", "算子生态"), ("verdict/", "结论"), ("guide/", "决策指南"),
       ("changelog/", "变更记录"), ("dataset/", "数据集"),
       ("sources/", "来源"), ("method/", "方法")]
FIELD_LABEL = {
    "vendor": "厂商", "series": "产品系列", "model": "型号", "category": "定位",
    "process_node": "制程", "architecture": "架构", "form_factor": "板型/接口", "launch_date": "上市时间",
    "memory_capacity": "显存容量", "memory_type": "显存类型", "memory_bandwidth": "显存带宽",
    "interconnect_bw": "片间互联", "host_interface": "主机接口",
    "fp64_tflops": "FP64", "fp32_tflops": "FP32", "fp16_tflops": "FP16", "bf16_tflops": "BF16",
    "fp8_tflops": "FP8", "int16_tops": "INT16", "int8_tops": "INT8", "tdp": "功耗",
    "software_stack": "软件栈", "instruction_set": "指令集", "programming_model": "编程模型",
    "cuda_compat": "CUDA 兼容层", "operator_lib": "算子库", "operator_coverage": "算子覆盖率",
    "missing_ops": "缺失算子", "custom_op": "自定义算子", "migration_tool": "迁移工具",
    "inference_engine": "推理后端", "framework_support": "框架支持", "certification": "安全可靠认证",
    "target_workload": "目标负载",
}
PRIMARY = ["category", "process_node", "architecture", "memory_capacity", "memory_type",
           "memory_bandwidth", "fp16_tflops", "int8_tops", "tdp", "software_stack",
           "cuda_compat", "certification"]
SW_FIELDS = ["software_stack", "instruction_set", "programming_model", "cuda_compat",
             "operator_lib", "inference_engine", "framework_support", "migration_tool"]
OP_FIELDS = ["operator_lib", "operator_coverage", "missing_ops", "custom_op", "migration_tool"]
# P4：12 型号 × 7 软件面字段（不得留空；无公开口径写「未公开」并同样附 source_url）
P4_FIELDS = ["instruction_set", "programming_model", "cuda_compat", "operator_lib",
             "inference_engine", "framework_support", "migration_tool"]
CMP_FIELDS = [("category", "定位"), ("process_node", "制程"), ("architecture", "架构"),
              ("form_factor", "板型/接口"), ("launch_date", "上市时间"),
              ("memory_capacity", "显存容量"), ("memory_type", "显存类型"),
              ("memory_bandwidth", "显存带宽"), ("interconnect_bw", "片间互联"),
              ("host_interface", "主机接口"), ("fp64_tflops", "FP64"), ("fp32_tflops", "FP32"),
              ("fp16_tflops", "FP16"), ("bf16_tflops", "BF16"), ("fp8_tflops", "FP8"),
              ("int16_tops", "INT16"), ("int8_tops", "INT8"), ("tdp", "功耗"),
              ("software_stack", "软件栈"), ("instruction_set", "指令集"),
              ("programming_model", "编程模型"), ("cuda_compat", "CUDA 兼容层"),
              ("operator_lib", "算子库"), ("inference_engine", "推理后端"),
              ("framework_support", "框架支持"), ("migration_tool", "迁移工具"),
              ("certification", "安全可靠认证")]
SKIP_DIRS = {".git", "raw", "temp", "tools", "__pycache__", "node_modules"}

CSS = ("body{font:15px/1.7 -apple-system,Segoe UI,Microsoft YaHei,sans-serif;"
       "max-width:1120px;margin:0 auto;padding:20px;color:#1c1c1e}"
       "h1{font-size:22px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
       "nav{font-size:13px;color:#666;margin-bottom:12px}"
       ".bc{font-size:12.5px;color:#666;margin-bottom:12px}.bc a{color:#0a63c2}.bc .cur{color:#333}"
       "table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}"
       ".tbl{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:8px 0}"
       ".tbl table{margin:0;min-width:520px}"
       "th,td{border:1px solid #ddd;padding:5px 8px;text-align:left;vertical-align:top}"
       "th{background:#f5f5f7;position:sticky;top:0;z-index:2}"
       "th.s{cursor:pointer}"
       "code{background:#f5f5f7;padding:1px 4px;border-radius:3px;font-size:12px}"
       ".warn{color:#a33}.muted{color:#777;font-size:12.5px}"
       ".fbar{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}"
       ".fbar input,.fbar select{font-size:14px;padding:6px 8px;border:1px solid #ccc;border-radius:6px}"
       ".fbar input{flex:1;min-width:180px}"
       ".ck{display:inline-block;margin:4px 14px 4px 0;font-size:13.5px}"
       "a{color:#0a63c2;text-decoration:none}a:hover{text-decoration:underline}")


def e(x):
    return html.escape(str(x), quote=True)


def R(depth, path):
    """按页面深度生成相对链接：depth=当前页相对站根的目录层数。"""
    return ("./" if depth == 0 else "../" * depth) + path


def A(depth, path, text):
    return '<a href="%s">%s</a>' % (e(R(depth, path)), e(text))


def crumbs(depth, items):
    """items=[(label, 站根相对路径 or None), ...]；None=当前页（不可点）。"""
    parts = []
    for lab, pth in items:
        if pth is None:
            parts.append('<span class="cur">%s</span>' % e(lab))
        else:
            parts.append(A(depth, pth, lab))
    return '<div class="bc">%s</div>' % " › ".join(parts)


def page(title, body, desc, kw=None, depth=0, bc=None, path="/"):
    nav = " · ".join('<a href="%s">%s</a>' % (e(R(depth, u)), e(t)) for u, t in NAV)
    doc_title = "国产算力站点 r40" if title == "国产算力站点" else "%s · 国产算力站点 r40" % title
    kwtag = '<meta name="keywords" content="%s">\n' % e("，".join(kw)) if kw else ""
    bch = (bc + "\n") if bc else ""
    canon = SITE_URL + path
    wrapped = re.sub(r"<table(\s|>)", r'<div class="tbl" style="overflow-x:auto"><table\1', body)
    wrapped = wrapped.replace("</table>", "</table></div>")
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>%s</title>\n"
            "<meta name=\"description\" content=\"%s\">\n"
            "%s"
            "<link rel=\"canonical\" href=\"%s\">\n"
            "<style>%s</style>\n</head>\n<body>\n<nav>%s</nav>\n%s<h1>%s</h1>\n%s\n"
            "<hr><p class=\"muted\">构建: %s · 数据来源见 <a href=\"%s\">来源页</a> · "
            "构建器 tools/build.py（确定性输出）</p>\n</body>\n</html>\n" %
            (e(doc_title), e(desc), kwtag, e(canon), CSS, nav, bch, e(title), wrapped,
             BUILD_ID, e(R(depth, "sources/"))))


def field_cell(v):
    s = e(v["value"])
    if v["unit"] not in ("n/a", ""):
        s += " <span class=\"muted\">%s</span>" % e(v["unit"])
    extra = ""
    if v.get("conflict_with"):
        extra = "<div class=\"warn\">冲突: %s</div>" % "；".join(
            "%s %s (%s)" % (e(c["value"]), e(c["unit"]), e(c["source_url"])) for c in v["conflict_with"])
    return s + extra


def main():
    rep = V.run()
    srcs = V.load_sources()
    url2slug = {u: k for k, u in srcs.items()}
    ok_chips = []
    for rec in rep["chips"]:
        with open(os.path.join(SITE, rec["file"]), encoding="utf-8") as f:
            obj = json.load(f)
        obj["_ok"] = rec["ok"]
        obj["_errors"] = rec["errors"]
        ok_chips.append(obj)
    excluded = [c for c in ok_chips if not c["_ok"]]
    live = [c for c in ok_chips if c["_ok"]]
    vendors = sorted({c["vendor"] for c in live})
    if len(live) < 10 or len(vendors) < 3:
        print("BUILD ABORT: 通过校验的卡片 %d 张 / 厂商 %d 家，低于 10/3 下限" % (len(live), len(vendors)))
        return 1

    def write(rel, txt):
        p = os.path.join(SITE, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(txt)
        return p

    total_fields = sum(len(c["fields"]) for c in live)

    def cert_v(c):
        return str(c["fields"]["certification"]["value"])

    inlist = sum(1 for c in live if "已入" in cert_v(c))
    notin = sum(1 for c in live if "未含" in cert_v(c))
    n_conf = sum(1 for c in live for f in c["fields"].values() if f.get("conflict_with"))
    bw_conf = sum(1 for c in live for k, f in c["fields"].items()
                  if k == "memory_bandwidth" and f.get("conflict_with"))

    # 首页（规格要求：三段入口 ①硬件瓶颈 ②采购选型 ③落地趋势）
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" %
                   (A(0, "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"]), c["model"]),
                    e(c["vendor"]), e(c["fields"]["category"]["value"]), e(cert_v(c)[:42]))
                   for c in live)
    home = ("<p>本页为国产 AI 芯片规格库 r40 迭代的静态站点首页。一期收录 "
            "<b>%d</b> 家厂商 <b>%d</b> 款芯片共 <b>%d</b> 个字段，全部字段可回指已归档原文（raw/）。</p>"
            % (len(vendors), len(live), total_fields) +
            "<h2>① 看硬件瓶颈</h2>"
            "<p>先看显存带宽 / 显存容量 / 片间互联这三项最易卡脖子的指标。全站共 <b>%d</b> 处"
            "跨来源口径冲突已并列展示、未取平均，其中<b>显存带宽</b>类占 <b>%d</b> 处（分歧最集中）。"
            "入口：" % (n_conf, bw_conf) +
            A(0, "chips/", "芯片矩阵") + "（点表头按带宽/容量/算力排序，降序即见档位差） · " +
            A(0, "verdict/", "结论") + "（数据缺口与不可比项）。</p>"
            "<h2>② 采购选型指导</h2>"
            "<p>按「硬件规格 → 软件栈迁移成本 → 算子覆盖」三步选。本批 <b>%d</b> 款卡中，"
            "<b>%d</b> 款的厂商已有同系列型号列入安全可靠 I 级名单，<b>%d</b> 款本批次名单未含"
            "（逐卡标注见右列与卡片页）。入口：" % (len(live), inlist, notin) +
            A(0, "stacks/", "软件栈") + "（CANN / DTK / MUSA / BANG 等迁移路径） · " +
            A(0, "operators/", "算子生态") + "（覆盖与缺失）。</p>"
            "<h2>③ 判断国产芯片可落地趋势</h2>"
            "<p>判断依据是「可核验的规格 + 可复现的来源 + 已声明的缺口」。入口：" +
            A(0, "verdict/", "结论与数据缺口") + " · " +
            A(0, "sources/", "来源台账") + "（<b>%d</b> 个归档原文） · " % rep["archived_raw"] +
            A(0, "method/", "方法") + "（管道与校验规则）。</p>"
            "<h2>全部型号一览</h2>"
            "<table><tr><th>型号</th><th>厂商</th><th>定位</th><th>安全可靠认证</th></tr>%s</table>"
            "<p class=\"muted\">校验: 通过 %d / 失败 %d；归档来源 %d 个页面 %d 字节。</p>"
            % (rows, rep["passed"], rep["failed"], rep["archived_raw"], rep["archived_bytes"]))
    home_desc = ("国产 AI 芯片规格库：收录 %d 家厂商 %d 款国产 AI 芯片共 %d 个字段，"
                 "每个字段可回指已归档原文；跨来源口径冲突并列展示、未取平均。" %
                 (len(vendors), len(live), total_fields))
    write("index.html", page("国产算力站点", home, home_desc, None, 0,
                             crumbs(0, [("首页", None)]), "/"))

    # /chips/ 芯片矩阵（可排序表格 + 厂商/定位筛选 + 关键词搜索，纯前端 JS，无后端）
    hdr = ["型号", "厂商", "定位", "显存", "带宽", "FP16", "INT8", "功耗", "安全可靠"]
    kk = ["category", "memory_capacity", "memory_bandwidth", "fp16_tflops", "int8_tops", "tdp", "certification"]
    th = "".join('<th class="s" onclick="st(%d)">%s</th>' % (i, e(h)) for i, h in enumerate(hdr))
    brows = []
    for c in live:
        catv = str(c["fields"]["category"]["value"])
        tds = ('<td><a href="%s">%s</a></td><td>%s</td>'
               % (e(R(1, "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"]))), e(c["model"]), e(c["vendor"])))
        for k in kk:
            tds += "<td>%s</td>" % field_cell(c["fields"][k])
        brows.append('<tr data-v="%s" data-c="%s">%s</tr>' % (e(c["vendor"]), e(catv), tds))
    vopt = "".join('<option value="%s">%s</option>' % (e(v), e(v)) for v in vendors)
    copt = "".join('<option value="%s">%s</option>' % (e(k), e(k))
                   for k in sorted({str(c["fields"]["category"]["value"]) for c in live}))
    js = ("<script>function st(n){var t=document.getElementById('mt'),b=t.tBodies[0],"
          "r=[].slice.call(b.rows);var d=(t.getAttribute('d')==String(n))?1:-1;"
          "t.setAttribute('d',(d==1)?('x'+n):String(n));"
          "r.sort(function(a,c){var x=a.cells[n].textContent.trim(),y=c.cells[n].textContent.trim();"
          "var nx=parseFloat(x),ny=parseFloat(y);if(!isNaN(nx)&&!isNaN(ny)){return d*(nx-ny);}"
          "return d*((x<y)?-1:((x>y)?1:0));});r.forEach(function(z){b.appendChild(z);});}"
          "function flt(){var v=document.getElementById('fv').value,c=document.getElementById('fc').value,"
          "q=document.getElementById('q').value.trim().toLowerCase();"
          "var rs=document.querySelectorAll('#mt tbody tr');"
          "for(var i=0;i<rs.length;i++){var r=rs[i],t=r.textContent.toLowerCase();"
          "var ok=(!v||r.getAttribute('data-v')===v)&&(!c||r.getAttribute('data-c')===c)&&(!q||t.indexOf(q)>=0);"
          "r.style.display=ok?'':'none';}}</script>")
    chips_body = (('<p>点击表头排序；可按厂商/定位筛选或关键词搜索（纯前端 JS，无后端）。共 %d 款芯片。</p>'
                   '<div class="fbar"><input id="q" type="search" placeholder="搜索型号 / 厂商 / 定位 / 显存…" oninput="flt()">'
                   '<select id="fv" onchange="flt()"><option value="">全部厂商</option>%s</select>'
                   '<select id="fc" onchange="flt()"><option value="">全部定位</option>%s</select></div>'
                   '<table id="mt" d=""><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
                   % (len(live), vopt, copt, th, "".join(brows))) + js +
                  '<p class="muted">对比入口：' + A(1, "compare/", "型号对比") +
                  '（可选 2–4 款并排对比关键字段）。</p>')
    write("chips/index.html", page("芯片矩阵", chips_body,
          "国产 AI 芯片矩阵：%d 款芯片的显存/带宽/算力/功耗横向对比表，可按厂商/定位筛选并关键词搜索。" % len(live),
          None, 1, crumbs(1, [("首页", ""), ("芯片卡片", None)]), "/chips/"))

    # /chip/<v>-<m>/
    for c in live:
        fs = c["fields"]
        head = ("<p class=\"muted\">厂商 %s · 系列 %s · 定位 %s · 字段数 %d · 数据文件 <code>%s</code></p>"
                % (e(c["vendor"]), e(c["series"]), e(c["category"]), len(fs),
                   "data/chips/%s-%s.json" % (c["vendor_slug"], c["model_slug"])))
        body = [head]
        for key in fs:
            v = fs[key]
            src = v["source_url"]
            slug = url2slug.get(src, "?")
            body.append("<h2>%s</h2><p>%s</p><p class=\"muted\">来源: <a href=\"%s\">%s</a> "
                        "· 归档 <code>raw/%s.html</code> · %s · %s</p>"
                        % (e(FIELD_LABEL.get(key, key)), field_cell(v), e(src), e(src),
                           e(slug), e(v["source_date"]), e(v["confidence"])))
        seen = []
        for key in fs:
            s = fs[key]["source_url"]
            if s not in seen:
                seen.append(s)
        body.append("<h2>数据来源回链</h2><p class=\"muted\">本卡每一字段的 <code>source_url</code> 均指向下列"
                    "已归档原文（<code>raw/</code>）；归档为原样保存，不改写、不解析。字段值以归档原文为准；"
                    "多源不一致时在该字段 <code>note</code> 中列明各方口径。</p><ul>%s</ul>"
                    % "".join("<li><a href=\"%s\">%s</a> → <code>raw/%s.html</code></li>"
                              % (e(s), e(s), e(url2slug.get(s, "?"))) for s in seen))
        chip_desc = ("%s %s 完整规格：%d 个字段（%s），每字段附来源与归档链接。" %
                     (c["vendor"], c["model"], len(fs), c["category"]))
        write("chip/%s-%s/index.html" % (c["vendor_slug"], c["model_slug"]),
              page(c["model"], "\n".join(body), chip_desc, c.get("keywords"), 2,
                   crumbs(2, [("首页", ""), ("芯片卡片", "chips/"), (c["model"], None)]),
                   "/chip/%s-%s/" % (c["vendor_slug"], c["model_slug"])))

    # /compare/ 型号对比（勾选 2–4 款，前端 JS 并排对比关键字段，无后端）
    sorted_live = sorted(live, key=lambda x: (x["vendor_slug"], x["model_slug"]))
    cmpD = []
    for c in sorted_live:
        f = {}
        for k, _ in CMP_FIELDS:
            if k in c["fields"]:
                f[k] = str(c["fields"][k]["value"])
        cmpD.append({"id": "%s-%s" % (c["vendor_slug"], c["model_slug"]), "v": c["vendor"],
                     "m": c["model"], "u": R(1, "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"])), "f": f})
    selparts = "".join('<label class="ck"><input type="checkbox" value="%d" onchange="upd()"> %s %s</label>'
                       % (i, e(d["v"]), e(d["m"])) for i, d in enumerate(cmpD))
    jsD = json.dumps(cmpD, ensure_ascii=False).replace("</", "<\\/")
    jsF = json.dumps([[k, l] for k, l in CMP_FIELDS], ensure_ascii=False)
    cmp_js = ("<script>var D=%s;var F=%s;"
              "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}"
              "function upd(){var bx=document.querySelectorAll('#sel input'),sel=[];"
              "for(var i=0;i<bx.length;i++){if(bx[i].checked)sel.push(D[+bx[i].value]);}"
              "var hint=document.getElementById('hint'),out=document.getElementById('out');"
              "if(sel.length<2||sel.length>4){hint.textContent='请选择 2–4 个型号（当前 '+sel.length+' 个）。';"
              "out.innerHTML='';return;}hint.textContent='已选 '+sel.length+' 个型号。';"
              "var h='<'+'table><thead><tr><th>字段</th>';"
              "for(var j=0;j<sel.length;j++){h+='<th><a class=\"cl\" data-i=\"'+j+'\">'+esc(sel[j].v+' '+sel[j].m)+'</a></th>';}"
              "h+='</tr></thead><tbody>';"
              "for(var k=0;k<F.length;k++){var key=F[k][0],any=false;"
              "for(j=0;j<sel.length;j++){if(sel[j].f[key]){any=true;}}if(!any){continue;}"
              "h+='<tr><th>'+esc(F[k][1])+'</th>';"
              "for(j=0;j<sel.length;j++){h+='<td>'+esc(sel[j].f[key]||'—')+'</td>';}h+='</tr>';}"
              "h+='</tbody></'+'table>';out.innerHTML=h;"
              "var as=out.querySelectorAll('a.cl');"
              "for(var z=0;z<as.length;z++){as[z].setAttribute('href',sel[z].u);}</script>" % (jsD, jsF))
    cmp_body = ('<p>勾选 2–4 款型号，并排对比关键字段（纯前端 JS，无后端、手机可点选）。</p>'
                '<div class="fbar" id="sel">%s</div>'
                '<p class="muted" id="hint">请选择 2–4 个型号。</p><div id="out"></div>' % selparts) + cmp_js
    write("compare/index.html", page("型号对比", cmp_body,
          "国产 AI 芯片型号对比：勾选 2–4 款，并排对比显存/带宽/算力/软件栈/迁移工具等关键字段（纯前端）。",
          None, 1, crumbs(1, [("首页", ""), ("型号对比", None)]), "/compare/"))

    # /stacks/
    rows = "".join("<tr><td>%s</td>%s</tr>" % (
        A(1, "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"]), c["model"]),
        "".join("<td>%s</td>" % field_cell(c["fields"][k]) for k in SW_FIELDS)) for c in live)
    write("stacks/index.html", page("软件栈与兼容层", "<table><tr><th>型号</th>%s</tr>%s</table>" % (
        "".join("<th>%s</th>" % e(FIELD_LABEL[k]) for k in SW_FIELDS), rows),
        "国产 AI 芯片软件栈与 CUDA 兼容层对比：%d 款芯片的 CANN/DTK/MUSA/BANG 等迁移路径。" % len(live),
        None, 1, crumbs(1, [("首页", ""), ("软件栈", None)]), "/stacks/"))

    # /operators/
    rows = "".join("<tr><td>%s</td>%s</tr>" % (
        A(1, "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"]), c["model"]),
        "".join("<td>%s</td>" % field_cell(c["fields"][k]) for k in OP_FIELDS)) for c in live)
    write("operators/index.html", page("算子库与迁移", "<table><tr><th>型号</th>%s</tr>%s</table>" % (
        "".join("<th>%s</th>" % e(FIELD_LABEL[k]) for k in OP_FIELDS), rows),
        "国产 AI 芯片算子库与迁移对比：%d 款芯片的算子覆盖、缺失算子与迁移工具。" % len(live),
        None, 1, crumbs(1, [("首页", ""), ("算子生态", None)]), "/operators/"))

    # /verdict/
    vb = ["<p>以下结论仅由入库字段机械汇总（不含估算与商业判断）：</p><table>"
          "<tr><th>型号</th><th>定位</th><th>FP16</th><th>显存</th><th>带宽</th><th>软件栈</th><th>安全可靠认证</th></tr>"]
    for c in live:
        f = c["fields"]
        vb.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            e(c["model"]), e(f["category"]["value"]), e(f["fp16_tflops"]["value"]),
            e(f["memory_capacity"]["value"]), e(f["memory_bandwidth"]["value"]),
            e(f["software_stack"]["value"]), e(f["certification"]["value"])))
    gaps = [(c["model"], k) for c in live for k in c["fields"] if c["fields"][k]["confidence"] == "unverified"]
    vb.append("</table><h2>数据缺口（confidence=unverified，公开口径未给出）</h2><ul>%s</ul>" %
              "".join("<li>%s · %s</li>" % (e(m), e(FIELD_LABEL.get(k, k))) for m, k in gaps))
    if excluded:
        vb.append("<h2 class=\"warn\">未入库卡片（校验失败）</h2><ul>%s</ul>" %
                  "".join("<li>%s: %s</li>" % (e(c["model"]), e("；".join(c["_errors"]))) for c in excluded))
    write("verdict/index.html", page("结论与数据缺口", "\n".join(vb),
          "结论与数据缺口：%d 款芯片的机械汇总，以及 %d 个公开口径未给出(unverified)的字段。" %
          (len(live), len(gaps)), None, 1, crumbs(1, [("首页", ""), ("结论", None)]), "/verdict/"))

    # /sources/
    rows = []
    for slug in sorted(srcs):
        p = os.path.join(V.RAW, slug + ".html")
        if os.path.exists(p):
            b = os.path.getsize(p)
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
            rows.append("<tr><td>%s</td><td><a href=\"%s\">%s</a></td><td><code>raw/%s.html</code></td>"
                        "<td>%d</td><td><code>%s</code></td></tr>" % (e(slug), e(srcs[slug]), e(srcs[slug]), e(slug), b, h))
        else:
            rows.append("<tr><td class=\"warn\">%s</td><td><a href=\"%s\">%s</a></td><td class=\"warn\">未归档</td>"
                        "<td>-</td><td>-</td></tr>" % (e(slug), e(srcs[slug]), e(srcs[slug])))
    write("sources/index.html", page("来源清单",
          "<p class=\"muted\">下列为字段来源 URL 与归档指纹（sha256[:16]）；归档原文 "
          "<code>raw/</code> 仅存于工作副本、不随站点发布（版权与商业敏感）。</p>"
          "<table><tr><th>slug</th><th>URL</th><th>归档</th>"
          "<th>字节</th><th>sha256[:16]</th></tr>%s</table>" % "".join(rows),
          "来源台账：%d 条来源 URL 及其归档指纹，字段级可追溯。" % len(srcs),
          None, 1, crumbs(1, [("首页", ""), ("来源", None)]), "/sources/"))

    # /method/
    pow_rows = []
    for c in live:
        miss = [k for k in P4_FIELDS if str(c["fields"].get(k, {}).get("value")) == "未公开"]
        pow_rows.append("<tr><td>%s</td><td>%d/%d</td><td>%.1f%%</td><td>%s</td></tr>" % (
            e(c["model"]), len(miss), len(P4_FIELDS), 100.0 * len(miss) / len(P4_FIELDS),
            e("、".join(FIELD_LABEL.get(k, k) for k in miss) or "—")))
    mb = ["<h2>数据管道</h2><ol>"
          "<li>归档原文到 <code>raw/</code>（URL 只归档，不改写、不解析）；"
          "<code>tools/collect/sources.json</code> 登记 slug→URL。</li>"
          "<li>抽取：<code>tools/collect/extract.py</code> 对 raw/*.html 去标签 + 关键词过滤，落 <code>temp/digest.txt</code> 供人工核对（不做数值改写）。</li>"
          "<li>回填：人工核对后写入 <code>data/chips/*.json</code>；每字段 source_url 指回 raw/ 已归档来源。</li>"
          "<li>校验：<code>tools/validate.py</code>（详见下）。</li>"
          "<li>渲染：<code>tools/build.py</code> 仅渲染通过校验的卡片。</li></ol>",
          "<h2>校验规则</h2><p>R1 结构(≥25 字段且六键齐全)；R2 非空；R3 日期格式；"
          "R4 置信枚举；R5 来源可追溯(source_url 命中 sources.json 且 raw/&lt;slug&gt;.* 归档存在)；"
          "R8 来源分级(source_tier ∈ T1/T2/T3)；R9 铁律(verified 必须有 T1 官方来源)；R10 时效(字段级 last_verified)；"
          "R6 数字字段必须带单位；R7 冲突登记完整且 conflict_with 可追溯。</p>"
          "<p class=\"warn\">边界：校验器保证“已登记项的完整与可追溯”，不保证“冲突发现的覆盖度”——"
          "后者依赖人工检索登记，属已知局限。</p>",
          "<h2>口径说明</h2><p>source_date 对动态产品页/规格站取「归档取得日」(2026-10-09)；"
          "对安全可靠认证公告取「公告发布日」(2026-05-26)。confidence: verified=≥2 个已归档来源一致；"
          "single-source=单一已归档来源；unverified=公开口径未给出（值为“未公开”）。</p>",
          "<h2>软件面字段「未公开」统计（P4）</h2>"
          "<p>下表为每个型号 7 个软件面字段（指令集 / 编程模型 / CUDA 兼容层 / 算子库 / 推理后端 / "
          "框架支持 / 迁移工具）中取值为「未公开」的计数与占比；「未公开」表示公开口径未给出，"
          "已登记的尝试来源见各卡片对应字段的 <code>source_url</code>（同样附来源与日期，未凭推测填数）。</p>"
          "<table><tr><th>型号</th><th>未公开字段数</th><th>占比</th><th>未公开字段</th></tr>%s</table>"
          % "".join(pow_rows),
          "<h2>本次校验结果</h2><p>通过 %d / 失败 %d；归档来源 %d 页 %d 字节；"
          "sources.json 登记 %d 条。</p>" % (rep["passed"], rep["failed"], rep["archived_raw"],
                                             rep["archived_bytes"], rep["sources_registered"]),
          "<h2>GEO 引用层（r41）</h2><ol>"
          "<li>robots.txt：对 %d 个 AI/检索直取器（GPTBot / ChatGPT-User / ClaudeBot / PerplexityBot 等）"
          "逐条显式 Allow；对 %d 个 SEO/反链采集器（AhrefsBot / SemrushBot 等）Disallow；并附 Sitemap 指令。</li>"
          "<li>sitemap.xml：由构建器按实际页面树生成，&lt;loc&gt; 条数 = 页面数（见页脚构建号与本页 [6] 核对）。</li>"
          "<li>dataset/chips.json：开放数据集导出（单一事实源 = data/chips/*.json），许可 %s；"
          "引用格式见 " % (len(AI_BOTS), len(SEO_BOTS), LICENSE) +
          A(1, "dataset/", "数据集页") + "。</li>"
          "<li>字段级 SEO：每页 &lt;title&gt;/&lt;meta description&gt; 由数据生成；型号页另含数据推导的 "
          "&lt;meta keywords&gt;（源自 data/chips/*.json 的 keywords 字段）。</li></ol>"
          "<p class=\"muted\">量口径唯一来源：型号数、厂商数、字段数均取自 data/chips/*.json，"
          "页面内数字一律由构建器注入，不手写。</p>",
          "<h2>更新节奏与引用版本</h2><p>本数据集为人工核验的静态快照、非实时；随迭代批次发布，"
          "批次号见页脚构建号（当前 <code>%s</code>）。来源归档 <code>raw/</code> 仅存于工作副本、"
          "不随站点发布（版权与商业敏感）；线上可回指的是字段级 source_url 与来源台账 sha256。</p>" % BUILD_ID]
    write("method/index.html", page("方法与纪律", "\n".join(mb),
          "方法与纪律：数据管道、校验规则、口径说明、软件面字段「未公开」统计，以及 r41 GEO 引用层。",
          None, 1, crumbs(1, [("首页", ""), ("方法", None)]), "/method/"))

    # data/index.json（阶段 2 预留：前端筛选/排序/对比与 URL 状态分享的数据结构）
    idx = {"schema_version": "0.1", "status": "reserved-for-phase-2",
           "note": "阶段 1 不渲染交互；此文件为阶段 2 前端筛选/对比/分享链接预留的数据结构。",
           "count": len(live), "vendors": sorted(vendors),
           "chips": [{"id": "%s-%s" % (c["vendor_slug"], c["model_slug"]), "vendor": c["vendor"],
                      "model": c["model"], "url": "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"]),
                      "category": c["fields"]["category"]["value"],
                      "software_stack": c["fields"]["software_stack"]["value"],
                      "certification": c["fields"]["certification"]["value"]}
                     for c in sorted(live, key=lambda x: (x["vendor_slug"], x["model_slug"]))]}
    with open(os.path.join(SITE, "data", "index.json"), "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    # /dataset/ 开放数据集页（r41 GEO 引用入口；引用格式 + 许可）
    ds_rows = "".join("<li>%s · %s</li>" %
                      (A(1, "chip/%s-%s/" % (c["vendor_slug"], c["model_slug"]),
                         "%s %s" % (c["vendor"], c["model"])), e(c["category"]))
                      for c in sorted(live, key=lambda x: (x["vendor_slug"], x["model_slug"])))
    cite_txt = "XieXiushen. 国产 AI 芯片规格库 [DB/OL]. %s. %s/dataset/chips.json" % (YEAR, BASE)
    bib = ("@misc{mapmatch_chips_%s,\n  title  = {{国产 AI 芯片规格库}},\n  author = {XieXiushen},\n"
           "  year   = {%s},\n  note   = {%s},\n  url    = {%s/dataset/chips.json}\n}" %
           (YEAR, YEAR, LICENSE, BASE))
    ds = ("<p>开放数据集：本站在单一事实源 <code>data/chips/*.json</code> 之上导出机器可读数据集 "
          "<a href=\"%s\"><code>/dataset/chips.json</code></a>，"
          "收录 <b>%d</b> 家厂商 <b>%d</b> 款芯片共 <b>%d</b> 个字段。</p>"
          "<h2>许可</h2><p>%s（<a href=\"%s\">%s</a>）。引用请保留出处与许可。</p>"
          "<h2>如何引用</h2><p class=\"muted\">引用格式（文本式 + BibTeX）：</p>"
          "<pre><code>%s</code></pre><pre><code>%s</code></pre>"
          "<h2>收录型号</h2><ul>%s</ul>" %
          (e(R(1, "dataset/chips.json")), len(vendors), len(live), total_fields,
           LICENSE, LICENSE_URL, LICENSE_URL, e(cite_txt), e(bib), ds_rows))
    write("dataset/index.html", page("开放数据集", ds,
          "开放数据集（%s）：%d 家厂商 %d 款国产 AI 芯片规格 JSON，附引用格式与许可。" %
          (LICENSE, len(vendors), len(live)), None, 1, crumbs(1, [("首页", ""), ("数据集", None)]), "/dataset/"))

    pages = []
    for root, dirs, files in os.walk(SITE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f == "index.html":
                rel = os.path.relpath(os.path.join(root, f), SITE).replace("\\", "/")
                pages.append("/" + os.path.dirname(rel).replace("\\", "/") + ("/" if os.path.dirname(rel) else ""))
    pages = sorted(set(pages))

    # r41 GEO 引用层：robots.txt（AI/检索直取器白名单 + 反链采集器拒绝）
    rb = ["# robots.txt — 国产算力站点 r40（r41 GEO 引用层）",
          "# Allow LLM crawling for citations（AI/检索直取器显式放行；注释口径见 R41 卡）",
          "User-agent: *", "Allow: /", ""]
    for b in AI_BOTS:
        rb += ["User-agent: %s" % b, "Allow: /"]
    rb += ["", "# Disallow SEO/backlink crawlers（反链与 SEO 采集器拒绝）"]
    for b in SEO_BOTS:
        rb += ["User-agent: %s" % b, "Disallow: /"]
    rb += ["", "Sitemap: %s/sitemap.xml" % BASE, ""]
    write("robots.txt", "\n".join(rb))

    # --- R44 补丁（P6-P10 / D1-D5）：新增 /guide/、/changelog/ 并做全站后处理 ---
    # 确定性：后处理只做静态注入（CSS/横幅/徽标/交互），无时间戳、无网络、无外部依赖。
    import r44 as _r44
    pages = sorted(set(pages) | set(_r44.apply(SITE, write, page, crumbs, e, R)))

    # sitemap.xml（<loc> 条数 = 实际页面树；对外绝对 URL 用全量前缀 SITE_URL）
    sm = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
          "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"]
    for p in pages:
        sm.append("  <url><loc>%s%s</loc></url>" % (BASE, p))
    sm += ["</urlset>", ""]
    write("sitemap.xml", "\n".join(sm))

    # dataset/chips.json（开放数据集导出；单一事实源 = data/chips/*.json）
    export = []
    for fn in sorted(os.listdir(os.path.join(SITE, "data", "chips"))):
        if fn.endswith(".json"):
            with open(os.path.join(SITE, "data", "chips", fn), encoding="utf-8") as fh:
                export.append(json.load(fh))
    dsj = {"schema_version": "0.2", "license": LICENSE, "license_url": LICENSE_URL,
           "citation": cite_txt, "source": BASE + "/", "built": BUILD_ID,
           "count": len(export), "chips": export}
    write("dataset/chips.json", json.dumps(dsj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    print("BUILD OK pages=%d chips=%d vendors=%d fields=%d excluded=%d archived=%d "
          "sitemap=%d ai_bots=%d seo_bots=%d dataset=%d" %
          (len(pages), len(live), len(vendors), total_fields, len(excluded), rep["archived_raw"],
           len(pages), len(AI_BOTS), len(SEO_BOTS), len(export)))
    for p in pages:
        print("  PAGE %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
