(function () {
  window.dispatchEvent(new CustomEvent("plchat-local-busy", { detail: { on: true } }));
  return "busy event dispatched";
})()