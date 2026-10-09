# -*- coding: utf-8 -*-
"""P2 静态链接检查（无网络）：解析构建产物每个 HTML 的 href/src，跳过 http(s):/mailto:/#，
断言解析后的目标文件存在于构建产物。任一失败 → 非零退出。

校验范围 = 构建产物（全部 .html，排除 raw/ temp/ tools/ .git/）。
根绝对链接（href="/..." / src="/..."）视为缺陷（P1 违规）直接判失败。
"""
import os, posixpath, re, sys

SITE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = {".git", "raw", "temp", "tools", "__pycache__", "data"}
ATTR = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"', re.I)
SKIP_PREFIX = ("http://", "https://", "mailto:", "javascript:", "data:", "tel:", "#")


def pages():
    out = []
    for root, dirs, files in os.walk(SITE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.lower().endswith(".html"):
                out.append(os.path.join(root, f))
    return sorted(out)


def resolve(page_rel, ref):
    """返回 (相对目标路径, 候选文件列表)；target 以 posix 相对 SITE 表示。"""
    p = ref.split("#")[0].split("?")[0]
    if not p:
        return None, []
    d = posixpath.dirname(page_rel)
    full = posixpath.normpath(posixpath.join(d, p))
    if p.endswith("/"):
        return full, [posixpath.join(full, "index.html")]
    return full, [full, posixpath.join(full, "index.html")]


def main():
    files = pages()
    errors, abs_refs, n_refs, n_ok = [], [], 0, 0
    for path in files:
        rel = os.path.relpath(path, SITE).replace("\\", "/")
        html = open(path, encoding="utf-8", errors="replace").read()
        for m in ATTR.finditer(html):
            ref = m.group(1).strip()
            if not ref or ref.lower().startswith(SKIP_PREFIX):
                continue
            n_refs += 1
            if ref.startswith("/"):
                abs_refs.append("%s -> %s" % (rel, ref))
                errors.append("%s -> 根绝对链接 %s" % (rel, ref))
                continue
            target, cands = resolve(rel, ref)
            hit = None
            for c in cands:
                if os.path.exists(os.path.join(SITE, c.replace("/", os.sep))):
                    hit = c
                    break
            if hit is None:
                errors.append("%s -> %s（目标不存在，期望 %s）" % (rel, ref, " / ".join(cands)))
            else:
                n_ok += 1

    print("HTML files scanned : %d" % len(files))
    print("internal refs      : %d" % n_refs)
    print("resolved OK        : %d" % n_ok)
    print("root-absolute refs : %d" % len(abs_refs))
    print("broken refs        : %d" % (len(errors) - len(abs_refs)))
    for e in errors:
        print("FAIL " + e)
    print("CHECK_LINKS_OK=%s" % ("PASS" if not errors else "FAIL"))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
