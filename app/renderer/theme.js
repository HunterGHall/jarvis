// Runs before the page is drawn, so the saved theme is there from the first frame (no flash of the other one).
(function () {
  var theme = "light";
  try {
    theme = localStorage.getItem("jarvis-theme") === "dark" ? "dark" : "light";
  } catch (error) {}
  document.documentElement.dataset.theme = theme;
})();
