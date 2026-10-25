// Show/hide the password.
document.querySelectorAll(".toggle").forEach(function (button) {
  button.addEventListener("click", function () {
    var input = document.getElementById(button.dataset.target);
    if (!input) return;

    var show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Hide" : "Show";
    button.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
});
