/* probe.js - open page via CDP, collect console/network, screenshot */
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const URL_ = process.argv[2] || "http://127.0.0.1:8765/";
const OUT = process.argv[3] || "shot.png";
const WAIT = Number(process.argv[4] || 12000);
const PORT = 9222 + Math.floor(Math.random() * 400);
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const UD = path.join(os.tmpdir(), "cdpprobe" + PORT);

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
  "--no-default-browser-check", "--disable-extensions",
  "--user-data-dir=" + UD,
  "--remote-debugging-port=" + PORT,
  "--window-size=1300,950",
  "about:blank"
], { stdio: "ignore" });

const sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

async function getWsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch("http://127.0.0.1:" + PORT + "/json/list");
      const list = await r.json();
      const page = list.find(function (t) { return t.type === "page"; });
      if (page && page.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch (e) { }
    await sleep(300);
  }
  throw new Error("devtools not ready");
}

(async function () {
  const wsUrl = await getWsUrl();
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const logs = [];
  const netFail = [];
  const reqs = [];
  const resp = [];

  const send = function (method, params) {
    return new Promise(function (res) {
      const mid = ++id;
      pending.set(mid, res);
      ws.send(JSON.stringify({ id: mid, method: method, params: params || {} }));
    });
  };

  ws.addEventListener("message", function (ev) {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); return; }
    if (m.method === "Runtime.consoleAPICalled") {
      logs.push("[" + m.params.type + "] " + m.params.args.map(function (a) { return a.value !== undefined ? a.value : (a.description || a.type); }).join(" "));
    }
    if (m.method === "Runtime.exceptionThrown") {
      const d = m.params.exceptionDetails;
      logs.push("[exception] " + ((d.exception && d.exception.description) || d.text));
    }
    if (m.method === "Log.entryAdded") {
      logs.push("[log:" + m.params.entry.level + "] " + m.params.entry.text + " " + (m.params.entry.url || ""));
    }
    if (m.method === "Network.responseReceived") {
      const u = m.params.response.url;
      resp.push(m.params.response.status + " " + u);
    }
    if (m.method === "Network.requestWillBeSent") {
      const u = m.params.request.url;
      if (u.indexOf("127.0.0.1:8765") < 0 && reqs.indexOf(u) < 0) reqs.push(u);
    }
    if (m.method === "Network.loadingFailed") {
      netFail.push(m.params.errorText + " " + (m.params.blockedReason || ""));
    }
    if (m.method === "Network.responseReceived" && m.params.response.status >= 400) {
      netFail.push("HTTP " + m.params.response.status + " " + m.params.response.url);
    }
  });

  await new Promise(function (r) { ws.addEventListener("open", r); });
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Page.enable");
  await send("Network.enable");
  await send("Page.navigate", { url: URL_ });
  await sleep(WAIT);

  const actionFile = process.argv[5];
  if (actionFile) {
    const act = fs.readFileSync(path.join(__dirname, actionFile), "utf8");
    const ar = await send("Runtime.evaluate", { expression: act, returnByValue: true });
    console.log("=== ACTION ===\n" + JSON.stringify(ar.result && ar.result.value));
    await sleep(Number(process.argv[6] || 8000));
  }

  const expr = fs.readFileSync(path.join(__dirname, "expr.js"), "utf8");
  const probe = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUT, Buffer.from(shot.data, "base64"));

  console.log("=== PROBE ===");
  console.log(probe.result && probe.result.value);
  console.log("=== CONSOLE (" + logs.length + ") ===");
  console.log(logs.slice(-50).join("\n"));
  console.log("=== RESPONSES (" + resp.length + ") ===");
  console.log(resp.join("\n"));
  console.log("=== REMOTE REQUESTS (" + reqs.length + ") ===");
  console.log(reqs.join("\n"));
  console.log("=== NET FAIL (" + netFail.length + ") ===");
  console.log(Array.from(new Set(netFail)).slice(0, 25).join("\n"));
  ws.close();
  chrome.kill();
  process.exit(0);
})().catch(function (e) { console.error("PROBE ERROR", e); chrome.kill(); process.exit(1); });
