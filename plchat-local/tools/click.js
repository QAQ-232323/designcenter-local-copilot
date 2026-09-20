(function () {
  var q = "What command should I use to mirror a body?";
  var all = document.querySelectorAll("*");
  var best = null;
  for (var i = 0; i < all.length; i++) {
    var t = (all[i].textContent || "").trim();
    if (t === q && !all[i].querySelector("*")) { best = all[i]; break; }
  }
  if (!best) { for (var j = 0; j < all.length; j++) { var t2 = (all[j].textContent || "").trim(); if (t2 === q) { best = all[j]; break; } } }
  if (!best) return "question node not found";
  best.click();
  return "clicked: " + best.tagName + "." + best.className;
})()