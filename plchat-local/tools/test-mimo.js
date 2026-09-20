/* test-mimo.js — 验证 MiMo Token Plan 的 OpenAI 兼容接口 + function calling */
const fs = require("fs");
const path = require("path");
const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "config.json"), "utf8"));
const BASE = cfg.baseUrl.replace(/\/+$/, "");
const H = { "Content-Type": "application/json", "Authorization": "Bearer " + cfg.apiKey };
const mask = (s) => s ? s.slice(0, 6) + "…" + s.slice(-4) : "(空)";

async function j(url, opt) {
  const r = await fetch(url, opt);
  const t = await r.text();
  let b = null; try { b = JSON.parse(t); } catch (e) { }
  return { status: r.status, body: b, text: t.slice(0, 600) };
}

(async () => {
  console.log("baseUrl =", BASE, " key =", mask(cfg.apiKey), " model =", cfg.model);

  console.log("\n=== 1) GET /models ===");
  const m = await j(BASE + "/models", { headers: H });
  console.log("status", m.status);
  if (m.body && m.body.data) console.log(m.body.data.map(x => x.id).join(", "));
  else console.log(m.text);

  console.log("\n=== 2) 普通对话 ===");
  const t0 = Date.now();
  const c = await j(BASE + "/chat/completions", {
    method: "POST", headers: H,
    body: JSON.stringify({ model: cfg.model, messages: [{ role: "user", content: "用一句话说明你是谁,以及你属于哪个厂商。" }], stream: false })
  });
  console.log("status", c.status, "耗时", Date.now() - t0, "ms");
  console.log(JSON.stringify(c.body && c.body.choices && c.body.choices[0].message, null, 1).slice(0, 600) || c.text);

  console.log("\n=== 3) function calling ===");
  const t1 = Date.now();
  const f = await j(BASE + "/chat/completions", {
    method: "POST", headers: H,
    body: JSON.stringify({
      model: cfg.model, stream: false,
      messages: [{ role: "user", content: "这台机器上装的是什么版本的 NX?请调用工具查询。" }],
      tools: [{
        type: "function",
        function: {
          name: "nx_status",
          description: "报告本机 NX / Designcenter 环境",
          parameters: { type: "object", properties: {}, required: [] }
        }
      }],
      tool_choice: "auto"
    })
  });
  console.log("status", f.status, "耗时", Date.now() - t1, "ms");
  const msg = f.body && f.body.choices && f.body.choices[0].message;
  console.log(JSON.stringify(msg, null, 1).slice(0, 800) || f.text);
})();
