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

  function enableHeaderTitleLink() {
    const title = document.querySelector(".md-header__title");
    const logo = document.querySelector("a.md-header__button.md-logo");
    if (!title || !logo || title.dataset.dbpHeaderLink === "true") {
      return;
    }

    title.dataset.dbpHeaderLink = "true";
    title.setAttribute("role", "link");
    title.setAttribute("tabindex", "0");

    const showsPageTitle = () =>
      title.classList.contains("md-header__title--active");

    const updateLabel = () => {
      title.setAttribute(
        "aria-label",
        showsPageTitle() ? "回到本页开头" : "返回首页",
      );
    };

    const followTitle = () => {
      if (showsPageTitle()) {
        if (window.location.hash) {
          window.history.replaceState(
            null,
            "",
            `${window.location.pathname}${window.location.search}`,
          );
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }

      const currentLogo = document.querySelector("a.md-header__button.md-logo");
      if (currentLogo?.href) {
        window.location.assign(currentLogo.href);
      }
    };

    updateLabel();
    new MutationObserver(updateLabel).observe(title, {
      attributeFilter: ["class"],
    });

    title.addEventListener("click", followTitle);
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        followTitle();
      }
    });
  }

  expandPrimaryNavigation();
  enableHeaderTitleLink();
  if (typeof document$ !== "undefined") {
    document$.subscribe(() => {
      expandPrimaryNavigation();
      enableHeaderTitleLink();
    });
  }
})();
