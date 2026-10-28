(() => {
  const summaryStates = new WeakMap();

  function setText(element, value) {
    if (element.textContent === value) return;
    // Preserve the framework-owned text node so native updates keep working.
    if (element.childNodes.length === 1 && element.firstChild.nodeType === Node.TEXT_NODE) {
      element.firstChild.data = value;
    } else {
      element.textContent = value;
    }
  }

  function localizeLabels(root) {
    const replacements = new Map([
      ["Search", "搜索"],
      ["Filters", "筛选"],
      ["Tags", "主题（数量为匹配段落数）"],
      ["Use Up and Down arrow keys to move between tags. Press Space or Enter to toggle a tag.",
        "使用上下方向键选择主题，按空格或回车键切换筛选。"],
    ]);
    for (const element of root.querySelectorAll("h1, h2, h3, h4, label, span")) {
      const replacement = replacements.get(element.textContent.trim());
      if (replacement) setText(element, replacement);
    }
    const input = root.querySelector('input[role="combobox"]');
    if (input) {
      input.placeholder = "搜索论文标题或正文";
      input.setAttribute("aria-label", "搜索论文标题或正文");
    }
    root.querySelector('[role="dialog"]')?.setAttribute("aria-label", "全文搜索");
    root.querySelector('[role="listbox"]')?.setAttribute("aria-label", "搜索结果");
    const count = root.querySelector('[role="status"]');
    if (count) count.dataset.dbpSearchCount = "true";
    const match = count?.textContent.trim().match(/^([\d,]+)\s+results?$/i);
    if (match) setText(count, `共 ${match[1].replaceAll(",", "")} 个匹配段落`);
    if (count?.textContent === "No results") setText(count, "没有匹配结果");
    if (count?.textContent === "Loading search…") setText(count, "正在加载搜索…");
  }

  function installStyles(root) {
    if (root.querySelector("style[data-dbp-search-styles]")) return;
    const style = document.createElement("style");
    style.dataset.dbpSearchStyles = "true";
    style.textContent = `
      [data-dbp-search-source-summary="true"] { display: none; }
      [data-dbp-search-summary][hidden] { display: none; }
      [data-dbp-search-summary] mjx-container[display="true"] { margin: 0.3em 0; }
      [data-dbp-search-summary] mjx-container { max-width: 100%; overflow-x: auto; overflow-y: hidden; }
      .dbp-search-math-fragment { font: inherit; overflow-wrap: anywhere; }
      .dbp-search-math-highlight { color: var(--color-highlight); }
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
        [data-dbp-search-filters][aria-hidden="true"] { height: 0; border: 0; pointer-events: none; }
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
    for (const item of root.querySelectorAll('ol[role="listbox"] > li')) {
      if (item.hidden) continue;
      const source = item.querySelector("a h2")?.parentElement?.querySelector(
        ":scope > div:not([data-dbp-search-summary])",
      );
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
    const filterButton = root.querySelector('button[aria-controls][aria-expanded]:has(svg.lucide-list-filter)');
    const panel = filterButton && root.getElementById(filterButton.getAttribute("aria-controls"));
    if (!panel) return;
    panel.dataset.dbpSearchFilters = "true";
    panel.parentElement.dataset.dbpSearchDialog = "true";
    if (!filterButton.dataset.dbpReady) {
      filterButton.dataset.dbpReady = "true";
      if (window.matchMedia("(max-width: 680px)").matches &&
          filterButton.getAttribute("aria-expanded") === "true") {
        filterButton.click();
      }
    }
    const expanded = filterButton.getAttribute("aria-expanded") === "true";
    filterButton.setAttribute("aria-label", expanded ? "收起搜索筛选" : "展开搜索筛选");
    root.querySelector('button[aria-label="Close search"]')?.setAttribute("aria-label", "关闭搜索");
    // Native buttons own keyboard handling, focus, selection and hidden state.
  }

  function enhance(root) {
    if (!root.querySelector('input[role="combobox"]')) return;
    localizeLabels(root);
    installStyles(root);
    enhanceControls(root);
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
