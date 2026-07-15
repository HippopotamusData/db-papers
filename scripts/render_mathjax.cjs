#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

if (process.argv.length !== 3) {
  console.error("usage: render_mathjax.cjs MATHJAX_MODULE_PATH");
  process.exit(2);
}

let MathJax;
try {
  MathJax = require(path.resolve(process.argv[2]));
} catch (error) {
  console.error(`cannot load MathJax: ${error.message}`);
  process.exit(2);
}

let expressions;
try {
  expressions = JSON.parse(fs.readFileSync(0, "utf8"));
} catch (error) {
  console.error(`cannot parse expressions: ${error.message}`);
  process.exit(2);
}

MathJax.init({
  loader: { load: ["input/tex", "output/svg"] },
}).then(async (MathJax) => {
  const failures = [];
  for (const expression of expressions) {
    try {
      const rendered = await MathJax.tex2svgPromise(expression.text, {
        display: expression.display,
      });
      const serialized = MathJax.startup.adaptor.serializeXML(rendered);
      if (/data-mjx-error=|<mjx-merror\b|<merror\b/i.test(serialized)) {
        failures.push({ ...expression, error: "MathJax produced an error node" });
      }
    } catch (error) {
      failures.push({ ...expression, error: error.message });
    }
  }
  process.stdout.write(JSON.stringify(failures));
  process.exit(failures.length ? 1 : 0);
}).catch((error) => {
  console.error(`cannot initialize MathJax: ${error.message}`);
  process.exit(2);
});
