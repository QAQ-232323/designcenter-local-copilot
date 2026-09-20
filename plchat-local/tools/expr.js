(function () {
  var el = document.querySelector('des-plchat-acc');
  return JSON.stringify({
    text: (el && el.innerText || '').replace(/\n+/g, ' | ').slice(0, 700)
  }, null, 1);
})()