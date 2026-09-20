/* nxdetect.js — 找出本机所有 Siemens Designcenter / NX 安装，并识别哪些版本带内置 Copilot
 *
 * 为什么不写死版本号:内置 Copilot 是"这一版软件里有没有这个功能"决定的,不是版本号决定的。
 * 本模块只认**结构特征**,所以 2606 / 2506 / 2406 / 2306 ... 一视同仁:
 *
 *   UGII/copilot/plchat/PLChat.html   内置 Copilot 页面本体(最强特征,页面前端从这里重建)
 *   UGII/copilot/plchat/              页面脚本目录(fetch-frontend.sh 也从这里取那 8 个 .js)
 *   UGII/copilot/                      Copilot 资源根
 *   NXBIN/libcopilot*.dll             AI 内核库(实测 2606 有 libcopilot / libcopilotui /
 *                                     libcopilotinit / libcopilotuiinit,其它版本命名可能不同,
 *                                     所以按通配匹配而不是枚举具体名字)
 *
 * 版本号(release,用于显示与 plservice-version)按下面的顺序取,取不到就是 "unknown":
 *   1. 注册表键名里的 4 位 token,如 "Designcenter 2606" / "NX 2506"
 *   2. 安装目录名里的 4 位 token,如 "DC 2606" / "NX 2506"
 *   3. 版本标记文件(NXBIN/nxversion 等)里的 4 位 token
 * 这套规则与 nx-skill 的 discovery.detect_release() 一致(那边是权威实现,这里只是
 * 宿主侧的零依赖复刻,只做显示与"选哪个安装"用)。
 *
 * 安装根目录的来源,按可信度排序:
 *   1. 显式指定(config.json 的 nxRoot / 环境变量 UGII_BASE_DIR、NX_SKILL_NX_ROOT、NX_ROOT)
 *   2. 注册表 HKLM\SOFTWARE\Siemens\* 每个子键的 UGII_BASE_DIR / INSTALLDIR
 *   3. 各固定盘的 \Program Files\Siemens\* 与 \Program Files (x86)\Siemens\*
 *
 * 零依赖(Node 内置模块)。输出结构见 probe()。
 * 一个已知限制:`reg query` 的输出用控制台代码页,若安装路径含中文可能乱码 ——
 * Siemens 默认装到 ASCII 路径,真乱码时用 config.json 的 nxRoot 显式指定即可。
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

/** Copilot 特征标记:相对安装根目录,从强到弱。 */
const COPILOT_MARKERS = [
  ["page", "UGII/copilot/plchat/PLChat.html"],   // 页面本体
  ["plchat_dir", "UGII/copilot/plchat"],         // 页面脚本目录
  ["copilot_dir", "UGII/copilot"],               // Copilot 资源根
];
/** AI 内核库所在目录 + 通配(Copilot 功能的核心,页面可以没有,库不会没有)。 */
const COPILOT_LIB_DIR = "NXBIN";
const COPILOT_LIB_RE = /^libcopilot.*\.(dll|so|dylib)$/i;
const RELEASE_RE = /(?<!\d)(\d{4})(?!\d)/;

function clean(p) {
  if (!p) return "";
  let s = String(p).trim().replace(/^"|"$/g, "");
  s = s.replace(/[\\/]+$/, "");
  return s;
}

function isDir(p) { try { return fs.statSync(p).isDirectory(); } catch (e) { return false; } }
function isFile(p) { try { return fs.statSync(p).isFile(); } catch (e) { return false; } }

/** 从一段名字里取 4 位 release token(如 "Designcenter 2606" -> "2606")。 */
function releaseFromText(text) {
  const m = RELEASE_RE.exec(String(text || ""));
  return m ? m[1] : "";
}

/** 从安装源目录名里取 NX 风格的完整版本(如 "DC2606.1700" 或 "NX2506.3000" -> "2606.1700")。
 *  这是页面上 plservice-version 用的那种格式,比只有 release 精确。取不到就返回 ""。 */
