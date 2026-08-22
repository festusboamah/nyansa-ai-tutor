(function () {
    "use strict";

    var STORAGE_KEY = "nyansa_low_data";

    function isOn() {
        return localStorage.getItem(STORAGE_KEY) === "on";
    }

    function apply() {
        document.body.dataset.lowData = isOn() ? "on" : "off";
        var toggle = document.getElementById("low-data-toggle");
        if (toggle) {
            toggle.textContent = "Low-data mode: " + (isOn() ? "On" : "Off");
        }
    }

    function toggle() {
        localStorage.setItem(STORAGE_KEY, isOn() ? "off" : "on");
        apply();
    }

    document.addEventListener("DOMContentLoaded", function () {
        apply();
        var toggle_el = document.getElementById("low-data-toggle");
        if (toggle_el) {
            toggle_el.addEventListener("click", function (event) {
                event.preventDefault();
                toggle();
            });
        }
    });
})();
