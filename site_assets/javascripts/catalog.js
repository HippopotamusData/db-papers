let cleanupCatalogState = () => {};

function setupCatalogFilters() {
  const grid = document.querySelector("#paper-grid");
  const search = document.querySelector("#catalog-search");
  const area = document.querySelector("#catalog-area");
  const topic = document.querySelector("#catalog-topic");
  const status = document.querySelector("#catalog-status");
  const sort = document.querySelector("#catalog-sort");
  const count = document.querySelector("#catalog-count");
  const empty = document.querySelector("#catalog-empty");
  const activeFilters = document.querySelector("#catalog-active-filters");
  const advancedToggle = document.querySelector(
    ".catalog-advanced__toggle",
  );

  if (
    !grid ||
    !search ||
    !area ||
    !topic ||
    !status ||
    !sort ||
    !count ||
    !empty
  ) {
    cleanupCatalogState();
    cleanupCatalogState = () => {};
    return;
  }
  if (grid.dataset.filtersReady === "true") {
    return;
  }
  cleanupCatalogState();
  grid.dataset.filtersReady = "true";

  const controls = { search, area, topic, status, sort };
  const storageKey = `dbp:catalog:${window.location.pathname}`;
  let saved = null;
  try {
    saved = JSON.parse(sessionStorage.getItem(storageKey));
  } catch {
    // Filtering remains available when browser storage is disabled.
  }
  if (saved && typeof saved === "object") {
    for (const [name, control] of Object.entries(controls)) {
      const value = saved[name];
      if (typeof value === "string" &&
          (control === search || Array.from(control.options).some(
            (option) => option.value === value))) {
        control.value = value;
      }
    }
    advancedToggle?.setAttribute("aria-expanded", String(saved.expanded === true));
  }
  const save = () => {
    if (!grid.isConnected) return;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({
        ...Object.fromEntries(Object.entries(controls).map(
          ([name, control]) => [name, control.value])),
        expanded: advancedToggle?.getAttribute("aria-expanded") === "true",
        scroll: window.scrollY,
      }));
    } catch {
      // Storage can be unavailable or full; do not interrupt navigation.
    }
  };

  const cards = Array.from(grid.querySelectorAll(".paper-card"));
  const originalOrder = new Map(cards.map((card, index) => [card, index]));
  const compareNumeric = (key, direction) => (left, right) => {
    const leftValue = Number.parseFloat(left.dataset[key]);
    const rightValue = Number.parseFloat(right.dataset[key]);
    const leftMissing = Number.isNaN(leftValue);
    const rightMissing = Number.isNaN(rightValue);
    if (leftMissing !== rightMissing) {
      return leftMissing ? 1 : -1;
    }
    if (!leftMissing && leftValue !== rightValue) {
      return (leftValue - rightValue) * direction;
    }
    return originalOrder.get(left) - originalOrder.get(right);
  };

  const apply = () => {
    const query = search.value.trim().toLocaleLowerCase("zh-CN");
    let visible = 0;
    for (const card of cards) {
      const matches =
        (!query || card.dataset.search.includes(query)) &&
        (!area.value || card.dataset.area === area.value) &&
        (!status.value || card.dataset.status === status.value) &&
        (!topic.value ||
          card.dataset.topics.split(/\s+/).includes(topic.value));
      card.hidden = !matches;
      if (matches) {
        visible += 1;
      }
    }

    const orderedCards = cards.slice();
    if (sort.value === "year-desc") {
      orderedCards.sort(compareNumeric("year", -1));
    } else if (sort.value === "year-asc") {
      orderedCards.sort(compareNumeric("year", 1));
    } else if (sort.value === "rating-desc") {
      orderedCards.sort(compareNumeric("rating", -1));
    } else if (sort.value === "rating-asc") {
      orderedCards.sort(compareNumeric("rating", 1));
    }
    // Moving a card during the search field's blur/change event cancels a
    // pending click on its link. Only move cards when their order changes.
    const currentOrder = Array.from(grid.querySelectorAll(".paper-card"));
    if (orderedCards.some((card, index) => card !== currentOrder[index])) {
      grid.append(...orderedCards);
    }

    count.textContent = String(visible);
    empty.hidden = visible !== 0;
    if (activeFilters) {
      const activeCount =
        Number(Boolean(area.value)) +
        Number(Boolean(topic.value)) +
        Number(Boolean(status.value)) +
        Number(sort.value !== "default");
      activeFilters.textContent = `${activeCount} 项已启用`;
      activeFilters.hidden = activeCount === 0;
    }
  };

  const update = () => {
    apply();
    save();
  };
  for (const control of Object.values(controls)) {
    control.addEventListener("input", update);
    control.addEventListener("change", update);
  }
  advancedToggle?.addEventListener("click", () => {
    const expanded =
      advancedToggle.getAttribute("aria-expanded") !== "true";
    advancedToggle.setAttribute("aria-expanded", String(expanded));
    save();
  });
  apply();
  // Capture before instant navigation detaches the current catalog.
  document.addEventListener("click", save, true);
  window.addEventListener("pagehide", save);
  let frame = requestAnimationFrame(() => {
    frame = requestAnimationFrame(() => {
      if (grid.isConnected && !window.location.hash &&
          Number.isFinite(saved?.scroll) && saved.scroll >= 0) {
        window.scrollTo(0, saved.scroll);
      }
    });
  });
  cleanupCatalogState = () => {
    cancelAnimationFrame(frame);
    document.removeEventListener("click", save, true);
    window.removeEventListener("pagehide", save);
  };
}

if (typeof document$ !== "undefined") {
  document$.subscribe(setupCatalogFilters);
} else {
  document.addEventListener("DOMContentLoaded", setupCatalogFilters);
}
