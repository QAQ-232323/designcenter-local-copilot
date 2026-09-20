#!/usr/bin/env bash
# ============================================================================
# fetch-frontend.sh —— 在本机重建 Copilot 页面的"西门子部分"
#
# 本仓库不包含任何西门子文件(版权归 Siemens)。它们由本脚本在你自己的机器上
# 从两处取得:
#   A) 本机 Designcenter / NX 安装目录里的页面脚本  UGII/copilot/plchat/*.js
#   B) 西门子 CDN 上的前端 bundle  plchat_v2(离线缓存用)
#
# 已经装好 Designcenter 的机器, 跑一次本脚本即可让宿主页面在浏览器里独立打开。
#
# 用法:
#   bash fetch-frontend.sh                 # 自动探测安装目录
#   NX_INSTALL="/d/Program Files/Siemens/DC 2606" bash fetch-frontend.sh
#   bash fetch-frontend.sh --skip-cdn      # 只从安装目录取脚本, 不联网
#
# 注意: 本脚本会覆盖 plchat-local/ 下那 8 个同名 .js, 这是预期行为
#       (它们是西门子原件 + 1 处必要的本地化补丁, 见下方 patch_sri)。
# ============================================================================
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"

SKIP_CDN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --skip-cdn) SKIP_CDN=1 ;;
    --force)    FORCE=1 ;;      # 强制重新下载(默认已存在的文件不动)
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

