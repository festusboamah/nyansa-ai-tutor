(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var forms = Array.from(document.querySelectorAll("form:not(.inline-form)"));

        forms.forEach(function (form) {
            if (form.closest(".auth-panel")) return;

            Array.from(form.querySelectorAll("input, select, textarea")).forEach(function (field) {
                if (field.type === "hidden") return;
                var group = field.closest("p");
                if (!group) return;
                group.classList.add("field-group");

                function updateState() {
                    group.classList.toggle("has-value", field.type === "checkbox" || field.type === "radio" ? field.checked : Boolean(field.value));
                }

                field.addEventListener("focus", function () { group.classList.add("is-focused"); });
                field.addEventListener("blur", function () { group.classList.remove("is-focused"); updateState(); });
                field.addEventListener("change", updateState);
                updateState();
            });

            var errors = Array.from(form.querySelectorAll(".errorlist li"));
            if (errors.length && !form.querySelector(".form-error-summary")) {
                var summary = document.createElement("div");
                summary.className = "form-error-summary";
                summary.setAttribute("role", "alert");
                summary.setAttribute("tabindex", "-1");
                var heading = document.createElement("strong");
                heading.textContent = errors.length === 1 ? "Please fix the highlighted problem" : "Please fix the " + errors.length + " highlighted problems";
                summary.appendChild(heading);
                form.insertBefore(summary, form.firstChild);
                window.setTimeout(function () { summary.focus(); }, 0);
            }

            form.addEventListener("submit", function () {
                if (!form.checkValidity()) return;
                var submit = form.querySelector('button[type="submit"], input[type="submit"]');
                if (!submit || submit.dataset.submitting === "true") return;
                submit.dataset.submitting = "true";
                submit.classList.add("is-submitting");
                submit.setAttribute("aria-busy", "true");
                if (submit.tagName === "BUTTON") {
                    submit.dataset.originalLabel = submit.textContent;
                    submit.textContent = "Working...";
                }
            });
        });

        Array.from(document.querySelectorAll('input[type="file"]')).forEach(function (input) {
            input.addEventListener("change", function () {
                var group = input.closest("p, .field-group");
                if (!group) return;
                group.dataset.fileName = input.files && input.files.length ? input.files[0].name : "";
            });
        });
    });
})();
