(() => {
    // Sidebar group expand/collapse (admin's "Academics" / "School Operations" sections).
    document.querySelectorAll(".sidebar-group-toggle").forEach((toggle) => {
        toggle.addEventListener("click", () => {
            const group = toggle.closest(".sidebar-group");
            if (group) group.classList.toggle("open");
        });
    });

    // Auto-expand a group that contains the current page, so the active link is visible.
    document.querySelectorAll(".sidebar-group").forEach((group) => {
        if (group.querySelector(".sidebar-link.active")) {
            group.classList.add("open");
        }
    });

    // Mobile off-canvas sidebar drawer.
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const sidebarBackdrop = document.getElementById("sidebar-backdrop");

    const closeSidebar = () => {
        document.body.classList.remove("sidebar-open");
        if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", "false");
    };

    const openSidebar = () => {
        document.body.classList.add("sidebar-open");
        if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", "true");
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
    });

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
