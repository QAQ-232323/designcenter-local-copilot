// list-sessions.js — 列出本机 DSH 会话(含标题摘要),用于挑选要引用的会话
// 用法: node list-sessions.js                -> 所有项目 + 会话数
//       node list-sessions.js NXMCP DCMCP    -> 指定项目的会话明细
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");
const Z = process.env.ZSTD || "C:/Users/01/AppData/Local/Microsoft/WinGet/Packages/oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe/poppler-25.07.0/Library/bin/zstd.exe";
const ROOT = path.join(os.homedir(), ".dsh", "sessions");
const want = process.argv.slice(2);

function lines(file) {
  try { return execFileSync(Z, ["-dc", file], { maxBuffer: 1024 * 1024 * 256 }).toString("utf8").split("\n").filter(Boolean); }
  catch (e) { return []; }
}
function summarize(file) {
  let out = { first: "", when: "", origin: "", turns: 0 };
  for (const l of lines(file)) {
    let o; try { o = JSON.parse(l); } catch (e) { continue; }
    if (o.type === "session") { out.origin = o.origin || "user"; out.when = o.createdAt ? new Date(o.createdAt).toLocaleString("zh-CN") : ""; }
    if (o.type === "user/message") {
      out.turns++;
      if (!out.first) {
        let t = "";
        const c = o.data && o.data.content;
        if (Array.isArray(c)) t = c.map(x => x && x.text ? x.text : "").join(" ");
        else if (typeof c === "string") t = c;
        if (t.indexOf("【环境变更提示】") >= 0) { /* 跳过导入提示 */ } else out.first = t;
      }
    }
  }
  return out;
}

const projects = fs.readdirSync(ROOT).filter(p => fs.statSync(path.join(ROOT, p)).isDirectory());
if (!want.length) {
  console.log("项目目录(" + projects.length + "):");
  for (const p of projects) {
    const n = fs.readdirSync(path.join(ROOT, p)).filter(d => fs.existsSync(path.join(ROOT, p, d, "session.jsonl.zstd"))).length;
    if (n) console.log("  " + String(n).padStart(3) + "  " + p.replace(/^--|--$/g, ""));
  }
  process.exit(0);
}

for (const proj of projects) {
  const slug = proj.replace(/^--|--$/g, "");
  if (!want.some(w => slug.includes(w))) continue;
  const pdir = path.join(ROOT, proj);
  const ids = fs.readdirSync(pdir).filter(d => fs.existsSync(path.join(pdir, d, "session.jsonl.zstd")));
  console.log("\n### " + slug + "  (" + ids.length + ")");
  const rows = ids.map(id => {
    const f = path.join(pdir, id, "session.jsonl.zstd");
    const s = summarize(f);
    return { id, size: fs.statSync(f).size, ...s };
  }).sort((a, b) => b.size - a.size);
  for (const r of rows) {
    console.log("  " + r.id.padEnd(42) + " " + r.when.padEnd(20) + " " + String(Math.round(r.size / 1024)).padStart(6) + "KB  " + r.first.replace(/\s+/g, " ").slice(0, 64));
  }
}
