# -*- coding: utf-8 -*-
"""P2 HTTP 回测：从 BASE 起 BFS 站内全部链接。
默认本地：线程内起 http.server 回读构建产物；也可传入远端 BASE（GitHub Pages）。
断言：
  * 每个站内链接返回 200；
  * HTML 页面响应体 >= 2048 字节且含非空 <h1>；
  * sitemap.xml 的 <loc> 数 == 实际页面数（首页 + 各栏目页 + 型号页）。
逐条输出：URL + HTTP 码 + 字节数。任一失败 → 非零退出。

用法:
  python tools/check_http.py                          # 本地构建产物
  python tools/check_http.py https://host/pre/        # 远端 BASE
"""
import functools, http.server, json, os, re, socketserver, sys, threading, urllib.request
from urllib.parse import urljoin, urldefrag

SITE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PORT = 8771
MIN_BYTES = 2048
ATTR = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"', re.I)
H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
UA = "r40-check/1.0"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read()


def crawl(base):
    order, res = [], {}
    queue = [base]
    while queue:
        u = queue.pop(0)
        if u in res:
            continue
        try:
            st, body = fetch(u)
            res[u] = (st, body, "")
        except Exception as ex:
            res[u] = (0, b"", str(ex)[:80])
            order.append(u)
            continue
        order.append(u)
        if st == 200 and u.endswith(("/", ".html")):
            for m in ATTR.finditer(body.decode("utf-8", "replace")):
                ref = m.group(1).strip()
                if not ref or ref.startswith("#"):
                    continue
                t = urldefrag(urljoin(u, ref))[0]
                if t.startswith(base) and t not in res:
                    queue.append(t)
    return order, res


def is_page(u):
    return u.endswith(("/", ".html"))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    httpd = None
    if arg:
        base = arg if arg.endswith("/") else arg + "/"
        mode = "remote"
    else:
        base = "http://127.0.0.1:%d/" % PORT
        mode = "local"
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITE)
        httpd = type("Q", (socketserver.ThreadingTCPServer,), {"allow_reuse_address": True})(
            ("127.0.0.1", PORT), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

    order, res = crawl(base)
    pages = [u for u in order if is_page(u) and res[u][0] == 200]

    fails = []
    print("BASE=%s mode=%s" % (base, mode))
    for u in order:
        st, body, err = res[u]
        print("%-72s %s %8d" % (u, st, len(body)))
        if st != 200:
            fails.append("%s 状态=%s %s" % (u, st, err))

    for u in pages:
        st, body, err = res[u]
        if len(body) < MIN_BYTES:
            fails.append("%s 字节数=%d < %d" % (u, len(body), MIN_BYTES))
        m = H1.search(body.decode("utf-8", "replace"))
        if not m or not TAG.sub("", m.group(1)).strip():
            fails.append("%s 缺少非空 <h1>" % u)

    locs = []
    try:
        st, body = fetch(urljoin(base, "sitemap.xml"))
        locs = LOC.findall(body.decode("utf-8", "replace"))
        if st != 200:
            fails.append("sitemap.xml 状态=%s" % st)
    except Exception as ex:
        fails.append("sitemap.xml 获取失败: %s" % ex)
    if len(locs) != len(pages):
        fails.append("sitemap <loc> 数=%d != 实际页面数=%d" % (len(locs), len(pages)))

    print("pages(HTML)=%d resources(other)=%d sitemap_locs=%d" % (
        len([u for u in order if is_page(u)]), len([u for u in order if not is_page(u)]), len(locs)))
    print("HTTP_OK=%d/%d" % (sum(1 for u in order if res[u][0] == 200), len(order)))
    for f in fails:
        print("FAIL " + f)
    print("CHECK_HTTP_OK=%s" % ("PASS" if not fails else "FAIL"))

    if httpd is not None:
        httpd.shutdown()
    payload = json.dumps(
        {"base": base, "mode": mode, "pages": len(pages), "locs": len(locs),
         "ok": sum(1 for u in order if res[u][0] == 200), "total": len(order),
         "rows": [{"url": u, "status": res[u][0], "bytes": len(res[u][1])} for u in order]},
        ensure_ascii=False, indent=1)
    os.makedirs(os.path.join(SITE, "temp"), exist_ok=True)
    open(os.path.join(SITE, "temp", "http_check_%s.json" % mode), "w", encoding="utf-8").write(payload)
    if mode == "local":
        open(os.path.join(SITE, "temp", "http_check.txt"), "w", encoding="utf-8").write(payload)
    print("wrote temp/http_check_%s.json" % mode)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
