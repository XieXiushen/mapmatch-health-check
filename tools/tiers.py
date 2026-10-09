# -*- coding: utf-8 -*-
"""来源分级（D2）与静态时效常量（D4）。

D2 口径：
  T1 = 厂商官网 / 官方白皮书 / 官方文档 / 官方公告
  T2 = 工信安全认证、招投标公告、证券披露、vLLM/SGLang 官方文档
  T3 = mirrorfrog、flopper 等聚合二手
硬规则：T1 缺失的字段不得标 verified；每字段必带 source_tier。

D4 口径：数据截止 / last_verified 一律取本文件内的静态日期常量，
不使用构建时刻的时间戳（以保持 tools/build.py 的确定性输出）。
"""

# 静态时效常量（禁时间戳）
DATA_CUTOFF = "2026-10-09"
LAST_VERIFIED = "2026-10-09"

T1, T2, T3 = "T1", "T2", "T3"
TIERS = (T1, T2, T3)
UNDISCLOSED = "未公开"

TIER_LABEL = {
    T1: "T1 厂商官方",
    T2: "T2 权威第三方",
    T3: "T3 聚合二手",
    UNDISCLOSED: "未公开",
}
TIER_DESC = {
    T1: "厂商官网 / 官方白皮书 / 官方文档 / 官方公告",
    T2: "工信安全认证 / 招投标公告 / 证券披露 / vLLM·SGLang 官方文档",
    T3: "mirrorfrog、flopper 等聚合二手来源",
}

# 域名 → tier（按子串匹配，顺序即优先级；未命中的域名按 T3 处理并会在审计中列出）
DOMAIN_RULES = [
    ("cambricon.com", T1),
    ("huawei.com", T1),
    ("hiascend.com", T1),
    ("mthreads.com", T1),
    ("iluvatar.com", T1),
    ("kunlunxin.com", T1),
    ("birentech.com", T1),
    ("enflame.com", T1),
    ("metax-tech.com", T1),
    ("hygon.cn", T1),
    ("itsec.gov.cn", T2),
    ("vllm.ai", T2),
    ("sglang.io", T2),
    ("d.run", T2),
    ("mirrorfrog", T3),
    ("flopper", T3),
]

UNKNOWN_HOSTS = set()


def tier_of(url):
    """按域名判定来源分级；未命中规则 → T3（并登记到 UNKNOWN_HOSTS 供审计）。"""
    u = (url or "").strip().lower()
    for pat, t in DOMAIN_RULES:
        if pat in u:
            return t
    host = u.split("//", 1)[-1].split("/", 1)[0]
    if u:
        UNKNOWN_HOSTS.add(host)
    return T3


def is_t1(url):
    return tier_of(url) == T1