function versionFromText(text) {
  const m = /(\d{4})\.(\d{1,6})/.exec(String(text || ""));
  return m ? m[1] + "." + m[2] : "";
}

/* ------------------------------------------------------------------ *
 * 卸载登记表:把安装路径映射到产品名与精确版本
 * 实测(2606):HKLM\...\Uninstall\{GUID} 里
 *   DisplayName     = "Siemens Designcenter 2606"   -> release
 *   InstallLocation = "D:\Program Files\Siemens\DC 2606\" -> 与安装根目录一一对应
 *   InstallSource   = "D:\DC2606\DC2606.1700\designcenter\" -> 精确版本 2606.1700
 * 换版本(NX 2506 / 2406 ...)同样是这几个值,所以按值解析,不按名字写死。
 * ------------------------------------------------------------------ */
let UNINSTALL = null;
function uninstallEntries(force) {
  if (UNINSTALL && !force) return UNINSTALL;
  const out = [];
  const prefixes = [
    "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
  ];
  for (const hive of prefixes) {
    let text = "";
    try {
      // 不能用 /f 过滤:reg 只回显命中的**值**,会把 DisplayVersion / InstallSource 吃掉。
      // 整棵树拉回来本地筛,输出量对内存无所谓(缓存一次)。
      text = execFileSync("reg", ["query", hive, "/s"], {
        encoding: "utf8", windowsHide: true, timeout: 15000, maxBuffer: 8 * 1024 * 1024,
      });
    } catch (e) { continue; }
    let cur = null;
    for (const raw of String(text).split(/\r?\n/)) {
      const line = raw.replace(/\s+$/, "");
      if (/^HKEY_/.test(line)) { cur = { key: line, name: "", version: "", location: "", source: "" }; out.push(cur); continue; }
      if (!cur) continue;
      const m = /^\s+(\S.*?)\s{2,}REG_(?:SZ|EXPAND_SZ)\s{2,}(.*)$/.exec(line);
      if (!m) continue;
      const n = m[1].trim(), v = clean(m[2]);
      if (!v) continue;
      if (n === "DisplayName") cur.name = v;
      else if (n === "DisplayVersion") cur.version = v;
      else if (n === "InstallLocation") cur.location = v;
      else if (n === "InstallSource") cur.source = v;
    }
  }
  const isSiemens = (e) => /siemens|designcenter|simcenter/i.test(e.name + " " + e.location + " " + e.source) ||
    /(^|[^a-z])nx([^a-z]|$)/i.test(e.name);
  UNINSTALL = out.filter(e => (e.name || e.location || e.source) && isSiemens(e));
  return UNINSTALL;
}

/** 给一个安装根目录配上产品名与精确版本(找不到对应登记项就返回空)。 */
function uninstallFor(root) {
  const want = clean(root).toLowerCase();
  let best = null;
  for (const e of uninstallEntries()) {
    const loc = clean(e.location).toLowerCase();
    if (loc && loc === want) return e;
    if (!best && e.source && clean(e.source).toLowerCase().indexOf(want) === 0) best = e;
  }
  return best;
}

function releaseFromRoot(root) {
  for (const part of [path.basename(root), path.basename(path.dirname(root))]) {
    const r = releaseFromText(part);
    if (r) return r;
  }
  for (const marker of ["NXBIN/nxversion", "NXBIN/nx_version", "nxversion", "NXBIN/nxrelease.dat"]) {
    const f = path.join(root, marker);
    if (!isFile(f)) continue;
    try {
      const r = releaseFromText(fs.readFileSync(f, "utf8").split(/\r?\n/)[0]);
      if (r) return r;
    } catch (e) { /* 读不到就继续找 */ }
  }
  return "unknown";
}

