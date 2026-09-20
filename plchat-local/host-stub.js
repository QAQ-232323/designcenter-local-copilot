/* host-stub.js ------------------------------------------------------------
 * 替代 Designcenter 的 WebView2 原生桥 (window.external.splmHostMethod /
 * globalhostedInfo.CallHost)，让随软件安装的内置 Copilot 页面
 * (UGII/copilot/plchat/PLChat.html) 能在普通浏览器里跑起来。
 *
 * 会话协议与 NX 侧 Copilot_UI_* 完全一致：
 *   InitPLChat -> { scripts:[{src,SRI}], icebreakerQuestionList:[],
 *                   plchatElement:"{...}", enableCustomBackend, enableCustomTheme }
 *   GetAnswer  -> { data: { answer: "<html>" } }   (自定义后端路径)
 * ---------------------------------------------------------------------- */
(function () {
  var CFG = window.__PLCHAT_LOCAL_CONFIG__ || {};
  var LOADER = CFG.loaderUrl || "/des-plchat-acc-local.js";   // 置空并设 CFG.loaderUrl 可切回西门子 CDN
  var LOADER_SRI = CFG.loaderSri || "";
  var BACKEND = CFG.backendUrl || "/api/ask";
  var PRODUCT = "NX_X";
  var VERSION = CFG.version || "2606.1700";

  var ICEBREAKERS = CFG.icebreakers || [
    "What command should I use to mirror a body?",
    "How do I analyze defective facets?",
    "What is the syntax for defining an expression?",
    "Can you write a journal to export all drawings to PDF?",
    "How do I measure the minimum distance between two bodies?"
  ];

  function log() {
    var a = Array.prototype.slice.call(arguments);
    a.unshift("[plchat-host]");
    console.log.apply(console, a);
  }

  function plchatElementAttrs() {
    return JSON.stringify({
      "id": "nx_plchat",
      "color-theme": CFG.colorTheme || "light",
      "locale": CFG.locale || "en_US",
      "plservice-identifier": PRODUCT,
      "plservice-version": VERSION,
      "display-plchat-title": true,
      "display-close-chat": false,
      "display-like-dislike-actions": true,
      "display-devplay": false,
      "support-command-context": false,
      "enable-agent-mode": false,
      "enable-streaming": true,   // 官方默认就是 true
      "enable-chat-history": true,
      "request-timeout-duration": 120,
      "initial-questions": JSON.stringify(ICEBREAKERS.map(function (q) { return { question: q }; }))
    });
  }

  function busy(on, question) {
    try {
      window.dispatchEvent(new CustomEvent("plchat-local-busy", { detail: { on: !!on, question: question || "" } }));
    } catch (e) { }
  }

  function answerSync(question, cb) {
    busy(true, question);
    fetch(BACKEND, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, product: { identifier: PRODUCT, version: VERSION } })
    }).then(function (r) { return r.json(); })
      .then(function (j) {
        var answer = (j && j.data && j.data.answer) || (j && j.answer) || "<p>(no answer)</p>";
        cb(JSON.stringify({ data: { answer: answer } }));
      })
      .catch(function (e) {
        cb(JSON.stringify({ data: { answer: "<p>本地后端调用失败: " + String(e) + "</p>" } }));
      })
      .then(function () { busy(false); });
  }

  function hostCallHost(serviceDesc, payloadString, callback) {
    var payload = {};
    try { payload = JSON.parse(payloadString); } catch (e) { }
    var method = payload.Method;
    var data = payload.MethodData || {};
    log("CallHost", method);

    if (method === "InitPLChat") {
      var scripts = [{ src: LOADER }];
      if (LOADER_SRI) { scripts[0].SRI = LOADER_SRI; }
      callback(JSON.stringify({
        scripts: scripts,
        icebreakerQuestionList: ICEBREAKERS,
        plchatElement: plchatElementAttrs(),
        enableCustomBackend: true,
        enableCustomTheme: false
      }));
      return;
    }
    if (method === "GetAnswer") { answerSync(data.question || "", callback); return; }
    if (method === "Command") {
      callback(JSON.stringify({ revealed: true, noPartState: false, tooltip: "" }));
      return;
    }
    if (method === "PLChat-CommandContextImage") { callback(JSON.stringify({ commandsImagesArr: [] })); return; }
    callback(JSON.stringify({}));
  }

  function hostCallHostEvent(serviceDesc, payloadString) {
    try { log("CallHostEvent", JSON.parse(payloadString).Method); } catch (e) { log("CallHostEvent", payloadString); }
    return "";
  }

  function takeover() {
    if (!window.globalhostedInfo) { console.error("[plchat-host] globalhostedInfo 未定义(host-stub 必须放在 plchat.js 之后)"); return; }
    var inNX = !!(window.chrome && window.chrome.webview);
    if (inNX && CFG.useOfficialHostInNX) {
      log("检测到 Designcenter WebView2 宿主,按配置让位给官方宿主桥");
      return;
    }
    window.globalhostedInfo.async = true;
    window.globalhostedInfo.CallHost = hostCallHost;
    window.globalhostedInfo.CallHostEvent = hostCallHostEvent;

    // Init 包一层"只跑一次"：WebView2 分支里 hostInterop_async 可能已经调过它
    var origInit = window.globalhostedInfo.Init;
    var inited = false;
    window.globalhostedInfo.Init = function () {
      if (inited) { log("Init 已被调用过,跳过重复初始化"); return; }
      inited = true;
      return origInit.apply(this, arguments);
    };
    log("宿主桥已接管" + (inNX ? "（Designcenter WebView2 内，走本地链路）" : "") + ",等待 DOM 就绪后触发 Init()");

    var kick = function () {
      try { window.globalhostedInfo.Init(); } catch (e) { console.error("[plchat-host] Init 失败", e); }
    };
    // 必须等 body 存在（plchat.js 的 addScript 会往 body 里插脚本）
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { setTimeout(kick, 0); });
    else setTimeout(kick, 0);
  }

  // 同步接管：必须在 hostInterop_async.js 的 DOMContentLoaded 握手之前完成，
  // 否则官方宿主桥会先被调用。因此 host-stub.js 必须放在 plchat.js 之后加载。
  takeover();
})();
