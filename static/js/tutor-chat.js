(function () {
    "use strict";

    // Inline icon markup copied verbatim from accounts/templatetags/icons.py's
    // _ICONS dict ("user", "sparkles") - can't call the Django {% icon %} tag
    // from JS, and this keeps JS-appended bubbles identical to server-rendered
    // ones. If icons.py's shapes ever change, update these two strings too.
    var ICON_WRAPPER = '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" ' +
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{inner}</svg>';
    var USER_ICON = ICON_WRAPPER.replace("{inner}",
        '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8"/>');
    var SPARKLES_ICON = ICON_WRAPPER.replace("{inner}",
        '<path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/>' +
        '<path d="M19 14l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z"/>');

    function readCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : "";
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.querySelector(".tutor-chat-form");
        if (!form) return;

        var history = document.querySelector(".qa-history");
        var textarea = form.querySelector("textarea[name='message']");
        var submitButton = form.querySelector('button[type="submit"]');
        if (!history || !textarea || !submitButton) return;

        var emptyNotice = history.querySelector("p");

        function appendItem(innerHtml) {
            var item = document.createElement("div");
            item.className = "qa-item";
            item.innerHTML = innerHtml;
            history.appendChild(item);
            item.scrollIntoView({ behavior: "smooth", block: "end" });
            return item;
        }

        function setBusy(busy) {
            textarea.disabled = busy;
            submitButton.disabled = busy;
            submitButton.textContent = busy ? "Working..." : "Send";
        }

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var text = textarea.value.trim();
            if (!text) return;

            if (emptyNotice) {
                emptyNotice.remove();
                emptyNotice = null;
            }

            appendItem('<div class="qa-question">' + USER_ICON + ' You: ' + escapeHtml(text) + '</div>');
            var thinkingItem = appendItem(
                '<div class="qa-answer">' + SPARKLES_ICON + ' <span class="thinking-dots" aria-live="polite" aria-label="Tutor is thinking">' +
                '<span></span><span></span><span></span></span></div>'
            );
            textarea.value = "";
            setBusy(true);

            fetch(window.location.href, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": readCsrfToken(),
                },
                body: new URLSearchParams({ message: text }),
            })
                .then(function (response) {
                    if (!response.ok) throw new Error("Tutor request failed");
                    return response.json();
                })
                .then(function (data) {
                    thinkingItem.innerHTML = '<div class="qa-answer">' + SPARKLES_ICON + ' Tutor: ' + escapeHtml(data.content) + '</div>';
                })
                .catch(function () {
                    thinkingItem.innerHTML = '<div class="qa-answer">' + SPARKLES_ICON +
                        ' Sorry, something went wrong sending that. Please try again.</div>';
                })
                .finally(function () {
                    setBusy(false);
                    textarea.focus();
                });
        });
    });
})();
