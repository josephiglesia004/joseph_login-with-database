// Confirm bago mag-submit ng form na may data-confirm.
document.querySelectorAll("form[data-confirm]").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
});

// Copy-to-clipboard buttons.
document.querySelectorAll("[data-copy]").forEach(function (button) {
  button.addEventListener("click", function () {
    var text = button.dataset.copy || "";
    var done = function () {
      var original = button.dataset.label || button.textContent;
      button.dataset.label = original;
      button.textContent = "Copied!";
      button.classList.add("copied");
      setTimeout(function () {
        button.textContent = original;
        button.classList.remove("copied");
      }, 1400);
    };

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(function () {});
      return;
    }

    var area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      done();
    } finally {
      document.body.removeChild(area);
    }
  });
});
