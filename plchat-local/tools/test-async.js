(async () => {
  const q = "建模一个阶梯轴,含三段不同直径、两端倒角和一个键槽";
  const t0 = Date.now();
  const start = await (await fetch("http://127.0.0.1:8765/api/plan/author", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q })
  })).json();
  console.log("任务号:", start.jobId, "| 立刻返回:", Date.now() - t0, "ms");
  for (;;) {
    await new Promise(r => setTimeout(r, 3000));
    const s = await (await fetch("http://127.0.0.1:8765/api/plan/author/status?id=" + start.jobId)).json();
    if (s.state === "running") { process.stdout.write("."); continue; }
    console.log("\n状态:", s.state, "| 总耗时:", Math.round(s.elapsedMs / 1000) + "s");
    const r = s.result || {};
    if (r.ok) {
      console.log("通过次数:", r.attempt, "| 计划:", r.planId, "| 步数:", r.stepCount);
      (r.steps || []).forEach(x => console.log("   ", String(x.name).padEnd(28), String(x.operation).padEnd(11), x.gate));
    } else {
      console.log("失败:", String(r.error).slice(0, 700));
    }
    break;
  }
})();
