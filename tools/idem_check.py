# -*- coding: utf-8 -*-
"""r40 幂等性检查：连续构建两次，比对产物 sha256 集合是否一致。"""
import hashlib, os, subprocess, sys, json

SITE = r"D:\Dev\爱马仕\work\r40\site"
PY = sys.executable


def tree():
    out = {}
    for root, dirs, files in os.walk(SITE):
        if os.sep + "raw" in root or root.endswith(os.sep + "raw"):
            continue
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), SITE).replace("\\", "/")
            # r41：构建产物全集 = 全部 .html + data/index.json + dataset/* + robots.txt + sitemap.xml
            if (f.endswith(".html") or rel == "data/index.json" or rel.startswith("dataset/")
                    or f in ("robots.txt", "sitemap.xml")):
                p = os.path.join(root, f)
                out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def build():
    r = subprocess.run([PY, os.path.join(SITE, "tools", "build.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=SITE)
    return r.returncode, (r.stdout or "").splitlines()[:1]


rc1, l1 = build(); a = tree()
rc2, l2 = build(); b = tree()
same = a == b
print("build1 rc=%d %s" % (rc1, l1))
print("build2 rc=%d %s" % (rc2, l2))
print("files=%d identical=%s" % (len(a), same))
if a != b:
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            print("DIFF %s\n  %s\n  %s" % (k, a.get(k), b.get(k)))
open(os.path.join(SITE, "temp", "idem_check.txt"), "w", encoding="utf-8").write(
    json.dumps({"files": len(a), "identical": same, "hashes": a}, ensure_ascii=False, indent=1))
print("wrote temp/idem_check.txt")
