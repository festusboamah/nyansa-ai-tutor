(function () {
    "use strict";

    var QUEUE_KEY = "nyansa_offline_quiz_queue";
    var NOTICES_KEY = "nyansa_notices";

    function readCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : "";
    }

    function readQueue() {
        try {
            return JSON.parse(localStorage.getItem(QUEUE_KEY)) || [];
        } catch (e) {
            return [];
        }
    }

    function writeQueue(queue) {
        localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
    }

    function pushNotice(message, tone) {
        var notices = [];
        try {
            notices = JSON.parse(localStorage.getItem(NOTICES_KEY)) || [];
        } catch (e) {
            notices = [];
        }
        notices.push({ message: message, tone: tone || "success" });
        localStorage.setItem(NOTICES_KEY, JSON.stringify(notices));
    }

    function renderNotices() {
        var notices = [];
        try {
            notices = JSON.parse(localStorage.getItem(NOTICES_KEY)) || [];
        } catch (e) {
            notices = [];
        }
        if (!notices.length) {
            return;
        }
        localStorage.removeItem(NOTICES_KEY);

        var mount = document.getElementById("offline-notices");
        if (!mount) {
            return;
        }
        notices.forEach(function (notice) {
            var div = document.createElement("div");
            div.className = "alert alert-" + (notice.tone === "error" ? "error" : "success");
            div.textContent = notice.message;
            mount.appendChild(div);
        });
    }

    function enqueue(quizId, quizTitle, formData) {
        var answers = {};
        formData.forEach(function (value, key) {
            answers[key] = value;
        });
        var queue = readQueue();
        queue.push({
            quizId: quizId,
            quizTitle: quizTitle,
            answers: answers,
            queuedAt: new Date().toISOString(),
        });
        writeQueue(queue);
    }

    function replayQueue() {
        var queue = readQueue();
        if (!queue.length) {
            return;
        }

        var remaining = [];
        var pending = queue.map(function (item) {
            var body = new URLSearchParams(item.answers);
            return fetch("/quizzes/" + item.quizId + "/take/", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": readCsrfToken(),
                },
                body: body.toString(),
            })
                .then(function (response) {
                    var finalUrl = response.url || "";
                    if (finalUrl.indexOf("/quizzes/result/") !== -1) {
                        pushNotice("Your offline answers for \"" + item.quizTitle + "\" were submitted.", "success");
                        return;
                    }
                    if (finalUrl.indexOf("/start/") !== -1) {
                        pushNotice(
                            "Your queued answers for \"" + item.quizTitle + "\" could not be submitted — " +
                            "the deadline or attempt limit was reached before you reconnected. Please check with your teacher.",
                            "error"
                        );
                        return;
                    }
                    remaining.push(item);
                })
                .catch(function () {
                    remaining.push(item);
                });
        });

        Promise.all(pending).then(function () {
            writeQueue(remaining);
        });
    }

    window.addEventListener("online", replayQueue);
    document.addEventListener("DOMContentLoaded", function () {
        renderNotices();
        if (navigator.onLine) {
            replayQueue();
        }
    });

    window.NyansaOfflineQueue = {
        enqueue: enqueue,
        replayQueue: replayQueue,
    };
})();
