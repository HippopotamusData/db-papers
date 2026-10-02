(() => {
  const GROUP_BUTTON_CLASS = "dbp-search-group-toggle";
  const RESULT_COUNT_PATTERN = /^([\d,]+)\s+results?$/i;
  const summaryStates = new WeakMap();

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
      [data-dbp-search-source-count] { display: none; }
      [data-dbp-search-source-summary="true"] { display: none; }
      [data-dbp-search-summary][hidden] { display: none; }
      [data-dbp-search-summary] mjx-container[display="true"] { margin: 0.3em 0; }
      [data-dbp-search-summary] mjx-container { max-width: 100%; overflow-x: auto; overflow-y: hidden; }
      .dbp-search-math-fragment { font: inherit; overflow-wrap: anywhere; }
      .dbp-search-math-highlight { color: var(--color-highlight); }
      [data-dbp-search-count] { overflow-wrap: anywhere; }
      @media (max-width: 680px) {
        [data-dbp-search-dialog] { flex-direction: column; }
        [data-dbp-search-filters] {
          position: relative;
          top: auto;
          right: auto;
          width: 100%;
          height: auto;
          max-height: 40vh;
          border-left: 0;
          border-top: 1px solid rgb(var(--color-foreground)/var(--alpha-lightest));
          box-shadow: none;
        }
        [data-dbp-search-filters] > div { position: relative; box-sizing: border-box; }
        [data-dbp-search-filters].l { height: 0; border: 0; pointer-events: none; }
      }
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

  function mathSegments(text) {
    const segments = [];
    const delimiters = /\\[()[\]]/g;
    let opening = null;
    for (const match of text.matchAll(delimiters)) {
      const delimiter = match[0];
      if (delimiter === "\\(" || delimiter === "\\[") {
        if (opening) {
          segments.push({ start: opening.index, end: match.index });
        }
        opening = { index: match.index, delimiter };
      } else if (opening && delimiter === (opening.delimiter === "\\(" ? "\\)" : "\\]")) {
        segments.push({
          start: opening.index,
          end: match.index + 2,
          tex: text.slice(opening.index + 2, match.index),
          display: opening.delimiter === "\\[",
        });
        opening = null;
      } else if (!segments.length && !opening) {
        // An excerpt can start inside a formula. Keep that exact fragment.
        segments.push({ start: 0, end: match.index + 2 });
      }
    }
    if (opening) segments.push({ start: opening.index, end: text.length });
    return segments;
  }

  function summaryMathSpans(display, segments) {
    const nodes = [];
    const walker = document.createTreeWalker(display, NodeFilter.SHOW_TEXT);
    let offset = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      nodes.push({ node, start: offset, end: offset + node.textContent.length });
      offset += node.textContent.length;
    }
    const spans = [];
    // Work backwards so ranges in earlier text and native highlights survive.
    for (const segment of segments.slice().reverse()) {
      const start = nodes.find((part) => part.end > segment.start);
      const end = nodes.find((part) => part.end >= segment.end);
      if (!start || !end || start.node.parentElement.closest("code, pre")) continue;
      const range = document.createRange();
      range.setStart(start.node, segment.start - start.start);
      range.setEnd(end.node, segment.end - end.start);
      const span = document.createElement("span");
      span.append(range.extractContents());
      range.insertNode(span);
      if (segment.tex === undefined) {
        showMathSource(span, "公式片段（查看正文）");
        span.title = "公式片段不完整，请打开正文查看完整公式";
        span.setAttribute("aria-label", `不完整的公式片段：${span.textContent}`);
      } else {
        if (span.querySelector("mark")) span.classList.add("dbp-search-math-highlight");
        spans.push({ span, ...segment });
      }
    }
    return spans;
  }

  function showMathSource(span, label) {
    const code = document.createElement("code");
    code.append(...span.childNodes);
    span.classList.add("dbp-search-math-fragment");
    span.append(document.createTextNode(`${label}：`), code);
  }

  async function renderSummary(root, source, state, segments) {
    const math = summaryMathSpans(state.display, segments);
    if (math.length) {
      const engine = window.MathJax;
      await engine?.startup?.promise;
      if (!engine?.tex2chtmlPromise) return;
      const fontSize = Number.parseFloat(getComputedStyle(source).fontSize) || 12;
      for (const item of math) {
        if (summaryStates.get(source) !== state || !source.isConnected) return;
        try {
          const rendered = await engine.tex2chtmlPromise(item.tex, {
            display: item.display, em: fontSize, ex: fontSize / 2,
            containerWidth: source.getBoundingClientRect().width || 360,
          });
          if (rendered.querySelector("mjx-merror, [data-mjx-error]")) {
            showMathSource(item.span, "公式暂未渲染（查看正文）");
            continue;
          }
          item.span.replaceChildren(rendered);
        } catch {
          showMathSource(item.span, "公式暂未渲染（查看正文）");
          item.span.title = "公式暂未渲染，请打开正文核对";
        }
      }
      // CSSOM includes adaptive fraction/superscript and font rules absent from
      // style.textContent. Keep the shared cache used by the reading pages.
      let style = root.querySelector("style[data-dbp-search-math-styles]");
      if (!style) {
        style = document.createElement("style");
        style.dataset.dbpSearchMathStyles = "true";
        root.append(style);
      }
      setText(style, engine.startup.adaptor.cssText(engine.chtmlStylesheet()));
    }
    if (summaryStates.get(source) !== state || !source.isConnected ||
        source.innerHTML !== state.signature) return;
    source.dataset.dbpSearchSourceSummary = "true";
    state.display.hidden = false;
  }

  function enhanceSummaries(root) {
    for (const item of root.querySelectorAll("ol > li")) {
      if (item.hidden) continue;
      const source = item.querySelector("a h2")?.nextElementSibling;
      if (!source || source.tagName !== "DIV") continue;
      const signature = source.innerHTML;
      if (summaryStates.get(source)?.signature === signature) continue;
      source.nextElementSibling?.matches("[data-dbp-search-summary]") &&
        source.nextElementSibling.remove();
      source.dataset.dbpSearchSourceSummary = "false";
      const segments = mathSegments(source.textContent);
      const state = { signature };
      summaryStates.set(source, state);
      if (!segments.length) continue;
      const display = source.cloneNode(true);
      display.removeAttribute("data-dbp-search-source-summary");
      display.dataset.dbpSearchSummary = "true";
      display.hidden = true;
      source.after(display);
      state.display = display;
      renderSummary(root, source, state, segments).catch(() => {
        // Preserve native readable source when the renderer is unavailable.
        if (summaryStates.get(source) === state) display.remove();
      });
    }
  }

  function enhanceControls(root) {
    const input = root.querySelector('input[role="combobox"]');
    const filterButton = root.querySelector('button:has(svg.lucide-list-filter)');
    const heading = Array.from(root.querySelectorAll("h3")).find(
      (element) => ["Filters", "筛选"].includes(element.textContent.trim()),
    );
    const panel = heading?.parentElement?.parentElement;
    if (!input || !filterButton || !panel?.contains(root.querySelector("h4"))) return;
    const dialog = panel.parentElement;
    panel.dataset.dbpSearchFilters = "true";
    panel.id = "dbp-search-filters";
    dialog.dataset.dbpSearchDialog = "true";
    // These two native states belong to the pinned Zensical search component.
    // Toggle through its own handler so its state and DOM remain in agreement.
    if (!filterButton.dataset.dbpReady) {
      filterButton.dataset.dbpReady = "true";
      if (window.matchMedia("(max-width: 680px)").matches && !panel.classList.contains("l")) {
        filterButton.click();
      }
    }
    const expanded = !panel.classList.contains("l");
    filterButton.setAttribute("aria-label", expanded ? "收起搜索筛选" : "展开搜索筛选");
    filterButton.setAttribute("aria-expanded", String(expanded));
    filterButton.setAttribute("aria-controls", panel.id);
    panel.inert = !expanded;
    for (const tag of panel.querySelectorAll("ol > li")) {
      tag.setAttribute("role", "button");
      tag.tabIndex = 0;
      tag.setAttribute("aria-pressed", String(tag.classList.contains("g")));
      if (!tag.dataset.dbpKeyboardReady) {
        tag.dataset.dbpKeyboardReady = "true";
        tag.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            event.stopPropagation();
            tag.click();
          }
        });
      }
    }
    root.querySelector('button:has(svg.lucide-search), button:has(svg.lucide-arrow-left)')
      ?.setAttribute("aria-label", "关闭搜索");
  }

  function updateCount(root, pages) {
    // Never replace the framework-owned text node: its reactive count updates
    // must continue through query changes, tag filters and lazy loading.
    const source = root.querySelector("[data-dbp-search-source-count]") ??
      Array.from(root.querySelectorAll("h3")).find(
        (element) => RESULT_COUNT_PATTERN.test(element.textContent.trim()),
      );
    if (!source) {
      root.querySelector("[data-dbp-search-count]")?.remove();
      return;
    }
    source.dataset.dbpSearchSourceCount = "true";
    const match = RESULT_COUNT_PATTERN.exec(source.textContent.trim());
    let display = source.nextElementSibling;
    if (!display?.hasAttribute("data-dbp-search-count")) {
      display = document.createElement("p");
      display.className = source.className;
      display.dataset.dbpSearchCount = "true";
      display.setAttribute("role", "status");
      source.after(display);
    }
    display.hidden = !match;
    if (match) {
      setText(display, `当前显示 ${pages} 个页面 · 共 ${match[1].replaceAll(",", "")} 个匹配段落`);
    }
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
      updateCount(root, 0);
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

    updateCount(root, groups.size);
  }

  function enhance(root) {
    if (!root.querySelector('input[role="combobox"]')) return;
    localizeLabels(root);
    installStyles(root);
    enhanceControls(root);
    groupResults(root);
    enhanceSummaries(root);
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
      characterData: true,
      attributes: true,
      attributeFilter: ["class"],
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
