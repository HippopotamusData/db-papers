const { test, expect } = require('@playwright/test');

test('reader fractions stay stacked on load and after catalog navigation', async ({ page }) => {
  const paper = 'papers/implementation-foundations/data-prefetch-mechanisms/';
  async function expectFractionLayout() {
    const fraction = page.locator('.md-content__inner mjx-mfrac').first();
    await expect(fraction).toBeVisible();
    // Valid TeX and CHTML nodes alone do not prove readable output. A cleared
    // adaptive stylesheet left l and s side by side with a zero-width bar.
    await expect.poll(() => fraction.evaluate((element) => {
      const numerator = element.querySelector('mjx-num').getBoundingClientRect();
      const denominator = element.querySelector('mjx-den').getBoundingClientRect();
      const bar = element.querySelector('mjx-line').getBoundingClientRect();
      return numerator.bottom <= bar.top && bar.bottom <= denominator.top && bar.width > 5;
    })).toBeTruthy();
  }

  await page.goto(paper);
  await page.evaluate(() => window.MathJax.startup.promise);
  await expectFractionLayout();
  await page.getByRole('link', { name: '论文目录', exact: true }).first().click();
  await expect(page.locator('#paper-grid')).toHaveAttribute('data-filters-ready', 'true');
  await page.locator('#catalog-search').fill('data prefetch mechanisms');
  await page.locator('.paper-card:visible a').first().click();
  await expect(page).toHaveURL(new RegExp(`${paper}$`));
  await expectFractionLayout();
});

// Match the production path prefix and exercise the built HTML and real scripts.
test('catalog search click survives blur and back restores filters', async ({ page, request }) => {
  await page.goto('catalog/');
  await expect(page.locator('#paper-grid')).toHaveAttribute('data-filters-ready', 'true');
  const search = page.locator('#catalog-search');
  await search.fill('access path selection');
  await expect(page.locator('.paper-card:visible')).toHaveCount(1);
  const link = page.locator('.paper-card:visible a').first();
  const target = await link.getAttribute('href');
  await link.click(); // No pre-blur: this caught the original cancelled-click defect.
  await expect(page).toHaveURL(new URL(target, 'http://127.0.0.1:8766/db-papers/catalog/').href);
  const pdf = page.locator('a[href$="source.pdf"]').first();
  await expect(pdf).toBeVisible();
  const response = await request.get(new URL(await pdf.getAttribute('href'), page.url()).href);
  expect(response.ok()).toBeTruthy();
  expect((await response.body()).subarray(0, 5).toString()).toBe('%PDF-');
  await page.goBack();
  await expect(search).toHaveValue('access path selection');
  await expect(page.locator('.paper-card:visible')).toHaveCount(1);
});

test('narrow catalog has working controls and no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('catalog/');
  await expect(page.locator('#paper-grid')).toHaveAttribute('data-filters-ready', 'true');
  await page.locator('.catalog-advanced__toggle').click();
  await expect(page.locator('#catalog-area')).toBeVisible();
  await page.locator('#catalog-area').selectOption('query-processing');
  await expect(page.locator('.paper-card:visible').first()).toHaveAttribute('data-area', 'query-processing');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  await page.locator('#catalog-search').fill('no-paper-matches-this-query');
  await expect(page.locator('#catalog-empty')).toBeVisible();
  await expect(page.locator('#catalog-count')).toHaveText('0');
});
