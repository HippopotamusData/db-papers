(() => {
  const GROUP_BUTTON_CLASS = "dbp-search-group-toggle";
  const RESULT_COUNT_PATTERN = /^([\d,]+)\s+results?$/i;

  function pageKey(anchor) {
    try {
      const url = new URL(anchor.href, window.location.href);
      return `${url.origin}${url.pathname}`;
    } catch {
      return anchor.href.split("#", 1)[0];
    }
  }

  function directResultItems(list) {
    return Array.from(list.children).filter(
      (item) => item.tagName === "LI" && item.querySelector("a[href]"),
    );
  }

  function setText(element, value) {
    if (element.textContent !== value) {
      element.textContent = value;
    }
  }

  function localizeLabels(root) {
    const replacements = new Map([
      ["Search", "搜索"],
      ["Filters", "筛选"],
      ["Tags", "主题（数量为匹配段落数）"],
    ]);
    for (const element of root.querySelectorAll(
      "h1, h2, h3, h4, label, span",
    )) {
      const replacement = replacements.get(element.textContent.trim());
      if (replacement) {
        setText(element, replacement);
      }
    }

    const input = root.querySelector('input[role="combobox"]');
    if (input) {
      input.placeholder = "搜索论文标题或正文";
      input.setAttribute("aria-label", "搜索论文标题或正文");
    }
  }

  function installStyles(root) {
    if (root.querySelector("style[data-dbp-search-styles]")) {
      return;
    }
    const style = document.createElement("style");
    style.dataset.dbpSearchStyles = "true";
    style.textContent = `
      .${GROUP_BUTTON_CLASS} {
        display: block;
        margin: 0.4rem 0 0;
        padding: 0;
        border: 0;
        color: var(--md-accent-fg-color, #007f78);
        background: transparent;
        cursor: pointer;
        font: inherit;
        font-weight: 700;
        text-align: left;
      }
      .${GROUP_BUTTON_CLASS}:hover {
        text-decoration: underline;
        text-underline-offset: 0.15em;
      }
      .${GROUP_BUTTON_CLASS}:focus-visible {
        border-radius: 0.15rem;
        outline: 2px solid var(--md-accent-fg-color, #007f78);
        outline-offset: 0.18rem;
      }
    `;
    root.append(style);
  }

  function updateGroup(items, button, expanded) {
    for (const item of items.slice(1)) {
      item.hidden = !expanded;
    }
    button.setAttribute("aria-expanded", String(expanded));
    const hiddenCount = items.length - 1;
    setText(
      button,
      expanded
        ? `收起此页面的另外 ${hiddenCount} 个匹配段落`
        : `展开此页面的另外 ${hiddenCount} 个匹配段落`,
    );
  }

  function groupResults(root) {
    const lists = Array.from(root.querySelectorAll("ol, ul"));
    const list = lists.find((candidate) => {
      const items = directResultItems(candidate);
      return items.length > 0;
    });
    if (!list) {
      return;
    }

    const items = directResultItems(list);
    const expandedByPage = new Map();
    for (const button of list.querySelectorAll(`.${GROUP_BUTTON_CLASS}`)) {
      expandedByPage.set(
        button.dataset.groupKey,
        button.getAttribute("aria-expanded") === "true",
      );
    }
    for (const item of items) {
      item.hidden = false;
    }

    const groups = new Map();
    for (const item of items) {
      const anchor = item.querySelector("a[href]");
      const key = pageKey(anchor);
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key).push(item);
    }

    const retainedButtons = new Set();
    for (const [key, groupItems] of groups) {
      if (groupItems.length < 2) {
        continue;
      }
      const firstItem = groupItems[0];
      let button = firstItem.querySelector(`:scope > .${GROUP_BUTTON_CLASS}`);
      if (!button) {
        button = document.createElement("button");
        button.type = "button";
        button.className = GROUP_BUTTON_CLASS;
        firstItem.append(button);
      }
      button.dataset.groupKey = key;
      retainedButtons.add(button);
      updateGroup(groupItems, button, expandedByPage.get(key) ?? false);

      if (button.dataset.listenerReady !== "true") {
        button.dataset.listenerReady = "true";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const expanded = button.getAttribute("aria-expanded") !== "true";
          const currentItems = directResultItems(list).filter((item) => {
            const anchor = item.querySelector("a[href]");
            return pageKey(anchor) === button.dataset.groupKey;
          });
          updateGroup(currentItems, button, expanded);
        });
      }
    }

    for (const button of list.querySelectorAll(`.${GROUP_BUTTON_CLASS}`)) {
      if (!retainedButtons.has(button)) {
        button.remove();
      }
    }

    let countHeading = root.querySelector("[data-dbp-search-count]");
    if (!countHeading) {
      countHeading = Array.from(
        root.querySelectorAll("h1, h2, h3, h4, p, span"),
      ).find((element) => RESULT_COUNT_PATTERN.test(element.textContent.trim()));
    }
    if (countHeading) {
      const match = RESULT_COUNT_PATTERN.exec(countHeading.textContent.trim());
      if (match) {
        countHeading.dataset.dbpSearchTotal = match[1].replaceAll(",", "");
      }
      countHeading.dataset.dbpSearchCount = "true";
      const total = countHeading.dataset.dbpSearchTotal ?? String(items.length);
      setText(
        countHeading,
        `当前显示 ${groups.size} 个页面 · 共 ${total} 个匹配段落`,
      );
    }
  }

  function enhance(root) {
    localizeLabels(root);
    installStyles(root);
    groupResults(root);
  }

  function observe(root) {
    if (root.__dbpSearchObserver) {
      return;
    }
    let scheduled = false;
    const schedule = () => {
      if (scheduled) {
        return;
      }
      scheduled = true;
      queueMicrotask(() => {
        scheduled = false;
        enhance(root);
        discoverShadowRoots(root);
      });
    };
    root.__dbpSearchObserver = new MutationObserver(schedule);
    root.__dbpSearchObserver.observe(root, {
      childList: true,
      subtree: true,
    });
    enhance(root);
  }

  function discoverShadowRoots(scope) {
    for (const element of scope.querySelectorAll("*")) {
      if (element.shadowRoot) {
        observe(element.shadowRoot);
      }
    }
  }

  function start() {
    discoverShadowRoots(document);
    let scheduled = false;
    const observer = new MutationObserver(() => {
      if (scheduled) {
        return;
      }
      scheduled = true;
      window.requestAnimationFrame(() => {
        scheduled = false;
        discoverShadowRoots(document);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
