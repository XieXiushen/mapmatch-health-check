#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r40 来源采集器：先归档原文，再抽取。
用法: python tools/collect/collect.py
- 读 tools/collect/sources.json
- 每个 URL 抓取原文 -> raw/<slug>.html（不改写、不解析）
- 写 raw/manifest.json：slug/url/status/bytes/sha256/fetched_at
- 幂等：--cached 时若 raw/<slug>.html 已存在则跳过抓取（默认重抓）
"""
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(os.path.dirname(HERE))  # site/
RAW = os.path.join(SITE, "raw")
MANIFEST = os.path.join(RAW, "manifest.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.status, r.read()


def main():
    cached = "--cached" in sys.argv
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(HERE, "sources.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    srcs = cfg["sources"]
    manifest = {}
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as f:
                manifest = json.load(f).get("entries", {})
        except Exception:
            manifest = {}
    for slug, meta in srcs.items():
        path = os.path.join(RAW, slug + ".html")
        if cached and os.path.exists(path):
            b = open(path, "rb").read()
            manifest[slug] = dict(meta, status=manifest.get(slug, {}).get("status", "cached"),
                                  bytes=len(b), sha256=hashlib.sha256(b).hexdigest(),
                                  fetched_at=manifest.get(slug, {}).get("fetched_at"))
            print("CACHED %-24s %8d" % (slug, len(b)))
            continue
        status = None
        try:
            status, body = fetch(meta["url"])
        except urllib.error.HTTPError as e:
            status, body = e.code, b""
        except Exception as e:  # noqa
            status, body = "ERR:" + type(e).__name__, b""
        if isinstance(status, int) and 200 <= status < 300 and body:
            with open(path, "wb") as f:
                f.write(body)
            manifest[slug] = dict(meta, status=status, bytes=len(body),
                                  sha256=hashlib.sha256(body).hexdigest(),
                                  fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            print("OK     %-24s %8d  %s" % (slug, len(body), meta["url"]))
        else:
            manifest[slug] = dict(meta, status=status, bytes=len(body),
                                  sha256=None, fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            print("FAIL   %-24s status=%s  %s" % (slug, status, meta["url"]))
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"_note": "raw 归档清单。sha256 为归档原文的哈希。",
                   "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "entries": manifest}, f, ensure_ascii=False, indent=2)
    ok = sum(1 for v in manifest.values() if isinstance(v.get("status"), int) and 200 <= v["status"] < 300)
    print("-- %d/%d ok --" % (ok, len(srcs)))


if __name__ == "__main__":
    main()
