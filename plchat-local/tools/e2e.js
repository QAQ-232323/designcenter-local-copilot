(async () => {
  const post = (u, b) => fetch("http://127.0.0.1:8765" + u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then(r => r.json());
  const get = (u) => fetch("http://127.0.0.1:8765" + u).then(r => r.json());
  const wait = async (u, t0) => { for (;;) { await new Promise(r => setTimeout(r, 3000)); const s = await get(u); if (s.state !== "running") return s; process.stdout.write("."); } };

  console.log("=== 1. 生成法兰计划 ===");
  let t0 = Date.now();
  const j1 = await post("/api/plan/author", { question: "建模一个法兰盘,外径200厚20,中心通孔80,在直径160的分度圆上均布6个直径16的螺栓孔" });
  const s1 = await wait("/api/plan/author/status?id=" + j1.jobId);
  const r1 = s1.result || {};
  console.log("\n  ok:", r1.ok, "| 耗时:", Math.round(s1.elapsedMs / 1000) + "s | 通过次数:", r1.attempt, "| 步数:", r1.stepCount);
  (r1.steps || []).forEach(x => console.log("   ", String(x.name).padEnd(26), String(x.operation).padEnd(11), x.gate));

  console.log("\n=== 2. 自动执行(headless) ===");
  const j2 = await post("/api/plan/run", {});
  const s2 = await wait("/api/plan/run/status?id=" + j2.jobId);
  const r2 = s2.result || {};
  console.log("\n  ok:", r2.ok, "| 耗时:", Math.round(s2.elapsedMs / 1000) + "s | NX 内部:", r2.nxSeconds, "s");
  console.log("  零件:", r2.part, "| 已保存:", r2.saved);
  (r2.steps || []).forEach(x => console.log("   ", String(x.id).padEnd(4), String(x.name || "").padEnd(28), x.status, x.message ? ("— " + String(x.message).slice(0, 90)) : ""));
  if (!r2.ok && r2.error) console.log("  错误:", String(r2.error).slice(0, 300));
})();
