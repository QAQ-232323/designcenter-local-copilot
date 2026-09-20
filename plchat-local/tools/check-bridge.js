// check-bridge.js —— 检查 .NET 实时桥的两个产物是不是"已打 127.0.0.1 补丁"的版本
// 背景: 开着 Clash 之类 TUN 代理时, 桥自报的主机名会被解析成假 IP(198.18.x.x),
//       客户端连不上。修法是把两端都钉死在 127.0.0.1。本脚本就是验证补丁进没进去。
// 用法: node check-bridge.js
const fs = require("fs");
const NX_SKILL_DIR = process.env.NX_SKILL_DIR || "E:/AIprojects/nx-skill";

const files = {
  "server.dll": NX_SKILL_DIR + "/nx_runtime/startup/NxLiveBridgeServer.dll",
  "client.exe": NX_SKILL_DIR + "/scripts/dotnet_bridge/bin/NxLiveBridgeClient.exe"
};
const needles = ["machineName", "127.0.0.1", "nx_live_bridge_http", "http://localhost:", "http://127.0.0.1:"];
let missing = 0;
for (const [label, f] of Object.entries(files)) {
  if (!fs.existsSync(f)) { console.log("--- " + label + "  不存在: " + f); missing++; continue; }
  const buf = fs.readFileSync(f);
  console.log("--- " + label + "  (" + buf.length + " bytes, mtime " + fs.statSync(f).mtime.toLocaleString("zh-CN") + ")");
  let any = false;
  for (const n of needles) {
    // .NET 字符串常量是 UTF-16LE, 所以两种编码都找
    const hit = buf.includes(Buffer.from(n, "utf16le")) || buf.includes(Buffer.from(n, "utf8"));
    if (hit) { console.log("    OK  含 " + JSON.stringify(n)); any = true; }
  }
  if (!any) console.log("    !! 一个特征串都没找到, 可能没打补丁");
}
console.log(missing ? "\n有 " + missing + " 个文件不存在, 先编译桥: 见 integrations/nx-skill/README.md" : "\n检查完毕");
