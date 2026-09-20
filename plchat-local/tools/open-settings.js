(function () {
  var b = document.getElementById("nxset-btn");
  if (!b) return "no button";
  b.click();
  var tabs = Array.prototype.map.call(document.querySelectorAll(".nxset-tab"), function (t) { return t.textContent.trim(); });
  var panes = Array.prototype.map.call(document.querySelectorAll(".nxset-pane"), function (p) { return p.getAttribute("data-pane") + (p.classList.contains("on") ? "(on)" : ""); });
  return "tabs=[" + tabs.join(" | ") + "] panes=[" + panes.join(" | ") + "]";
})()