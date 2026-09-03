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

(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var carousel = document.querySelector("[data-auth-carousel]");
        var dotsHost = document.querySelector("[data-auth-dots]");
        if (!carousel || !dotsHost) return;

        var slides = Array.from(carousel.querySelectorAll(".auth-tip"));
        var current = 0;
        var timer = null;
        var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        slides.forEach(function (slide, index) {
            var button = document.createElement("button");
            button.type = "button";
            button.setAttribute("aria-label", "Show learning tip " + (index + 1));
            if (index === 0) {
                button.classList.add("is-active");
                button.setAttribute("aria-current", "true");
            }
            button.addEventListener("click", function () { show(index); restart(); });
            dotsHost.appendChild(button);
        });

        var dots = Array.from(dotsHost.querySelectorAll("button"));

        function show(index) {
            slides[current].classList.remove("is-active");
            dots[current].classList.remove("is-active");
            dots[current].removeAttribute("aria-current");
            current = (index + slides.length) % slides.length;
            slides[current].classList.add("is-active");
            dots[current].classList.add("is-active");
            dots[current].setAttribute("aria-current", "true");
        }

        function restart() {
            if (reducedMotion) return;
            if (timer) window.clearInterval(timer);
            timer = window.setInterval(function () { show(current + 1); }, 5200);
        }

        carousel.addEventListener("mouseenter", function () { if (timer) window.clearInterval(timer); });
        carousel.addEventListener("mouseleave", restart);
        carousel.addEventListener("focusin", function () { if (timer) window.clearInterval(timer); });
        carousel.addEventListener("focusout", restart);
        restart();
    });
})();

// Landing-page hero headline carousel - same shape as the auth-tip
// carousel above (dots built from the slide list, autoplay that pauses on
// hover/focus, no rotation at all under prefers-reduced-motion).
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var carousel = document.querySelector("[data-headline-carousel]");
        var dotsHost = document.querySelector("[data-headline-dots]");
        if (!carousel || !dotsHost) return;

        var slides = Array.from(carousel.querySelectorAll(".hero-headline-slide"));
        if (slides.length < 2) return;
        var current = 0;
        var timer = null;
        var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        slides.forEach(function (slide, index) {
            var button = document.createElement("button");
            button.type = "button";
            button.setAttribute("aria-label", "Show headline " + (index + 1) + " of " + slides.length);
            if (index === 0) {
                button.classList.add("is-active");
                button.setAttribute("aria-current", "true");
            }
            button.addEventListener("click", function () { show(index); restart(); });
            dotsHost.appendChild(button);
        });

        var dots = Array.from(dotsHost.querySelectorAll("button"));

        function show(index) {
            slides[current].classList.remove("is-active");
            dots[current].classList.remove("is-active");
            dots[current].removeAttribute("aria-current");
            current = (index + slides.length) % slides.length;
            slides[current].classList.add("is-active");
            dots[current].classList.add("is-active");
            dots[current].setAttribute("aria-current", "true");
        }

        function restart() {
            if (reducedMotion) return;
            if (timer) window.clearInterval(timer);
            timer = window.setInterval(function () { show(current + 1); }, 4200);
        }

        carousel.addEventListener("mouseenter", function () { if (timer) window.clearInterval(timer); });
        carousel.addEventListener("mouseleave", restart);
        carousel.addEventListener("focusin", function () { if (timer) window.clearInterval(timer); });
        carousel.addEventListener("focusout", restart);
        restart();
    });
})();
