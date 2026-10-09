# -*- coding: utf-8 -*-
"""r40 静态回读：本地起 http.server 于线程内，逐一 GET 全部页面，记录 HTTP 状态码。"""
import functools, http.server, json, os, threading, urllib.request, socketserver

SITE = r"D:\Dev\爱马仕\work\r40\site"
PORT = 8771
URLS = ["/", "/chips/", "/stacks/", "/operators/", "/verdict/", "/sources/", "/method/",
        "/dataset/", "/robots.txt", "/sitemap.xml", "/dataset/chips.json"]
for d in sorted(os.listdir(os.path.join(SITE, "chip"))):
    URLS.append("/chip/%s/" % d)

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITE)
class Q(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
httpd = Q(("127.0.0.1", PORT), Handler)
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()

rows = []
for u in URLS:
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, u), timeout=10) as r:
            body = r.read()
            rows.append((u, r.status, len(body), body[:15].decode("utf-8", "replace")))
    except Exception as ex:
        rows.append((u, "ERR", 0, str(ex)[:60]))
httpd.shutdown()

ok = sum(1 for r in rows if r[1] == 200)
for r in rows:
    print("%-34s %s %6d %s" % (r[0], r[1], r[2], r[3]))
print("HTTP_OK=%d/%d port=%d" % (ok, len(URLS), PORT))
open(os.path.join(SITE, "temp", "http_check.txt"), "w", encoding="utf-8").write(
    json.dumps({"port": PORT, "ok": ok, "total": len(URLS),
                "rows": [{"url": a, "status": b, "bytes": c} for a, b, c, d in rows]}, ensure_ascii=False, indent=1))
print("wrote temp/http_check.txt")
