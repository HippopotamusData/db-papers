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
  await page.getByRole('button', { name: '清除全部筛选和排序' }).click();
  await expect(page.locator('#catalog-search')).toHaveValue('');
  await expect(page.locator('#catalog-area')).toHaveValue('');
  await expect(page.locator('#catalog-empty')).toBeHidden();
  const total = await page.locator('.paper-card').count();
  await expect(page.locator('#catalog-count')).toHaveText(String(total));
  await page.reload();
  await expect(page.locator('#catalog-count')).toHaveText(String(total));
  await expect(page.locator('#catalog-clear')).toBeHidden();
});

test('search totals follow queries, filters and lazy loading without stale counts', async ({ page }) => {
  await page.goto('');
  await page.getByRole('button', { name: /查找/ }).click();
  const search = page.getByRole('combobox', { name: '搜索论文标题或正文' });
  const count = page.locator('[data-dbp-search-count]');
  const nativeCount = page.locator('[data-dbp-search-source-count]');
  async function expectCurrentCount(query) {
    await search.fill(query);
    await expect.poll(() => page.locator('li > a[href*="?h="]').first().evaluate(
      (link) => new URL(link.href).searchParams.get('h'),
    )).toBe(query);
    await expect(nativeCount).toHaveText(/^\d+ results?$/);
    await expect.poll(async () => {
      const raw = await nativeCount.textContent();
      return (await count.textContent()).endsWith(`共 ${raw.split(' ')[0]} 个匹配段落`);
    }).toBeTruthy();
    return (await nativeCount.textContent()).split(' ')[0];
  }
  const first = await expectCurrentCount('ClickHouse');
  await expect(count).toContainText('当前显示 1 个页面');
  const second = await expectCurrentCount('连接');
  expect(second).not.toBe(first);
  expect(await expectCurrentCount('ClickHouse')).toBe(first);
  // Loading more passages changes the rendered count, never the total.
  await page.locator('.dbp-search-group-toggle').click();
  await page.locator('li:has(> a[href*="clickhouse-lightning-fast"])').last().scrollIntoViewIfNeeded();
  await expect.poll(() => page.locator('li:has(> a[href*="clickhouse-lightning-fast"])').count()).toBeGreaterThan(10);
  await expect(count).toContainText(`共 ${first} 个匹配段落`);
  await search.fill('no-paper-matches-this-query');
  await expect(page.locator('[data-dbp-search-dialog] li:has(> a[href*="/papers/"])')).toHaveCount(0);
  await expect(count).toBeHidden();
  await search.fill('');
  await expect(count).toBeHidden();
  await expectCurrentCount('ClickHouse');
  await page.getByRole('button', { name: '关闭搜索' }).click();
  await page.getByRole('button', { name: /查找/ }).click();
  expect(await expectCurrentCount('ClickHouse')).toBe(first);
  // Tags are native toggles; their count should still drive our own label.
  const beforeFilter = Number(await expectCurrentCount('连接'));
  const tag = page.locator('[data-dbp-search-filters]').getByRole('button', { name: /^云原生/ });
  await tag.focus();
  await page.keyboard.press('Enter');
  await expect(tag).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(async () => Number((await nativeCount.textContent()).split(' ')[0])).toBeLessThan(beforeFilter);
  await expect.poll(async () => {
    const raw = await nativeCount.textContent();
    return (await count.textContent()).endsWith(`共 ${raw.split(' ')[0]} 个匹配段落`);
  }).toBeTruthy();
  await tag.focus();
  await page.keyboard.press('Space');
  await expect(tag).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(async () => Number((await nativeCount.textContent()).split(' ')[0])).toBe(beforeFilter);
});

test('mobile search filters stay below results and can be reopened', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('');
  await page.locator('label[for="__search"]').click();
  await page.getByRole('combobox').fill('连接');
  const filters = page.locator('[data-dbp-search-filters]');
  await expect(page.getByRole('button', { name: '展开搜索筛选' })).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: '展开搜索筛选' }).click();
  await expect(page.getByRole('button', { name: '收起搜索筛选' })).toHaveAttribute('aria-expanded', 'true');
  await expect.poll(() => filters.evaluate((panel) => {
    const dialog = panel.parentElement;
    const results = dialog.firstElementChild;
    return panel.getBoundingClientRect().top >= results.getBoundingClientRect().bottom - 1;
  })).toBeTruthy();
  await page.getByRole('button', { name: '收起搜索筛选' }).click();
  await expect(page.locator('[data-dbp-search-count]')).toBeVisible();
});

