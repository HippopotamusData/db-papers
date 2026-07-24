function setupCatalogFilters() {
  const grid = document.querySelector("#paper-grid");
  const search = document.querySelector("#catalog-search");
  const area = document.querySelector("#catalog-area");
  const topic = document.querySelector("#catalog-topic");
  const status = document.querySelector("#catalog-status");
  const sort = document.querySelector("#catalog-sort");
  const count = document.querySelector("#catalog-count");
  const empty = document.querySelector("#catalog-empty");

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
    return;
  }
  if (grid.dataset.filtersReady === "true") {
    return;
  }
  grid.dataset.filtersReady = "true";

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
    grid.append(...orderedCards);

    count.textContent = String(visible);
    empty.hidden = visible !== 0;
  };

  for (const control of [search, area, topic, status, sort]) {
    control.addEventListener("input", apply);
    control.addEventListener("change", apply);
  }
  apply();
}

if (typeof document$ !== "undefined") {
  document$.subscribe(setupCatalogFilters);
} else {
  document.addEventListener("DOMContentLoaded", setupCatalogFilters);
}
