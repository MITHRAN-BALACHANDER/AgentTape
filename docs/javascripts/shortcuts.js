// Cmd/Ctrl + K opens the search box, and the keyboard hint shows the
// platform-correct label. Guarded so navigation.instant re-runs don't
// register the keydown listener more than once.
(function () {
  var isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent);
  document.documentElement.style.setProperty("--at-kbd", isMac ? '"⌘ K"' : '"Ctrl K"');

  if (window.__atShortcutsBound) {
    return;
  }
  window.__atShortcutsBound = true;

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && (event.key === "k" || event.key === "K")) {
      var toggle = document.getElementById("__search");
      if (!toggle) {
        return;
      }
      event.preventDefault();
      toggle.checked = true;
      toggle.dispatchEvent(new Event("change"));
      var input = document.querySelector(".md-search__input");
      if (input) {
        setTimeout(function () {
          input.focus();
        }, 10);
      }
    }
  });
})();