/** 用结构特征判断这个安装里有没有内置 Copilot,并记下命中了哪些特征。 */
function probeCopilot(root) {
  const markers = [];
  let page = null, scriptsDir = null, copilotRoot = null;
  for (const [name, rel] of COPILOT_MARKERS) {
    const p = path.join(root, ...rel.split("/"));
    if (name === "page" ? isFile(p) : isDir(p)) {
      markers.push(name);
      if (name === "page") page = p;
      if (name === "plchat_dir") scriptsDir = p;
      if (name === "copilot_dir") copilotRoot = p;
    }
  }
  let libs = [];
  const libDir = path.join(root, COPILOT_LIB_DIR);
  try {
    libs = fs.readdirSync(libDir).filter(f => COPILOT_LIB_RE.test(f)).map(f => path.join(libDir, f));
  } catch (e) { /* 没有 NXBIN 就没有库 */ }
  if (libs.length) markers.push("ai_libs");
  return {
    available: markers.length > 0,
    // 页面在 = 这个版本的前端能被 fetch-frontend.sh 重建;只有库 = 有 AI 但没有我们镜像的那套页面
    pageAvailable: !!page,
    markers,
    page,
    scriptsDir,
    copilotRoot,
    libs,
  };
}

/** 探测单个安装根目录。valid = 是 NX 安装(有 NXBIN);root 不存在时返回 null。
 *  extra.versions=true 时才会去翻卸载登记表拿"精确版本 2606.1700"——那次查询要
 *  拉整棵 Uninstall 树,约 2~3 秒;只有原版页面(plservice-version)需要它,
 *  普通识别(哪个安装、带不带 Copilot)不需要。 */
function probe(root, extra) {
  const dir = clean(root);
  if (!dir || !isDir(dir)) return null;
  const nxbin = path.join(dir, "NXBIN");
  if (!isDir(nxbin)) return null;
  const copilot = probeCopilot(dir);
  const ugrafExe = path.join(nxbin, "ugraf.exe");
  const reg = (extra && extra.versions) ? uninstallFor(dir) : null;
  // 版本:登记表里的精确版本(2606.1700 这种)优先,其次目录名/标记文件里的 release
  const release = (reg && releaseFromText(reg.name)) || releaseFromRoot(dir);
  const version = (reg && versionFromText(reg.source)) || "";
  return Object.assign({
    root: dir,
    release,
    version,                                   // 精确版本,取不到就是 ""
    product: (reg && reg.name) || "",          // 如 "Siemens Designcenter 2606"
    nxbin,
    ugraf: isFile(ugrafExe) ? ugrafExe : path.join(nxbin, "ugraf"),
    copilot,
    hasCopilot: copilot.available,
  }, extra || {});
}

/* ------------------------------------------------------------------ *
 * 候选安装目录
 * ------------------------------------------------------------------ */
function envCandidates(env) {
  const out = [];
  const vars = ["NX_SKILL_NX_ROOT", "UGII_BASE_DIR", "NX_ROOT", "UGII_ROOT_DIR"];
  for (const v of vars) {
    const val = clean(env[v]);
    if (val) out.push({ root: val, source: "env:" + v });
  }
  return out;
}

/** 注册表 HKLM\SOFTWARE\Siemens\* —每个子键一个已安装产品,值里有 UGII_BASE_DIR。 */
function registryCandidates() {
  const out = [];
  for (const hive of ["HKLM\\SOFTWARE\\Siemens", "HKLM\\SOFTWARE\\WOW6432Node\\Siemens"]) {
    let text = "";
    try {
      text = execFileSync("reg", ["query", hive, "/s"], { encoding: "utf8", windowsHide: true, timeout: 8000 });
    } catch (e) { continue; }
    let currentKey = "", currentProduct = "";
    for (const raw of String(text).split(/\r?\n/)) {
      const line = raw.replace(/\s+$/, "");
      if (/^HKEY_/.test(line)) { currentKey = line; currentProduct = line.split("\\").pop() || ""; continue; }
      const m = /^\s+(\S.*?)\s{2,}REG_SZ\s{2,}(.*)$/.exec(line);
      if (!m) continue;
      const valueName = m[1].trim();
      const valueData = clean(m[2]);
      if (!valueData) continue;
      if (valueName === "UGII_BASE_DIR" || valueName === "INSTALLDIR" || valueName === "(默认)") {
        out.push({ root: valueData, source: "registry:" + currentProduct, product: currentProduct, key: currentKey });
      }
    }
  }
  return out;
}

