#!/usr/bin/env node
"use strict";

const fs = require("fs");

if (process.argv.length !== 3) {
  console.error("usage: render_katex.cjs KATEX_MODULE_PATH");
  process.exit(2);
}

let katex;
try {
  katex = require(process.argv[2]);
} catch (error) {
  console.error(`cannot load KaTeX: ${error.message}`);
  process.exit(2);
}

let expressions;
try {
  expressions = JSON.parse(fs.readFileSync(0, "utf8"));
} catch (error) {
  console.error(`cannot parse expressions: ${error.message}`);
  process.exit(2);
}

const failures = [];
for (const expression of expressions) {
  try {
    katex.renderToString(expression.text, {
      displayMode: expression.display,
      throwOnError: true,
      strict: "error",
      trust: false,
    });
  } catch (error) {
    failures.push({ ...expression, error: error.message });
  }
}

process.stdout.write(JSON.stringify(failures));
process.exit(failures.length ? 1 : 0);
