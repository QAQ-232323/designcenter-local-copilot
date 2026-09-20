// test-stdin.js —— 验证 nx-skill 的 review 提交走 stdin 时中文编码是否正确
// (Windows 下 Python 读 stdin 默认不是 UTF-8, 曾经把中文备注变成乱码)
// 用法: node test-stdin.js
const { spawn } = require("child_process");
const fs = require("fs");
const NX_SKILL_DIR = process.env.NX_SKILL_DIR || "E:/AIprojects/nx-skill";
const NX_WORKSPACE = process.env.NX_SKILL_WORKSPACE || "E:/AIprojects/nx-workspace";

const plan = { prompt: "法兰盘建模(Node-stdin 自检)", steps: [{ id: "01", name: "01_Stdin_Check", operation: "status", gate: "auto", note: "中文备注:stdin 编码" }] };
const json = JSON.stringify(plan);
console.log("发送的 JSON 字节长度:", Buffer.byteLength(json, "utf8"));

const env = Object.assign({}, process.env, {
  PYTHONPATH: "src", PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1",
  NX_SKILL_SKIP_GLOBAL_SEARCH: "true",
  NX_SKILL_WORKSPACE: NX_WORKSPACE
});
const p = spawn("python", ["-m", "nx_skill", "review", "submit"], { cwd: NX_SKILL_DIR, env });
p.stdin.write(json); p.stdin.end();
let o = ""; p.stdout.on("data", d => o += d); p.stderr.on("data", d => o += d);
p.on("close", () => {
  const back = JSON.parse(fs.readFileSync(NX_WORKSPACE + "/review/plan.json", "utf8"));
  console.log("落盘后的 note  :", JSON.stringify(back.steps[0].note));
  console.log("落盘后的 prompt:", JSON.stringify(back.prompt));
  console.log("是否一致       :", back.steps[0].note === plan.steps[0].note ? "✔ 是" : "✘ 否 —— 编码有问题");
});
