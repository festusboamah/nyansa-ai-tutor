(() => {
    document.querySelectorAll('.sidebar-nav a').forEach((link) => {
        if (new URL(link.href, window.location.href).pathname === window.location.pathname) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'page');
        }
    });
    // Sidebar group expand/collapse (admin's "Academics" / "School Operations" sections).
    document.querySelectorAll(".sidebar-group-toggle").forEach((toggle) => {
        toggle.setAttribute("aria-expanded", toggle.closest(".sidebar-group")?.classList.contains("open") ? "true" : "false");
        toggle.addEventListener("click", () => {
            const group = toggle.closest(".sidebar-group");
            if (group) {
                group.classList.toggle("open");
                toggle.setAttribute("aria-expanded", String(group.classList.contains("open")));
            }
        });
    });

    // Auto-expand a group that contains the current page, so the active link is visible.
    document.querySelectorAll(".sidebar-group").forEach((group) => {
        if (group.querySelector(".sidebar-link.active")) {
            group.classList.add("open");
            group.querySelector('.sidebar-group-toggle')?.setAttribute('aria-expanded', 'true');
        }
    });

    // Mobile off-canvas sidebar drawer.
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const sidebarBackdrop = document.getElementById("sidebar-backdrop");
    const sidebar = document.getElementById("sidebar");
    const main = document.querySelector(".app-main");
    const mobile = window.matchMedia("(max-width: 900px)");

    const closeSidebar = (restoreFocus = true) => {
        const wasOpen = document.body.classList.contains("sidebar-open");
        document.body.classList.remove("sidebar-open");
        if (main) main.inert = false;
        if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", "false");
        if (wasOpen && restoreFocus && mobile.matches) sidebarToggle?.focus();
    };

    const openSidebar = () => {
        document.body.classList.add("sidebar-open");
        if (main && mobile.matches) main.inert = true;
        if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", "true");
        sidebar?.querySelector('a[href], button')?.focus();
    };

    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", () => {
            if (document.body.classList.contains("sidebar-open")) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener("click", closeSidebar);
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeSidebar();
        if (event.key === "Tab" && mobile.matches && document.body.classList.contains("sidebar-open") && sidebar) {
            const focusable = [sidebarToggle, ...sidebar.querySelectorAll('a[href],button,input,select,[tabindex="0"]')].filter(el => el && !el.disabled && el.getClientRects().length);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
    });
    mobile.addEventListener('change', () => { if (!mobile.matches) closeSidebar(false); });

    // Public marketing header's mobile menu toggle.
    const navbar = document.getElementById("public-navbar");
    const navbarToggle = document.getElementById("navbar-toggle");

    if (navbar && navbarToggle) {
        navbarToggle.addEventListener("click", () => {
            const isOpen = navbar.classList.toggle("navbar-open");
            navbarToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                navbar.classList.remove("navbar-open");
                navbarToggle.setAttribute("aria-expanded", "false");
            }
        });
    }
})();
