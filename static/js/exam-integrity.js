(function () {
    "use strict";

    function readCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : "";
    }

    function postForm(url, fields) {
        var formData = new FormData();
        Object.keys(fields).forEach(function (key) {
            formData.append(key, fields[key]);
        });
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": readCsrfToken() },
            body: formData,
        }).catch(function () {
            // Best-effort logging - a failed integrity ping shouldn't disrupt the exam.
        });
    }

    function requestFullscreen(el) {
        var request = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
        if (!request) {
            return Promise.resolve();
        }
        try {
            return request.call(el) || Promise.resolve();
        } catch (e) {
            return Promise.resolve();
        }
    }

    function isFullscreen() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement);
    }

    function init(config) {
        var eventUrl = config.eventUrl;
        var snapshotUrl = config.snapshotUrl;
        var requireWebcam = !!config.requireWebcam;
        var snapshotIntervalMs = (config.snapshotIntervalSeconds || 90) * 1000;
        var warningCountEl = document.getElementById("integrity-warning-count");
        var warningBoxEl = document.getElementById("integrity-warning-box");
        var warningCount = 0;

        function bumpWarning() {
            warningCount++;
            if (warningCountEl) {
                warningCountEl.textContent = String(warningCount);
            }
            if (warningBoxEl) {
                warningBoxEl.hidden = false;
            }
        }

        function logEvent(eventType, detail) {
            bumpWarning();
            postForm(eventUrl, { event_type: eventType, detail: detail || "" });
        }

        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                logEvent("TAB_HIDDEN", "");
            }
        });

        window.addEventListener("blur", function () {
            logEvent("BLUR", "");
        });

        document.addEventListener("fullscreenchange", function () {
            if (!isFullscreen()) {
                logEvent("FULLSCREEN_EXIT", "");
            }
        });

        document.addEventListener("contextmenu", function (e) { e.preventDefault(); });
        document.addEventListener("copy", function (e) { e.preventDefault(); });
        document.addEventListener("paste", function (e) { e.preventDefault(); });

        var fullscreenGate = document.getElementById("fullscreen-gate");
        var examContent = document.getElementById("exam-content");
        var enterButton = document.getElementById("enter-fullscreen-btn");

        function revealExam() {
            if (fullscreenGate) fullscreenGate.hidden = true;
            if (examContent) examContent.hidden = false;
            startWebcamIfNeeded();
        }

        if (enterButton) {
            enterButton.addEventListener("click", function () {
                requestFullscreen(document.documentElement).then(revealExam);
            });
        } else {
            revealExam();
        }

        function startWebcamIfNeeded() {
            if (!requireWebcam) {
                return;
            }
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                logEvent("CAMERA_ERROR", "Camera access is not supported in this browser.");
                return;
            }

            var video = document.createElement("video");
            video.autoplay = true;
            video.muted = true;
            video.setAttribute("playsinline", "");
            video.style.display = "none";
            document.body.appendChild(video);

            navigator.mediaDevices.getUserMedia({ video: true })
                .then(function (stream) {
                    video.srcObject = stream;

                    function capture(trigger) {
                        if (!video.videoWidth) {
                            return;
                        }
                        var canvas = document.createElement("canvas");
                        canvas.width = 320;
                        canvas.height = Math.round(320 * video.videoHeight / video.videoWidth) || 240;
                        var ctx = canvas.getContext("2d");
                        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                        canvas.toBlob(function (blob) {
                            if (!blob) {
                                return;
                            }
                            var formData = new FormData();
                            formData.append("image", blob, "snapshot.jpg");
                            formData.append("trigger", trigger);
                            fetch(snapshotUrl, {
                                method: "POST",
                                credentials: "same-origin",
                                headers: { "X-CSRFToken": readCsrfToken() },
                                body: formData,
                            }).catch(function () {});
                        }, "image/jpeg", 0.6);
                    }

                    video.addEventListener("loadedmetadata", function () {
                        capture("ATTEMPT_START");
                    });
                    setInterval(function () { capture("INTERVAL"); }, snapshotIntervalMs);
                    document.addEventListener("visibilitychange", function () {
                        if (document.hidden) capture("TAB_SWITCH");
                    });
                    window.addEventListener("blur", function () { capture("BLUR"); });
                })
                .catch(function () {
                    logEvent("CAMERA_DENIED", "");
                });
        }
    }

    window.NyansaExamIntegrity = { init: init };
})();
