# -*- coding: utf-8 -*-
"""r41 字段级 SEO：为每个型号 JSON 写入 keywords（面向检索/LLM 抽取）。

纪律:
 - keywords 只由该卡自身的字段值推导，不引入外部信息、不臆造事实。
 - 幂等: 重复运行结果一致（sort_keys + indent=2 + 换行 \n）。
用法: python tools/collect/make_keywords.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.abspath(os.path.join(HERE, "..", ".."))
CHIPS = os.path.join(SITE, "data", "chips")

GENERIC = ["国产AI芯片", "AI加速卡", "芯片规格", "算力规格库"]
FIELD_KWS = ["category", "process_node", "architecture", "form_factor",
             "memory_type", "software_stack", "programming_model",
             "inference_engine", "framework_support", "operator_lib"]
SKIP = {"", "未公开", "n/a", "N/A", "无"}


def kws_for(obj):
    f = obj.get("fields") or {}
    out = []

    def add(s):
        s = str(s).strip()
        if s and len(s) <= 24 and s not in SKIP and s not in out:
            out.append(s)

    add(obj.get("model"))
    add(obj.get("vendor"))
    add(obj.get("series"))
    add(obj.get("model_slug"))
    add(obj.get("vendor_slug"))
    for k in FIELD_KWS:
        add((f.get(k) or {}).get("value", ""))
    for g in GENERIC:
        add(g)
    return out[:18]


def main():
    n = 0
    for fn in sorted(os.listdir(CHIPS)):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(CHIPS, fn)
        with open(p, encoding="utf-8") as fh:
            obj = json.load(fh)
        k = kws_for(obj)
        obj["keywords"] = k
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print("%-34s keywords=%d  %s" % (fn, len(k), ", ".join(k)))
        n += 1
    print("done files=%d" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
