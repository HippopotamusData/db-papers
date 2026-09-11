const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  timeout: 30000,
  retries: 0,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:8766/db-papers/', trace: 'retain-on-failure' },
  webServer: {
    command: `${process.env.PYTHON || '.venv/bin/python'} scripts/serve_built_site.py`,
    url: 'http://127.0.0.1:8766/db-papers/',
    reuseExistingServer: false,
  },
});
