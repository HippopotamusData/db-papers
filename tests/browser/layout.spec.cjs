const { test, expect } = require('@playwright/test');

const pages = [
  ['', 'home'],
  ['catalog/', 'catalog'],
  ['papers/query-processing/', 'area'],
  ['papers/system-architecture/clickhouse-lightning-fast-analytics-for-everyone/', 'reader'],
];

for (const width of [390, 834, 1440]) {
  for (const mode of ['light', 'dark']) {
    for (const [path, kind] of pages) {
      test(`${kind} stays usable at ${width}px in ${mode} mode`, async ({ page }) => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme: mode });
        await page.goto(path, { waitUntil: 'domcontentloaded' });
        await expect(page.locator('body')).toHaveAttribute('data-md-color-scheme', mode === 'dark' ? 'slate' : 'default');
        await expect(page.locator('.md-content__inner h1')).toBeVisible();
        if (kind === 'reader') {
          await expect(page.locator('.paper-meta')).toBeVisible();
          await expect(page.locator('.md-content__inner mjx-container').first()).toBeAttached();
        }
        const layout = await page.locator('.md-content__inner').evaluate(root => {
          // Classic scrollbars consume viewport width on Linux. Compare with
          // the available content area, rather than treating that gutter as overflow.
          const viewportWidth = document.documentElement.clientWidth;
          const outside = Array.from(root.querySelectorAll('.paper-card, .area-card, .recent-paper, .catalog-controls, .paper-meta, .paper-actions .md-button'))
            .filter(e => e.getClientRects().length)
            .filter(e => {
              const r = e.getBoundingClientRect();
              return r.left < -1 || r.right > viewportWidth + 1;
            }).map(e => ({ tag: e.className, text: e.textContent.trim().slice(0, 70) }));
          return { outside, overflow: document.documentElement.scrollWidth - viewportWidth };
        });
        expect(layout).toEqual({ outside: [], overflow: 0 });
        if (kind === 'catalog' || kind === 'area') {
          // Every paper has one unambiguous title entry after removing actions.
          const cards = await page.locator('.paper-card').evaluateAll(es => es.map(e => ({
            links: e.querySelectorAll('a').length,
            entry: !!e.querySelector('h3 a[href]'),
          })));
          expect(cards.length).toBeGreaterThan(0);
          expect(cards.every(e => e.links === 1 && e.entry)).toBeTruthy();
        }
        if (kind === 'catalog') {
          const controls = page.getByRole('search', { name: '筛选和排序论文' });
          expect((await controls.boundingBox()).height).toBeLessThan(width < 832 ? 55 : 110);
          if (width < 832) {
            const toggle = page.getByRole('button', { name: '筛选与排序', exact: true });
            await expect(page.getByRole('combobox', { name: '领域', exact: true })).toBeHidden();
            await toggle.focus();
            await toggle.press('Enter');
            await expect(toggle).toHaveAttribute('aria-expanded', 'true');
            expect((await controls.boundingBox()).height).toBeLessThan(170);
          }
          const fields = await controls.locator('select').evaluateAll(es => es.map(e => {
            const r = e.getBoundingClientRect();
            return { top: r.top, left: r.left, right: r.right, height: r.height };
          }));
          expect(fields[0].top).toBe(fields[1].top);
          expect(fields[2].top).toBe(fields[3].top);
          expect(fields.every(r => r.left >= 0 && r.right <= width && r.height >= (width < 832 ? 44 : 40))).toBeTruthy();
        }
        if (kind === 'reader' && mode === 'light') {
          expect(await page.locator('.paper-meta').evaluate(e => getComputedStyle(e).backgroundImage)).toBe('none');
        }
        expect(errors).toEqual([]);
      });
    }
  }
}
