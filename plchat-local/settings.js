/* settings.js — Copilot 页面内的本地宿主面板
 * 选项卡:复核队列(Review Plan) / 模型 / nx-skill
 * 计划一提交就自动载入复核选项卡,并在齿轮按钮上打红点提示。
 */
(function () {
  var API = "/api/settings";
  var state = null;
  var lastPlanId = null;
  var lastSeenPlanId = null;
  var pollTimer = null;

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "style") e.style.cssText = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }

  var CSS = [
    "#nxset-btn{position:fixed;right:18px;bottom:18px;z-index:2147483000;width:42px;height:42px;border-radius:50%;",
    "border:1px solid #d0d7de;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.15);cursor:pointer;font-size:19px;line-height:1}",
    "#nxset-btn.nxset-hasnew::after{content:'';position:absolute;top:2px;right:2px;width:11px;height:11px;border-radius:50%;",
    "background:#e5484d;border:2px solid #fff}",
    "#nxset-panel{position:fixed;right:18px;bottom:70px;z-index:2147483000;width:470px;max-height:80vh;overflow:auto;",
    "background:#fff;border:1px solid #d0d7de;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.2);",
    "font:13px/1.5 system-ui,'Segoe UI',sans-serif;color:#24292f;padding:0 0 14px}",
    "#nxset-panel h3{margin:0;padding:12px 16px 0;font-size:14px}",
    ".nxset-tabs{display:flex;gap:4px;padding:10px 16px 0;border-bottom:1px solid #eaeef2;margin-bottom:10px}",
    ".nxset-tab{padding:6px 12px;border:1px solid transparent;border-bottom:none;border-radius:7px 7px 0 0;cursor:pointer;",
    "font:inherit;background:transparent;color:#57606a;margin-bottom:-1px}",
    ".nxset-tab.on{background:#fff;border-color:#d0d7de;color:#0F789B;font-weight:600}",
    ".nxset-tab .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#e5484d;margin-left:5px;vertical-align:middle}",
    ".nxset-pane{display:none;padding:0 16px}",
    ".nxset-pane.on{display:block}",
    "#nxset-panel label{display:block;margin:9px 0 3px;color:#57606a;font-size:12px}",
    "#nxset-panel input,#nxset-panel select,#nxset-panel textarea{width:100%;box-sizing:border-box;padding:5px 7px;",
    "border:1px solid #d0d7de;border-radius:6px;font:inherit;background:#fff}",
    "#nxset-panel textarea{min-height:74px;resize:vertical}",
    ".nxset-row{display:flex;gap:8px}.nxset-row>*{flex:1}",
    ".nxset-btn{padding:6px 12px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;cursor:pointer;font:inherit}",
    ".nxset-btn.primary{background:#0F789B;border-color:#0F789B;color:#fff}",
    ".nxset-note{margin-top:10px;padding:8px;border-radius:6px;background:#f6f8fa;font-size:12px;color:#57606a;white-space:pre-wrap}",
    ".nxset-ok{color:#0a7}.nxset-bad{color:#b00}",
    ".nxset-sec{margin-top:12px;padding-top:10px;border-top:1px solid #eaeef2}",
    ".nxset-tag{display:inline-block;margin:2px 4px 0 0;padding:1px 6px;border-radius:10px;background:#eef6f9;color:#0F789B;font-size:11px}",
    ".nxset-step{display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px dashed #eaeef2}",
    ".nxset-step .nm{flex:1;font-size:12px}",
    ".nxset-badge{display:inline-block;padding:1px 6px;border-radius:9px;font-size:11px;white-space:nowrap}",
    ".b-pending{background:#f1f3f5;color:#57606a}.b-done{background:#e6f6ee;color:#0a7}",
    ".b-failed{background:#fdecec;color:#b00}.b-undone{background:#fff4e5;color:#b26a00}",
    ".b-running{background:#e7f1fb;color:#0969da}",
    ".g-auto{background:#eef6f9;color:#0F789B}.g-manual{background:#fff4e5;color:#b26a00}",
    ".nxset-mini{font-size:11px;color:#8b949e;margin-top:2px}",
    ".nxset-banner{border:1px solid #0F789B;background:#eef6f9;border-radius:8px;padding:9px 11px;margin-bottom:8px;font-size:12px;color:#0F789B}"
  ].join("");

  function show(msg, cls) {
    var n = document.getElementById("nxset-note");
    if (!n) return;
    n.className = "nxset-note " + (cls || "");
    n.textContent = msg;
  }

  function setTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll(".nxset-tab"), function (b) {
      b.classList.toggle("on", b.getAttribute("data-pane") === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".nxset-pane"), function (p) {
      p.classList.toggle("on", p.getAttribute("data-pane") === name);
    });
    if (name === "review") { lastSeenPlanId = lastPlanId; markNew(false); refreshReview(); }
  }

  function markNew(on) {
    var b = document.getElementById("nxset-btn");
    if (b) b.classList.toggle("nxset-hasnew", !!on);
    var d = document.getElementById("nxset-tab-dot");
    if (d) d.style.display = on ? "inline-block" : "none";
  }

  /* ---------- 进度浮层(思维链) ---------- */
  var progTimer = null;

  function progEl() { return document.getElementById("nxprog"); }

  function progShow() {
    var p = progEl();
    if (!p) return;
    p.style.display = "block";
    if (!progTimer) progTimer = setInterval(progTick, 800);
    progTick();
  }

  function progHide(delay) {
    if (progTimer) { clearInterval(progTimer); progTimer = null; }
    var p = progEl();
    if (!p) return;
    if (delay) setTimeout(function () { p.style.display = "none"; }, delay);
    else p.style.display = "none";
  }

  function progTick() {
    fetch("/api/progress").then(function (r) { return r.json(); }).then(function (j) {
      var p = progEl();
      if (!p) return;
      if (!j.active && j.stage !== "done") { p.style.display = "none"; return; }
      var secs = Math.round((j.elapsedMs || 0) / 1000);
      var head = document.getElementById("nxprog-head");
      var body = document.getElementById("nxprog-body");
      var think = document.getElementById("nxprog-think");
      var tools = document.getElementById("nxprog-tools");

      if (!j.active) {
        head.textContent = "✅ 完成 · 用时 " + secs + " 秒";
        body.textContent = "";
        think.textContent = "";
        tools.textContent = "";
        progHide(3500);
        return;
      }
      var kindLabel = j.kind === "author" ? "生成计划" : "回答";
      head.textContent = "⏳ " + kindLabel + "中 · " + secs + " 秒" + (j.attempts > 1 ? " · 第 " + j.attempts + " 次尝试" : "");
      body.textContent = (j.stage || "") + (j.detail ? " — " + j.detail : "");
      tools.textContent = (j.tools || []).length ? "工具:" + j.tools.map(function (t) { return t.name + (t.ok ? "" : "✗"); }).join(" → ") : "";
      var lines = (j.reasoning || []).slice(-6);
      think.textContent = lines.join("\n").slice(-900);
      think.scrollTop = think.scrollHeight;
    }).catch(function () { });
  }

  function buildProgress() {
    if (progEl()) return;
    var box = el("div", { id: "nxprog", style:
      "display:none;position:fixed;right:18px;bottom:70px;z-index:2147483000;width:420px;max-height:46vh;overflow:auto;" +
      "background:#0f1b22;color:#d7e3ea;border:1px solid #24404d;border-radius:10px;padding:10px 12px;" +
      "font:12px/1.6 ui-monospace,Consolas,monospace;box-shadow:0 8px 30px rgba(0,0,0,.35)" }, [
      el("div", { id: "nxprog-head", style: "color:#7fd4ea;font-weight:600", text: "⏳ 准备中…" }),
      el("div", { id: "nxprog-body", style: "margin-top:2px;opacity:.9" }),
      el("div", { id: "nxprog-tools", style: "margin-top:4px;color:#9fe0b0;font-size:11px;white-space:pre-wrap" }),
      el("div", { style: "margin-top:6px;padding-top:6px;border-top:1px solid #24404d;color:#8fa6b3;font-size:11px" }, [
        el("div", { text: "思考链(live):" }),
        el("pre", { id: "nxprog-think", style: "margin:2px 0 0;white-space:pre-wrap;max-height:22vh;overflow:auto;font-size:11px;color:#b9c9d3" })
      ])
    ]);
    document.body.appendChild(box);
  }

  /* ---------- 复核队列 ---------- */
  function badge(text, cls) { return el("span", { "class": "nxset-badge " + cls, text: text }); }

  function refreshReview(force) {
    var box = document.getElementById("nxset-review-list");
    if (!box) return;
    fetch("/api/review").then(function (r) { return r.json(); }).then(function (j) {
      var wsEl = document.getElementById("nxset-review-ws");
      if (wsEl) wsEl.textContent = j.reviewDir || "(未配置工作区)";

      var warn = document.getElementById("nxset-review-warn");
      if (warn) {
        if (j.workspaceMismatch) {
          warn.style.display = "block";
          warn.textContent = "⚠ NX 侧看到的工作区是 " + j.envWorkspace + ",与宿主的 " + j.workspace +
            " 不一致 —— NX 的 Review Plan 对话框会找不到计划。请运行 dc\\review-workspace-on.cmd 并重启 Designcenter。";
        } else { warn.style.display = "none"; }
      }

      var pid = j.hasPlan ? (j.plan.planId || "?") : null;
      var isNew = pid && pid !== lastSeenPlanId;
      if (pid !== lastPlanId) lastPlanId = pid;
      if (isNew) markNew(true);

      box.innerHTML = "";
      if (!j.hasPlan) {
        box.appendChild(el("div", { "class": "nxset-mini", text: "还没有计划。对 AI 说「出个计划并载入复核队列」。" }));
        return;
      }
      if (isNew) {
        box.appendChild(el("div", { "class": "nxset-banner", text: "✅ 新计划已载入:" + pid + " · " + j.steps.length + " 步" }));
      }
      box.appendChild(el("div", { "class": "nxset-mini" }, [
        el("div", { text: "计划 " + pid + " · " + j.steps.length + " 步" + (j.plan.prompt ? " · " + j.plan.prompt.slice(0, 36) : "") })
      ]));
      j.steps.forEach(function (s) {
        var nm = el("div", { "class": "nm" }, [
          el("div", { text: s.name }),
          el("div", { "class": "nxset-mini", text: s.operation + (s.note ? " · " + s.note : "") + (s.message ? " · " + s.message : "") })
        ]);
        if (s.script) {
          nm.appendChild(el("details", { style: "margin-top:4px" }, [
            el("summary", { style: "cursor:pointer;color:#0F789B;font-size:11px",
              text: "查看脚本 " + ((s.params && s.params.path) || "") + "(" + s.script.split("\n").length + " 行,执行前请审阅)" }),
            el("pre", { style: "margin:4px 0 0;padding:6px;background:#f6f8fa;border-radius:6px;overflow:auto;max-height:200px;font-size:11px", text: s.script })
          ]));
        }
        box.appendChild(el("div", { "class": "nxset-step" }, [
          badge(s.status || "pending", "b-" + (s.status || "pending")),
          nm,
          badge(s.gate || "manual", s.gate === "auto" ? "g-auto" : "g-manual")
        ]));
      });
      box.appendChild(el("div", { "class": "nxset-mini", style: "margin-top:8px", html:
        "在 Designcenter 里执行:<b>Help → NX Skill → Review Plan</b>,或按 <b>Ctrl+Alt+Shift+R</b>。" }));
    }).catch(function (e) {
      box.innerHTML = "";
      box.appendChild(el("div", { "class": "nxset-mini nxset-bad", text: "读取复核队列失败:" + e }));
    });
  }

  function authorPlan() {
    var q = document.getElementById("nxset-plan-q").value.trim();
    if (!q) { alert("先写一句需求"); return; }
    var t0 = Date.now();
    var box = document.getElementById("nxset-author-note") || (function () {
      var d = el("div", { id: "nxset-author-note", "class": "nxset-note" });
      document.getElementById("nxset-plan-q").parentNode.appendChild(d);
      return d;
    })();
    box.className = "nxset-note";
    progShow();
    var tick = setInterval(function () {
      box.textContent = "正在生成并校验计划 … 已用 " + Math.round((Date.now() - t0) / 1000) + " 秒(校验不过会自动修正重试)";
    }, 1000);
    // 先把任务交给服务端(立刻返回),再轮询状态 —— 避免长请求被浏览器掐断
    fetch("/api/plan/author", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q })
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.jobId) throw new Error(j.error || "服务端未返回任务号");
      var poll = setInterval(function () {
        fetch("/api/plan/author/status?id=" + j.jobId).then(function (r) { return r.json(); }).then(function (s) {
          if (s.state === "running") {
            box.textContent = "服务端正在生成并校验计划 … 已用 " + Math.round(s.elapsedMs / 1000) + " 秒(可关掉面板,任务会继续跑)";
            return;
          }
          clearInterval(poll); clearInterval(tick); progHide(3000);
          var res = s.result || {};
          if (res.ok) {
            box.className = "nxset-note nxset-ok";
            box.textContent = "✅ 已载入队列:计划 " + (res.planId || "") + " · " + (res.stepCount || 0) + " 步 · 第 " + res.attempt + " 次通过校验 · " + Math.round(s.elapsedMs / 1000) + " 秒\n去 Designcenter 点 NX Skill → Review Plan(或 Ctrl+Alt+Shift+R)执行。";
            lastSeenPlanId = null;
            refreshReview(true);
          } else {
            box.className = "nxset-note nxset-bad";
            box.textContent = "❌ 未能产出合法计划:" + String(res.error || "").slice(0, 600);
          }
        }).catch(function () { });
      }, 2000);
    }).catch(function (e) {
      clearInterval(tick); progHide(2000);
      box.className = "nxset-note nxset-bad";
      box.textContent = "❌ 提交任务失败:" + e;
    });
  }

  function runPlan(mode) {
    var n = document.getElementById("nxset-run-note");
    var msg = mode === "live"
      ? "在【当前打开的 NX 会话】里执行这份计划?\n\n会直接改你正在编辑的零件(当前工作零件),不新建文件、不自动保存。需要先在 DC 里点过 NX Skill → Start NX Skill Live Bridge。"
      : "自动执行队列里的计划?\n\n这会启动一个 headless NX 进程、新建零件并跑完所有步骤 —— 过程中看不到画面。";
    if (!confirm(msg)) return;
    n.textContent = mode === "live" ? "正在把步骤推进当前 NX 会话 …" : "正在把计划交给 headless NX …";
    progShow();
    fetch("/api/plan/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: mode }) })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.jobId) throw new Error(j.error || "未返回任务号");
        var poll = setInterval(function () {
          fetch("/api/plan/run/status?id=" + j.jobId).then(function (r) { return r.json(); }).then(function (s) {
            if (s.state === "running") { n.textContent = "headless NX 正在执行 … 已用 " + Math.round(s.elapsedMs / 1000) + " 秒"; return; }
            clearInterval(poll); progHide(3000);
            var res = s.result || {};
            if (res.ok) {
              n.className = "nxset-mini nxset-ok";
              n.textContent = "✅ 执行完成 · " + (res.steps || []).filter(function (x) { return x.status === "done"; }).length + " 步成功 · " +
                Math.round(s.elapsedMs / 1000) + " 秒" + (res.part ? "\n零件:" + res.part + (res.saved ? "(已保存)" : "(未保存)") : "");
            } else {
              n.className = "nxset-mini nxset-bad";
              var bad = (res.steps || []).filter(function (x) { return x.status === "failed"; });
              n.textContent = "❌ " + (res.error || (bad.length + " 步失败")) +
                (bad.length ? "\n第一步失败:" + bad[0].name + " — " + String(bad[0].message || "").slice(0, 200) : "");
            }
            refreshReview(true);
          }).catch(function () { });
        }, 2000);
      })
      .catch(function (e) { clearInterval(0); progHide(2000); n.className = "nxset-mini nxset-bad"; n.textContent = "❌ 启动失败:" + e; });
  }

  function cleanScratch() {
    var n = document.getElementById("nxset-clean-note");
    n.textContent = "正在清理 …";
    fetch("/api/cleanup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope: "all" }) })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        n.textContent = "✅ 已清理:临时目录 " + ((j.scratch && j.scratch.tempDirs) || 0) + " 个、" +
          "队列文件 " + ((j.queue && j.queue.files) || 0) + " 个,共释放 " +
          Math.round((((j.scratch && j.scratch.bytes) || 0) + ((j.queue && j.queue.bytes) || 0)) / 1024) + " KB";
        lastSeenPlanId = lastPlanId = null;
        refreshReview(true);
      })
      .catch(function (e) { n.textContent = "❌ 清理失败:" + e; });
  }

  function clearReview() {
    if (!confirm("清空复核队列(删除 plan.json 与 run.json)?")) return;
    fetch("/api/review/clear", { method: "POST" }).then(function () { lastSeenPlanId = lastPlanId = null; refreshReview(true); });
  }

  /* ---------- 模型设置 ---------- */
  function providerById(id) {
    return (state.providers || []).filter(function (p) { return p.id === id; })[0];
  }
  function fillForm(p) {
    document.getElementById("nxset-baseurl").value = p.baseUrl || "";
    document.getElementById("nxset-model").value = p.model || "";
    var k = document.getElementById("nxset-apikey");
    k.value = "";
    k.placeholder = p.hasKey ? ("已保存:" + p.apiKeyMasked + "(留空则不改)") : "未设置";
    var dl = document.getElementById("nxset-models");
    dl.innerHTML = "";
    (p.models || []).forEach(function (m) { dl.appendChild(el("option", { value: m })); });
  }
  function renderSettings() {
    var sel = document.getElementById("nxset-provider");
    sel.innerHTML = "";
    (state.providers || []).forEach(function (p) {
      sel.appendChild(el("option", { value: p.id, text: p.label + (p.id === state.activeProvider ? "  ← 当前" : "") }));
    });
    sel.value = state.activeProvider;
    fillForm(providerById(state.activeProvider) || {});
    document.getElementById("nxset-sys").value = state.systemPrompt || "";
    document.getElementById("nxset-nxroot").value = (state.nx || {}).nxSkillRoot || "";
    document.getElementById("nxset-nxinstall").value = (state.nx || {}).nxRoot || "";
    document.getElementById("nxset-nxws").value = (state.nx || {}).nxWorkspace || "";
    document.getElementById("nxset-rounds").value = (state.nx || {}).maxToolRounds || 8;
    var tools = document.getElementById("nxset-tools");
    tools.innerHTML = "";
    (state.tools || []).forEach(function (t) { tools.appendChild(el("span", { "class": "nxset-tag", text: t })); });
  }
  function loadSettings() {
    return fetch(API).then(function (r) { return r.json(); }).then(function (j) { state = j; renderSettings(); });
  }
  function payload(withKey) {
    var id = document.getElementById("nxset-provider").value;
    var p = { id: id, baseUrl: document.getElementById("nxset-baseurl").value, model: document.getElementById("nxset-model").value };
    var k = document.getElementById("nxset-apikey").value;
    if (withKey && k) p.apiKey = k;
    return {
      activeProvider: id, provider: p,
      systemPrompt: document.getElementById("nxset-sys").value,
      nx: {
        nxSkillRoot: document.getElementById("nxset-nxroot").value,
        nxRoot: document.getElementById("nxset-nxinstall").value,
        nxWorkspace: document.getElementById("nxset-nxws").value,
        maxToolRounds: Number(document.getElementById("nxset-rounds").value) || 8
      }
    };
  }
  function test() {
    show("正在测试 …");
    fetch(API + "/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload(true)) })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.ok) show("✅ 连接正常 · " + j.provider + " / " + j.model + " · " + j.ms + " ms\n回复:" + (j.reply || "(空)"), "nxset-ok");
        else show("❌ 连接失败 · " + j.provider + " / " + j.model + " · " + j.ms + " ms\n" + (j.error || "HTTP 非 200"), "nxset-bad");
      })
      .catch(function (e) { show("❌ " + e, "nxset-bad"); });
  }
  function save() {
    fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload(true)) })
      .then(function (r) { return r.json(); }).then(loadSettings)
      .then(function () { show("✅ 已保存并设为当前供应商(下一条消息即生效,无需刷新)。", "nxset-ok"); })
      .catch(function (e) { show("❌ 保存失败:" + e, "nxset-bad"); });
  }

  /* ---------- 构建 ---------- */
  function tab(name, label, withDot) {
    return el("button", { type: "button", "class": "nxset-tab", "data-pane": name, onclick: function () { setTab(name); } }, [
      el("span", { text: label }),
      withDot ? el("span", { id: "nxset-tab-dot", "class": "dot", style: "display:none" }) : null
    ]);
  }

  function build() {
    document.head.appendChild(el("style", { text: CSS }));

    var panel = el("form", { id: "nxset-panel", onsubmit: function (e) { e.preventDefault(); return false; } }, [
      el("h3", { text: "⚙ 本地宿主(非西门子官方)" }),

      el("div", { "class": "nxset-tabs" }, [
        tab("review", "复核队列 / Review Plan", true),
        tab("model", "模型"),
        tab("nxskill", "nx-skill")
      ]),

      /* --- 复核队列 --- */
      el("div", { "class": "nxset-pane on", "data-pane": "review" }, [
        el("div", { id: "nxset-review-warn", "class": "nxset-mini nxset-bad", style: "display:none;background:#fdecec;padding:6px;border-radius:6px;margin-bottom:6px" }),
        el("div", { "class": "nxset-mini", text: "工作区:" }),
        el("div", { id: "nxset-review-ws", "class": "nxset-mini", text: "…" }),
        el("div", { id: "nxset-review-list", style: "margin:6px 0 4px" }),
        el("div", { "class": "nxset-row" }, [
          el("button", { type: "button", "class": "nxset-btn primary", text: "▶ 在当前 NX 会话执行", onclick: function () { runPlan("live"); } })
        ]),
        el("div", { "class": "nxset-row", style: "margin-top:6px" }, [
          el("button", { type: "button", "class": "nxset-btn", text: "⚡ 后台新建零件执行", onclick: function () { runPlan("batch"); } })
        ]),
        el("div", { id: "nxset-run-note", "class": "nxset-mini", text: "自动执行走的是 headless NX:不用一步步点,但看不到过程。要看着做就用 NX Skill → Review Plan。" }),
        el("div", { "class": "nxset-row", style: "margin-top:6px" }, [
          el("button", { type: "button", "class": "nxset-btn", text: "载入 / 刷新", onclick: function () { lastSeenPlanId = lastPlanId; markNew(false); refreshReview(true); } }),
          el("button", { type: "button", "class": "nxset-btn", text: "清空队列", onclick: clearReview })
        ]),
        el("div", { "class": "nxset-row", style: "margin-top:6px" }, [
          el("button", { type: "button", "class": "nxset-btn", text: "清理临时残留", onclick: cleanScratch })
        ]),
        el("div", { id: "nxset-clean-note", "class": "nxset-mini", text: "Designcenter 退出时会自动清理(策略见 config.json 的 cleanupOnNxExit)。" }),
        el("div", { "class": "nxset-mini", style: "margin-top:6px", text: "AI 出完计划会自动载入到这里;执行始终由你在 NX 里点。" }),
        el("div", { "class": "nxset-sec" }),
        el("label", { text: "让 AI 生成计划并直接载入(推荐)" }),
        el("input", { id: "nxset-plan-q", placeholder: "例如:建模一个法兰,含螺栓孔与密封槽" }),
        el("div", { "class": "nxset-row", style: "margin-top:6px" }, [
          el("button", { type: "button", "class": "nxset-btn primary", text: "生成计划并载入", onclick: authorPlan })
        ]),
        el("div", { "class": "nxset-mini", text: "一次请求直接产出结构化计划 + NXOpen 脚本,服务端校验 API 名后写入队列;通常 1-3 分钟。" })
      ]),

      /* --- 模型 --- */
      el("div", { "class": "nxset-pane", "data-pane": "model" }, [
        el("label", { text: "大模型供应商" }),
        el("select", { id: "nxset-provider", onchange: function () { fillForm(providerById(this.value) || {}); } }),
        el("label", { text: "Base URL(OpenAI 兼容)" }),
        el("input", { id: "nxset-baseurl", placeholder: "https://…/v1" }),
        el("label", { text: "API Key" }),
        el("input", { id: "nxset-apikey", type: "password", autocomplete: "new-password" }),
        el("label", { text: "模型" }),
        el("input", { id: "nxset-model", list: "nxset-models" }),
        el("datalist", { id: "nxset-models" }),
        el("div", { "class": "nxset-row", style: "margin-top:12px" }, [
          el("button", { type: "button", "class": "nxset-btn", text: "测试连接", onclick: test }),
          el("button", { type: "button", "class": "nxset-btn primary", text: "保存并启用", onclick: save })
        ]),
        el("div", { id: "nxset-note", "class": "nxset-note", text: "选好供应商后点「测试连接」确认再保存。" }),
        el("div", { "class": "nxset-sec" }, [
          el("label", { text: "系统提示词" }),
          el("textarea", { id: "nxset-sys" })
        ])
      ]),

      /* --- nx-skill --- */
      el("div", { "class": "nxset-pane", "data-pane": "nxskill" }, [
        el("label", { text: "nx-skill 根目录" }),
        el("input", { id: "nxset-nxroot" }),
        el("label", { text: "NX 安装根目录(钉死,避免遗留环境变量污染)" }),
        el("input", { id: "nxset-nxinstall" }),
        el("label", { text: "nx-skill 工作区(与 NXMCP 隔离,须与 NX 侧一致)" }),
        el("input", { id: "nxset-nxws" }),
        el("label", { text: "最大工具调用轮数" }),
        el("input", { id: "nxset-rounds", type: "number", min: "1", max: "20" }),
        el("label", { text: "已接入工具" }),
        el("div", { id: "nxset-tools" })
      ])
    ]);

    var btn = el("button", { type: "button", id: "nxset-btn", title: "本地宿主设置", text: "⚙", onclick: function () {
      var open = panel.style.display !== "block";
      panel.style.display = open ? "block" : "none";
      if (open) { markNew(false); lastSeenPlanId = lastPlanId; refreshReview(); }
    } });

    document.body.appendChild(btn);
    document.body.appendChild(panel);
    buildProgress();

    // 聊天页每提一个问题,host-stub 会派发这个事件 → 亮出进度浮层
    window.addEventListener("plchat-local-busy", function (e) {
      if (e.detail && e.detail.on) progShow(); else progHide(2500);
    });

    // 后台轮询:计划一变化就打红点(面板没开也能发现)
    if (!pollTimer) pollTimer = setInterval(function () { refreshReview(); }, 8000);

    loadSettings().then(function () { refreshReview(); })
      .catch(function (e) { show("读取设置失败:" + e, "nxset-bad"); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})();