/** 各固定盘的 \Program Files\Siemens\* —— 注册表没登记时的兜底。 */
function driveCandidates() {
  const out = [];
  for (let c = 65; c <= 90; c++) {
    const letter = String.fromCharCode(c) + ":";
    const base = letter + "\\";
    if (!isDir(base)) continue;
    for (const pf of ["Program Files", "Program Files (x86)"]) {
      const siemens = path.join(letter + "\\", pf, "Siemens");
      if (!isDir(siemens)) continue;
      let names = [];
      try { names = fs.readdirSync(siemens); } catch (e) { continue; }
      for (const n of names) {
        const p = path.join(siemens, n);
        if (isDir(path.join(p, "NXBIN"))) out.push({ root: p, source: pf + "\\Siemens" });
      }
    }
  }
  return out;
}

function allCandidates(env) {
  return [].concat(envCandidates(env || process.env), registryCandidates(), driveCandidates());
}

/** 版本号比较:大在前。release 是 "2606" 这种,直接比数值。 */
function releaseRank(p) {
  const n = parseInt(p.release, 10);
  return isNaN(n) ? -1 : n;
}

/**
 * 探测本机所有 Siemens 安装。
 * 排序:先按 release 从大到小(2606 > 2506 > 2406 > 2306),同版本内"带 Copilot"优先。
 */
function detectAll(opts) {
  const o = opts || {};
  const seen = new Map();
  for (const c of allCandidates(o.env)) {
    const p = probe(c.root, { source: c.source, product: c.product, versions: o.versions });
    if (!p) continue;
    const key = p.root.toLowerCase();
    const prev = seen.get(key);
    if (!prev) { seen.set(key, p); continue; }
    // 同一路径从多处发现:合并更具体的信息(注册表给的产品名更准)
    if (!prev.product && p.product) prev.product = p.product;
    if (prev.source.indexOf("env:") !== 0 && p.source.indexOf("env:") === 0) prev.source = p.source;
  }
  for (const c of (o.extraRoots || [])) {
    const p = probe(c.root, { source: c.source || "explicit", product: c.product, versions: o.versions });
    if (p) seen.set(p.root.toLowerCase(), p);
  }
  const list = Array.from(seen.values());
  list.sort((a, b) => (releaseRank(b) - releaseRank(a)) || (Number(b.hasCopilot) - Number(a.hasCopilot)) || a.root.localeCompare(b.root));
  return list;
}

/**
 * 选一个"当前使用"的安装。
 * 指定了 preferred(config.json 的 nxRoot)就用它(它必须是个有效安装,否则退回自动探测);
 * 否则优先选**带 Copilot 页面**的最高版本 —— 本地宿主镜像的就是那套页面,没有页面的版本
 * 只能当 NX 环境用,当不了 Copilot 宿主。
 */
function pick(preferred, opts) {
  const all = detectAll(opts);
  const want = clean(preferred);
  if (want) {
    const exact = all.find(p => p.root.toLowerCase() === want.toLowerCase()) ||
      probe(want, { source: "configured", versions: (opts || {}).versions });
    if (exact) return exact;
  }
  return all.find(p => p.copilot.pageAvailable) || all[0] || null;
}

module.exports = {
  detectAll, probe, pick, probeCopilot,
  releaseFromText, releaseFromRoot, versionFromText,
  uninstallEntries, COPILOT_MARKERS,
};
