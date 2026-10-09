#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r40 抽取器：把 raw/*.html 去标签为纯文本，按关键词过滤出规格行，落 temp/digest.txt。
纪律：只做「去标签 + 关键词过滤」，不做任何数值改写；digest 供人工核对后回填 data/chips。
用法: python tools/collect/extract.py
"""
import os, re, html, glob

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> site/
RAW = os.path.join(BASE, "raw")
OUT = os.path.join(BASE, "temp", "digest.txt")

KW = ["FP16","BF16","FP32","FP64","INT8","INT4","FP8","TFLOPS","TOPS","显存","带宽",
      "GB/s","TB/s","HBM","TDP","功耗","制程","nm","架构","PCIE","PCIe","OAM","算子",
      "认证","I级","vLLM","SGLang","CANN","DTK","MUSA","BANG","CNNL","互联","HCCS",
      "安全可靠","算力","处理器","显卡","加速卡","容量","内存","工艺","指令集","软件栈"]

def to_text(b):
    for enc in ("utf-8","gbk","latin-1"):
        try:
            s = b.decode(enc)
            break
        except Exception:
            continue
    s = re.sub(r"(?is)<script.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    files = sorted(glob.glob(os.path.join(RAW, "*.html")))
    with open(OUT, "w", encoding="utf-8", newline="\n") as w:
        for f in files:
            name = os.path.basename(f)
            try:
                b = open(f, "rb").read()
            except Exception as e:
                w.write(f"===== {name} [READ-ERR {e}]\n"); continue
            t = to_text(b)
            lines = [ln.strip() for ln in t.splitlines()]
            hits = [ln for ln in lines if ln and any(k in ln for k in KW)]
            # 去重保序
            seen=set(); uniq=[]
            for ln in hits:
                k=ln[:120]
                if k in seen: continue
                seen.add(k); uniq.append(ln)
            cap = 40 if "cert" in name else 22
            uniq = uniq[:cap]
            w.write(f"\n===== {name}  (matches={len(hits)}, shown={len(uniq)})\n")
            for ln in uniq:
                w.write("  - " + ln[:300] + "\n")
    print("digest ->", OUT, os.path.getsize(OUT), "bytes")

if __name__ == "__main__":
    main()
