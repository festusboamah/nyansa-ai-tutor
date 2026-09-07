(() => {
    // Progressive enhancement: every record and server link works without JS.
    document.querySelectorAll("[data-search-scope]").forEach((scope) => {
        const input = scope.querySelector("[data-search-input]");
        const cards = [...scope.querySelectorAll("[data-search-card]")];
        const count = scope.querySelector("[data-search-count]");
        const empty = scope.querySelector("[data-search-empty]");
        const tools = scope.querySelector("[data-search-tools]");
        if (!input || !count || !empty || !tools) return;
        tools.hidden = false;
        function filter() {
            const query = input.value.trim().toLocaleLowerCase();
            let visible = 0;
            cards.forEach((card) => {
                card.hidden = !(card.dataset.searchText || "").toLocaleLowerCase().includes(query);
                if (!card.hidden) visible += 1;
            });
            count.textContent = `${visible} of ${cards.length} shown`;
            empty.hidden = visible !== 0;
        }
        input.addEventListener("input", filter);
        scope.querySelector("[data-search-clear]")?.addEventListener("click", () => {
            input.value = "";
            filter();
            input.focus();
        });
        filter();
    });
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        });
    });
})();
