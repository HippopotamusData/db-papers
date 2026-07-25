(() => {
  function expandPrimaryNavigation() {
    const toggles = document.querySelectorAll(
      ".md-sidebar--primary .md-nav--primary > .md-nav__list > " +
        ".md-nav__item--nested > .md-nav__toggle",
    );
    for (const toggle of toggles) {
      toggle.checked = true;
      const nestedNavigation = toggle.parentElement?.querySelector(
        ":scope > nav.md-nav",
      );
      nestedNavigation?.setAttribute("aria-expanded", "true");
    }
  }

  expandPrimaryNavigation();
  if (typeof document$ !== "undefined") {
    document$.subscribe(expandPrimaryNavigation);
  }
})();
