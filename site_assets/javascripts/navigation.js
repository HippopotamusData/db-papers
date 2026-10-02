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
  // The mobile floating TOC uses the same checkbox as the responsive sidebar.
  // Closing it does not cancel the native anchor navigation or scroll handling.
  document.addEventListener("click", (event) => {
    const link = event.target.closest('nav[aria-label="目录"] a[href]');
    const toggle = document.querySelector("#__toc");
    if (!link || !toggle?.checked) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin === window.location.origin &&
        target.pathname === window.location.pathname && target.hash) {
      toggle.checked = false;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const toggle = document.querySelector("#__toc");
      if (toggle?.checked) toggle.checked = false;
    }
  });
  if (typeof document$ !== "undefined") {
    document$.subscribe(expandPrimaryNavigation);
  }
})();
