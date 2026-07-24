(() => {
  function enableHeaderHomeLink() {
    const title = document.querySelector(".md-header__title");
    const logo = document.querySelector("a.md-header__button.md-logo");
    if (!title || !logo || title.dataset.dbpHomeLink === "true") {
      return;
    }

    title.dataset.dbpHomeLink = "true";
    title.setAttribute("role", "link");
    title.setAttribute("tabindex", "0");
    title.setAttribute("aria-label", "返回首页");

    const openHome = () => {
      const currentLogo = document.querySelector("a.md-header__button.md-logo");
      if (currentLogo?.href) {
        window.location.assign(currentLogo.href);
      }
    };

    title.addEventListener("click", openHome);
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openHome();
      }
    });
  }

  enableHeaderHomeLink();
  if (typeof document$ !== "undefined") {
    document$.subscribe(enableHeaderHomeLink);
  }
})();
