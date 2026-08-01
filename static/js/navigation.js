(() => {
    const menus = Array.from(document.querySelectorAll(".nav-menu"));
    const supportsHover = window.matchMedia("(hover: hover) and (pointer: fine)");

    const closeOthers = (activeMenu) => {
        menus.forEach((menu) => {
            if (menu !== activeMenu) menu.removeAttribute("open");
        });
    };

    menus.forEach((menu) => {
        menu.querySelector("summary").addEventListener("click", (event) => {
            if (!supportsHover.matches) return;
            event.preventDefault();
            closeOthers(menu);
            menu.setAttribute("open", "");
        });

        menu.addEventListener("toggle", () => {
            if (menu.open) closeOthers(menu);
        });

        menu.addEventListener("mouseenter", () => {
            if (!supportsHover.matches) return;
            closeOthers(menu);
            menu.setAttribute("open", "");
        });

        menu.addEventListener("mouseleave", () => {
            if (supportsHover.matches) menu.removeAttribute("open");
        });
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".nav-menu")) closeOthers(null);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeOthers(null);
            document.querySelector(".nav-menu summary:focus")?.blur();
        }
    });
})();