test('mobile TOC closes after section selection and Escape', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('papers/system-architecture/clickhouse-lightning-fast-analytics-for-everyone/');
  const toggle = page.locator('#__toc');
  await page.locator('.md-sidebar-button[for="__toc"]').click();
  await expect(toggle).toBeChecked();
  await page.locator('nav[aria-label="目录"]').getByRole('link', { name: '3.2 数据剪枝', exact: true }).click();
  await expect(page).toHaveURL(/#32$/);
  await expect(toggle).not.toBeChecked();
  await page.locator('.md-sidebar-button[for="__toc"]').click();
  await expect(toggle).toBeChecked();
  await page.keyboard.press('Escape');
  await expect(toggle).not.toBeChecked();
});

test('search math renders with highlights and survives updates and lazy loading', async ({ page }) => {
  await page.goto('');
  await page.getByRole('button', { name: /查找/ }).click();
  const search = page.getByRole('combobox', { name: '搜索论文标题或正文' });
  await search.fill('连接');
  const snippets = page.locator('[data-dbp-search-summary]:not([hidden])');
  await expect(snippets.locator('mjx-container').first()).toBeVisible();
  await expect(snippets.locator('mark').first()).toBeVisible();
  await expect(page.locator('[data-dbp-search-source-summary="true"]').first()).toBeHidden();
  await expect(page.locator('style[data-dbp-search-math-styles]')).toHaveCount(1);
  await expect(page.locator('[data-dbp-search-dialog] mjx-merror')).toHaveCount(0);
  await search.fill('ClickHouse');
  await expect(page.locator('[data-dbp-search-count]')).toContainText('共 44 个匹配段落');
  await search.fill('连接');
  await expect(snippets.locator('mjx-container').first()).toBeVisible();
  const toggle = page.locator('.dbp-search-group-toggle').first();
  await toggle.click();
  const items = page.locator('[data-dbp-search-dialog] ol > li:has(> a[href])');
  const loaded = await items.count();
  await items.filter({ visible: true }).last().scrollIntoViewIfNeeded();
  await expect.poll(() => items.count()).toBeGreaterThan(loaded);
  await expect(page.locator('[data-dbp-search-dialog] mjx-merror')).toHaveCount(0);

  // A controlled native excerpt update exercises split highlights, new
  // adaptive fraction rules and an unbalanced formula at the truncation edge.
  const source = page.locator('[data-dbp-search-source-summary]').first();
  const fixture = String.raw`比例 \(<mark>\frac</mark>{l}{s}\) 与平方 \(x^2\)，截断片段 \(\frac{a}{`;
  await source.evaluate((element, html) => { element.innerHTML = html; }, fixture);
  const display = source.locator('xpath=following-sibling::*[1]');
  const fraction = display.locator('mjx-mfrac');
  await expect(fraction).toBeVisible();
  await expect.poll(() => fraction.evaluate((element) => {
    const numerator = element.querySelector('mjx-num').getBoundingClientRect();
    const denominator = element.querySelector('mjx-den').getBoundingClientRect();
    const bar = element.querySelector('mjx-line').getBoundingClientRect();
    return numerator.bottom <= bar.top && bar.bottom <= denominator.top && bar.width > 2;
  })).toBeTruthy();
  await expect(display.locator('mjx-msup')).toBeVisible();
  await expect(display.locator('.dbp-search-math-highlight mjx-mfrac')).toBeVisible();
  await expect(display.locator('.dbp-search-math-fragment')).toContainText('公式片段（查看正文）');
  await expect(display.locator('.dbp-search-math-fragment code')).toHaveText(String.raw`\(\frac{a}{`);
  await expect(display.locator('.dbp-search-math-fragment')).toHaveAttribute('title', /不完整/);
  expect(await source.innerHTML()).toBe(fixture);
  // A slow old conversion must never overwrite a newer framework excerpt.
  await page.evaluate(() => {
    const convert = window.MathJax.tex2chtmlPromise.bind(window.MathJax);
    window.MathJax.tex2chtmlPromise = async (...args) => {
      await new Promise(resolve => { window.releaseSearchMath = resolve; });
      window.MathJax.tex2chtmlPromise = convert;
      return convert(...args);
    };
  });
  await source.evaluate(element => { element.textContent = String.raw`旧摘要 \(x^3\)`; });
  await expect.poll(() => page.evaluate(() => typeof window.releaseSearchMath)).toBe('function');
  await source.evaluate(element => { element.textContent = '新的无公式摘要'; });
  await page.evaluate(() => window.releaseSearchMath());
  await expect(source).toBeVisible();
  await expect(source).toHaveText('新的无公式摘要');
  await expect(display).toHaveCount(0);
});
