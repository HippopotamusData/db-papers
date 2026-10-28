(() => {
  function clearMathHighlights() {
    // Search highlights split TeX across HTML elements. Keep highlights in prose,
    // and restore contiguous source inside formulas before MathJax scans them.
    for (const mark of document.querySelectorAll(".arithmatex mark[data-md-highlight]")) {
      mark.replaceWith(...mark.childNodes);
    }
  }

  window.MathJax = {
    tex: {
      inlineMath: [["\\(", "\\)"]],
      displayMath: [["\\[", "\\]"]],
      processEscapes: true,
      processEnvironments: true,
    },
    options: {
      ignoreHtmlClass: ".*|",
      processHtmlClass: "arithmatex",
    },
    startup: {
      pageReady: () => {
        clearMathHighlights();
        return window.MathJax.startup.defaultPageReady();
      },
    },
  };

  if (typeof document$ !== "undefined") {
    document$.subscribe(() => {
      clearMathHighlights();
      if (!window.MathJax.startup || !window.MathJax.typesetPromise) {
        return;
      }
      // document$ can fire after the initial typeset. Keep the adaptive CSS
      // cache: clearing it drops rules still needed by existing CHTML nodes
      // (for example, fraction bars and stacked numerators/denominators).
      window.MathJax.typesetClear();
      window.MathJax.texReset();
      window.MathJax.typesetPromise();
    });
  }
})();
