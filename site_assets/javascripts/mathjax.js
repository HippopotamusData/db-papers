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
};

if (typeof document$ !== "undefined") {
  document$.subscribe(() => {
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
