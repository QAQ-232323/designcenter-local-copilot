// gate-test.js —— 拿 review 队列里已有的脚本, 过一次宿主的静态门禁
// (Python 语法检查 + NXOpen API 名是否存在), 用来验证门禁本身有没有失灵。
// 用法: 先起宿主(node server.js), 再 node gate-test.js
const fs = require("fs");
const NX_WORKSPACE = process.env.NX_SKILL_WORKSPACE || "E:/AIprojects/nx-workspace";
const HOST = process.env.NX_HOST_URL || "http://127.0.0.1:8765";
const dir = NX_WORKSPACE + "/review/scripts";

if (!fs.existsSync(dir)) { console.log("没有脚本目录: " + dir + "\n先让 Copilot 生成一份计划。"); process.exit(0); }
const files = fs.readdirSync(dir).filter(f => f.endsWith(".py"));
if (!files.length) { console.log("脚本目录是空的: " + dir); process.exit(0); }

const check = (script) => fetch(HOST + "/api/nxopen/check", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ script })
}).then(r => r.json());

(async () => {
  for (const f of files) {
    const src = fs.readFileSync(dir + "/" + f, "utf8");
    const j = await check(src);
    console.log("--- " + f);
    console.log("    语法 : " + (j.syntax.ok ? "OK" : "失败 -> " + String(j.syntax.error).trim().split("\n").pop().slice(0, 100)));
    console.log("    API  : " + (j.api.ok ? "全部存在" : (j.api.unknown.length + " 个不存在的名字: " + j.api.unknown.slice(0, 8).join(", "))));
  }
  const probe = await check("x");
  console.log("\n索引规模: " + probe.indexSize + " 个 API 名");
})();