# ---------- 1. 定位安装目录 -------------------------------------------------
# Windows 路径(drive:\a\b)在 bash 里 dirname 不认反斜杠, 先转成 POSIX 路径
to_posix() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$1" 2>/dev/null || printf '%s' "$1"
  else
    printf '%s' "$1" | tr '\\\\' '/'
  fi
}
# 一个候选目录是不是"装了 Designcenter/NX 且带 Copilot 页面"
is_install() {
  [ -n "$1" ] && [ -d "$1/UGII/copilot/plchat" ]
}
# 从目录名里取 4 位版本号("DC 2606" -> 2606),取不到给 0
release_of() {
  local tok
  tok="$(basename "$1" | grep -oE '(^|[^0-9])[0-9]{4}([^0-9]|$)' | head -1 | grep -oE '[0-9]{4}')"
  printf '%s' "${tok:-0}"
}
find_install() {
  local u
  # 1) 显式指定优先
  if [ -n "${NX_INSTALL:-}" ]; then
    u="$(to_posix "$NX_INSTALL")"
    if is_install "$u"; then printf '%s\n' "$u"; return; fi
    echo "!! NX_INSTALL 里没有 UGII/copilot/plchat: $u" >&2
  fi
  # 2) UGII_BASE_DIR: 可能是 <install> 也可能是 <install>/UGII
  if [ -n "${UGII_BASE_DIR:-}" ]; then
    u="$(to_posix "$UGII_BASE_DIR")"
    if is_install "$u"; then printf '%s\n' "$u"; return; fi
    if is_install "$(dirname "$u")"; then printf '%s\n' "$(dirname "$u")"; return; fi
  fi
  # 3) 常见安装位置: 全部收集后取**版本号最高**的那个(2606 > 2506 > 2406 > 2306 ...)
  #    同一台机器可能同时装着几个版本,挑最新的是最合理的默认值。
  local c cands=""
  for c in "/d/Program Files/Siemens"/* "/c/Program Files/Siemens"/* \
           "/e/Program Files/Siemens"/*; do
    is_install "$c" && cands="$cands$c"$'\n'
  done
  [ -z "$cands" ] && return
  printf '%s' "$cands" | while IFS= read -r line; do
    [ -n "$line" ] && printf '%s\t%s\n' "$(release_of "$line")" "$line"
  done | sort -t$'\t' -k1,1 -rn | head -1 | cut -f2-
}
INSTALL="$(find_install)"
if [ -z "$INSTALL" ]; then
  echo "!! 找不到 Designcenter/NX 安装目录。请用 NX_INSTALL=... 指定。" >&2
  exit 1
fi
SRC="$INSTALL/UGII/copilot/plchat"
echo "安装目录 : $INSTALL"
echo "页面脚本 : $SRC"
echo

# ---------- 2. 复制页面脚本 ------------------------------------------------
# 版本之间文件名会有出入(2306/2406 的页面脚本未必和 2606 同名),所以规则是
# "安装里有哪些 .js 就拷哪些";下面这份已知清单只用来提示缺件,不再是唯一来源。
PAGE_KNOWN="AppService.js HostInteropService.js NXService.js PLChatAgentEventHandler.js PLChatEventHandler.js PLChatFeedbackEventUtils.js hostInterop_async.js plchat.js"
PAGE_ACTUAL="$(cd "$SRC" 2>/dev/null && ls *.js 2>/dev/null | tr '\n' ' ')"
for f in $PAGE_ACTUAL; do
  cp -f "$SRC/$f" "$HERE/$f"
  # 安装目录里的文件是只读的, cp 会把只读属性带过来, 后面打补丁就写不进去
  chmod u+w "$HERE/$f" 2>/dev/null || true
  echo "COPY  $f  ($(wc -c < "$HERE/$f") bytes)"
done
for f in $PAGE_KNOWN; do
  case " $PAGE_ACTUAL " in
    *" $f "*) ;;
    *) echo "MISS  $f  <- 这个安装里没有该文件(不同版本文件名可能不一样, 以实际拷到的为准)" >&2 ;;
  esac
done
# 参考用: 原始入口页(我们不用它, 用自己的 index.html)
[ -f "$SRC/PLChat.html" ] && cp -f "$SRC/PLChat.html" "$HERE/PLChat.original.html"

# ---------- 3. 给 plchat.js 打本地化补丁 -----------------------------------
# 原件在 <script> 上强制 integrity=SRI。本地副本 / 本地服务时 SRI 对不上,
# 浏览器会直接拒绝执行, 于是整页白屏。改成"SRI 存在才校验"。
patch_sri() {
  local f="$HERE/plchat.js"
  [ -f "$f" ] || return
  python - "$f" <<'PYEOF'
import sys, io
p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
OLD = "  script.integrity = scriptSrc.SRI;"
NEW = "  if (scriptSrc.SRI) { script.integrity = scriptSrc.SRI; } // local-host patch"
if NEW in s:
    print("OK    plchat.js  SRI guard already patched")
elif OLD in s:
    s = s.replace(OLD, NEW, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("PATCH plchat.js  SRI guard disabled for local copies")
else:
    print("WARN  plchat.js  expected SRI line not found - upstream may have changed, check by hand")
PYEOF
}
patch_sri
echo

if [ "$SKIP_CDN" = "1" ]; then
  echo "已跳过 CDN 下载 (--skip-cdn)"
  exit 0
fi

# ---------- 4. 下载前端 bundle --------------------------------------------
CDN="https://acc.adhoc.sws.siemens.com/plchat_v2"
DST="$HERE/plchat_v2"
mkdir -p "$DST/static/js" "$DST/static/css" "$DST/assets/config" "$DST/assets/images"

# 非破坏性下载: 已经存在的文件默认不重下, 失败也绝不覆盖本地可用文件。
# 想强制重下: bash fetch-frontend.sh --force
fetch_one() {  # $1 = CDN 上的相对路径, $2 = 本地目标
  local rel="$1" out="$2" code
  if [ -s "$out" ] && [ "$FORCE" = "0" ]; then
    echo "SKIP  $rel  (已存在 $(wc -c < "$out") bytes)"
    return
  fi
  code=$(curl -s --max-time 120 --retry 2 -o "$out.tmp" -w "%{http_code}" "$CDN/$rel")
  if [ "$code" = "200" ] && [ -s "$out.tmp" ]; then
    mv -f "$out.tmp" "$out"
    echo "OK    $rel  ($(wc -c < "$out") bytes)"
  else
    rm -f "$out.tmp"
    echo "FAIL  $rel  (HTTP $code) — 本地原文件未改动"
  fi
}

echo "前端 bundle 源: $CDN"
BUNDLE=(
  "static/js/runtime~main.56cd68ec.js"
  "static/js/main.9cdf9dc5.js"
  "static/js/components.84c3a360.js"
  "static/js/dynamic-plchat.65732d65.js"
  "static/js/dynamic-config.650aebd1.js"
  "static/js/dynamic-command.dfe8be79.js"
  "static/js/dynamic-declarativeui.2bebe43e.js"
  "static/js/dynamic-table.f49084b5.js"
  "static/js/8.ac79b2ef.js"
  "static/js/9.f6eac797.chunk.js"
  "static/css/8.f48c9386.css"
)
for f in "${BUNDLE[@]}"; do fetch_one "$f" "$DST/$f"; done

# ---------- 4b. 把前端里的云端地址改成本地 ----------
# 官方 bundle 里写死了自己的 CDN 源。不改的话:
#   runtime~main.js  -> webpack publicPath 指向云端, 懒加载 chunk 会回去联网(离线就白屏)
#   dynamic-config.js -> 配置/i18n 走跨域, 被 CORS 挡掉, 界面上出现 {{i18n.xxx}} 未翻译占位
# 两处要换的是同一个前缀, 所以统一替换。幂等, 重复跑不会重复改。
patch_bundle() {
  python - "$DST/static/js" <<'PYEOF'
import sys, io, os, glob
jsdir = sys.argv[1]
ORIGIN = "https://acc.adhoc.sws.siemens.com/plchat_v2"
LOCAL  = "/plchat_v2"
targets = sorted(glob.glob(os.path.join(jsdir, "runtime~main.*.js"))) \
        + sorted(glob.glob(os.path.join(jsdir, "dynamic-config.*.js")))
if not targets:
    print("WARN  runtime~main.js / dynamic-config.js not found, skip rewriting")
for p in targets:
    s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
    n = s.count(ORIGIN)
    if n:
        io.open(p, "w", encoding="utf-8", errors="surrogateescape", newline="").write(s.replace(ORIGIN, LOCAL))
        print("PATCH %-34s replaced %d CDN url(s) -> %s" % (os.path.basename(p), n, LOCAL))
    elif LOCAL in s:
        print("OK    %-34s already points at the local path" % os.path.basename(p))
    else:
        print("WARN  %-34s neither CDN nor local path found - upstream layout may have changed" % os.path.basename(p))
PYEOF
}
patch_bundle

# ---------- 5. 下载 config / images 资源 -----------------------------------
# CDN 上是公开的, 但浏览器跨域直接取会被 CORS 挡, 所以落盘由宿主同源提供
echo
# 清单只列 CDN 上确实存在的; workspace/commands/views/layout/themes 等在当前
# 版本上是 404(页面代码里有名字但没有实体文件), 不要往这里加, 加了只会刷 FAIL。
CONFIGS="adapters decorators typeFiles indicators commandsViewModel syncStrategy i18n i18n_zh_CN states typeIconsRegistry"
for n in $CONFIGS; do fetch_one "assets/config/$n.json" "$DST/assets/config/$n.json"; done
IMAGES="Error_Icon Landing_Page_light Landing_Page_Light Landing_Page_dark"
for n in $IMAGES; do fetch_one "assets/images/$n.svg" "$DST/assets/images/$n.svg"; done

echo
echo "完成。"
echo "  启动宿主:  node server.js"
echo "  打开页面:  http://127.0.0.1:8765/"
