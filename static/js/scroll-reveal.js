(function () {
    "use strict";

    // Progressive enhancement only: elements marked `.reveal` are fully
    // visible without this script. If IntersectionObserver is available and
    // the visitor hasn't asked for reduced motion, arm a fade-up entrance.
    if (!("IntersectionObserver" in window)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    document.addEventListener("DOMContentLoaded", function () {
        var targets = document.querySelectorAll(".reveal");
        if (!targets.length) return;

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("in-view");
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12 });

        targets.forEach(function (el, index) {
            el.classList.add("reveal-armed");
            el.style.transitionDelay = Math.min(index * 60, 300) + "ms";
            observer.observe(el);
        });
    });
})();
