(function () {
    "use strict";

    function readCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : "";
    }

    function showError(form, message) {
        var existing = form.querySelector(".form-error-summary");
        if (existing) existing.remove();
        var summary = document.createElement("div");
        summary.className = "form-error-summary";
        summary.setAttribute("role", "alert");
        summary.setAttribute("tabindex", "-1");
        var heading = document.createElement("strong");
        heading.textContent = message;
        summary.appendChild(heading);
        form.insertBefore(summary, form.firstChild);
        window.setTimeout(function () { summary.focus(); }, 0);
    }

    document.addEventListener("DOMContentLoaded", function () {
        Array.from(document.querySelectorAll(".ai-generation-form")).forEach(function (form) {
            var submitButton = form.querySelector('button[type="submit"]');
            if (!submitButton) return;

            form.addEventListener("submit", function (event) {
                if (!form.checkValidity()) return;
                event.preventDefault();

                var originalLabel = submitButton.textContent;
                submitButton.disabled = true;
                submitButton.setAttribute("aria-busy", "true");
                submitButton.innerHTML = 'Generating<span class="thinking-dots thinking-dots-on-primary" aria-hidden="true"><span></span><span></span><span></span></span>';

                fetch(form.action || window.location.href, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "X-CSRFToken": readCsrfToken(),
                    },
                    body: new FormData(form),
                })
                    .then(function (response) {
                        return response.json().then(function (data) {
                            return { ok: response.ok, data: data };
                        });
                    })
                    .then(function (result) {
                        if (result.data && result.data.redirect_to) {
                            window.location.href = result.data.redirect_to;
                            return;
                        }
                        var message = (result.data && result.data.error) || "Something went wrong. Please try again.";
                        showError(form, message);
                        submitButton.disabled = false;
                        submitButton.removeAttribute("aria-busy");
                        submitButton.textContent = originalLabel;
                    })
                    .catch(function () {
                        showError(form, "Something went wrong. Please check your connection and try again.");
                        submitButton.disabled = false;
                        submitButton.removeAttribute("aria-busy");
                        submitButton.textContent = originalLabel;
                    });
            });
        });
    });
})();
