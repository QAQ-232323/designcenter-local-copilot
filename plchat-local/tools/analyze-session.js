// analyze-session.js — 把 DSH 会话 dump 成可读的结构化摘要
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const Z = "C:/Users/01/AppData/Local/Microsoft/WinGet/Packages/oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe/poppler-25.07.0/Library/bin/zstd.exe";
const OUT = process.argv[2];
const files = process.argv.slice(3);
fs.mkdirSync(OUT, { recursive: true });

function blocks(content) {
  const texts = [], calls = [];
  if (typeof content === "string") return { texts: [content], calls };
  if (!Array.isArray(content)) return { texts, calls };
  for (const b of content) {
    if (!b) continue;
    if (b.type === "text" && b.text) texts.push(b.text);
    else if (b.type === "tool-call") calls.push({ name: b.name, args: b.arguments });
  }
  return { texts, calls };
}

for (const f of files) {
  const id = path.basename(path.dirname(f));
  const recs = execFileSync(Z, ["-dc", f], { maxBuffer: 1024 * 1024 * 512 }).toString("utf8")
    .split("\n").filter(Boolean).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean);
  const meta = recs.find(r => r.type === "session") || {};
  const users = [], assistants = [], tools = new Map(), filesTouched = new Map();

  function noteFiles(s) {
    if (!s) return;
    for (const m of String(s).matchAll(/[A-Za-z]:[\\/][^"\n\\]{0,150}?\.(ts|js|tsx|json|md|py|yaml|yml|cs|csx|txt|cmd|ps1|toml|mjs|cjs)/gi)) {
      const p = m[0].replace(/\\/g, "/").replace(/\\"/g, "");
      filesTouched.set(p, (filesTouched.get(p) || 0) + 1);
    }
  }

  for (const r of recs) {
    if (r.type === "user/message") {
      const { texts } = blocks(r.data && r.data.content);
      const t = texts.join("\n").trim();
      if (t && t.indexOf("【环境变更提示】") < 0) users.push(t);
    } else if (r.type === "assistant/message") {
      const { texts } = blocks(r.data && r.data.message && r.data.message.content);
      const t = texts.join("\n").trim();
      if (t) assistants.push(t);
    } else if (r.type === "tool/call") {
      const d = r.data || {};
      tools.set(d.name || "?", (tools.get(d.name || "?") || 0) + 1);
      noteFiles(d.arguments);
    }
  }

  const out = [];
  out.push("# 会话 " + id);
  out.push("- cwd: " + (meta.cwd || "") + "   origin: " + (meta.origin || "user") + "   createdAt: " + (meta.createdAt ? new Date(meta.createdAt).toLocaleString("zh-CN") : ""));
  out.push("- 记录 " + recs.length + " / 用户消息 " + users.length + " / 助手消息 " + assistants.length);
  out.push("- 工具: " + [...tools.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0] + "×" + e[1]).join(", "));
  out.push("");
  out.push("## 用户消息(全部)");
  users.forEach((u, i) => { out.push("### U" + (i + 1)); out.push(u.slice(0, 5000)); out.push(""); });
  out.push("## 助手文本(截断 700 字)");
  assistants.forEach((a, i) => { out.push("### A" + (i + 1) + " " + a.replace(/\s+/g, " ").slice(0, 700)); });
  out.push("");
  out.push("## 涉及文件(按出现次数)");
  out.push([...filesTouched.entries()].sort((a, b) => b[1] - a[1]).slice(0, 80).map(e => e[1] + "\t" + e[0]).join("\n"));
  const dest = path.join(OUT, id + ".md");
  fs.writeFileSync(dest, out.join("\n"));
  console.log(id.slice(0, 30).padEnd(32) + (fs.statSync(dest).size / 1024).toFixed(0).padStart(5) + "KB  users=" + users.length + " asst=" + assistants.length + " tools=" + [...tools.values()].reduce((a, b) => a + b, 0));
}
