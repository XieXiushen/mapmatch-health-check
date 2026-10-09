#!/usr/bin/env bash
# r40 站点阶段 1 —— 一键验收（在任意目录: bash tools/verify.sh）
# 覆盖卡片「验收」5 条：无来源不入库 / 口径冲突并列 / 页面数与 HTTP 200 /
#                       构建幂等 + 校验通过率 100% / 无后端调用
set -u
cd "$(dirname "$0")/.."   # 切到 site/
PY=python
TMP=temp
mkdir -p "$TMP"

echo "== [1/4] validate（无来源不入库硬规则） =="
$PY tools/validate.py | tail -3
echo "exit=$?"

echo "== [2/4] build 幂等（连跑两次 + sha256 比对） =="
$PY tools/build.py | grep '^BUILD OK' ; echo "run1_exit=$?"
$PY tools/build.py | grep '^BUILD OK' ; echo "run2_exit=$?"
$PY tools/idem_check.py | tail -2

echo "== [3/4] 静态回读（本地 http.server，逐页 HTTP 状态） =="
$PY tools/check_http.py | tail -2

echo "== [4/4] 验收核对（对照规格 §五 五条 + r41 GEO 引用层） =="
$PY tools/acceptance_check.py | grep -E '^(\[[0-9]\]|    -> )'

echo "== done =="
