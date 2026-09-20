/* des-plchat-acc-local.js -----------------------------------------------
 * des-plchat-acc-loader-v2.js 的本地等价物：
 * 加载随 Designcenter 一起的 Copilot 前端 (plchat_v2) 的本地副本。
 * 原版 loader 会从西门子 CDN 拉 component-bundle-v2.js 并按 SRI 校验，
 * 这里改成同顺序加载本地文件，离线可用、不受 CDN 抽风影响。
 * ---------------------------------------------------------------------- */
(function () {
  var BASE = "/plchat_v2/static/";
  window._plchatVersion = "v2";
  window.plchat_v2ModuleUrl = new URL("/plchat_v2/", window.location.href);

  var css = document.createElement("link");
  css.rel = "stylesheet";
  css.type = "text/css";
  css.href = BASE + "css/8.f48c9386.css";
  document.head.appendChild(css);

  var FILES = [
    "js/runtime~main.56cd68ec.js",
    "js/dynamic-table.f49084b5.js",
    "js/components.84c3a360.js",
    "js/dynamic-plchat.65732d65.js",
    "js/dynamic-config.650aebd1.js",
    "js/dynamic-command.dfe8be79.js",
    "js/dynamic-declarativeui.2bebe43e.js",
    "js/8.ac79b2ef.js",
    "js/main.9cdf9dc5.js"
  ];
  FILES.forEach(function (f) {
    var s = document.createElement("script");
    s.src = BASE + f;
    s.onerror = function () { console.error("[plchat-local] chunk 加载失败 " + f); };
    document.head.appendChild(s);
  });
})();
