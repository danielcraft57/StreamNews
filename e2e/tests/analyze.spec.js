const { test, expect } = require('@playwright/test');

const MOCK_SITE = process.env.E2E_MOCK_URL || 'http://127.0.0.1:8765/';

async function openAddSourceModal(page) {
  await page.getByTestId('open-add-source').click();
  await expect(page.getByTestId('analyze-form')).toBeVisible();
}

async function fillAnalyzeUrl(page, url) {
  // Material Web: l'input natif est dans le shadow DOM
  await page.getByTestId('url-input').locator('input').fill(url);
}

test.describe('StreamNews UI', () => {
  test('affiche la console (feed + navigation)', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.sidebar-brand, .brand-name, h1').filter({ hasText: /StreamNews|Feed/i }).first()).toBeVisible();
    await expect(page.getByTestId('articles-list')).toBeVisible();
    await page.locator('[data-nav="sources"]').click();
    await expect(page.getByTestId('sites-list')).toBeVisible();
    await expect(page.getByTestId('open-add-source')).toBeVisible();
  });

  test('parcours sidebar Lire / Analyser / Compte', async ({ page }) => {
    await page.goto('/');

    await page.locator('[data-nav="favoris"]').click();
    await expect(page.getByTestId('articles-list')).toBeVisible();

    await page.locator('[data-nav="sources"]').click();
    await expect(page.getByTestId('sites-list')).toBeVisible();

    await page.locator('[data-nav="jobs"]').click();
    await expect(page.getByTestId('jobs-list')).toBeVisible();

    await page.locator('[data-nav="tendances"]').click();
    await expect(page.getByTestId('trends-list')).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Tendances$/i })).toBeVisible();

    await page.getByTestId('nav-radar').click();
    await expect(page.getByTestId('radar-list')).toBeVisible();
    await expect(page.getByRole('heading', { name: /Radar idees/i })).toBeVisible();

    await page.locator('[data-nav="settings"]').click();
    await expect(page.getByTestId('settings-form')).toBeVisible();

    await page.locator('[data-nav="feed"]').click();
    await expect(page.getByTestId('articles-list')).toBeVisible();
  });

  test('API health repond', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toEqual({ status: 'healthy', service: 'web' });
  });
});

test.describe('Radar idees e2e', () => {
  test('nav Radar + API radar', async ({ page, request }) => {
    await page.goto('/');
    await page.getByTestId('nav-radar').click();
    await expect(page.getByTestId('radar-list')).toBeVisible();
    await expect(page.getByRole('heading', { name: /Radar idees/i })).toBeVisible();
    await expect(page.getByTestId('radar-pack')).toBeVisible();

    const res = await request.get('/api/radar?days=30&limit=10');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('ideas');
    expect(Array.isArray(body.ideas)).toBeTruthy();
    expect(body).toHaveProperty('count');
    expect(body).toHaveProperty('window_days');
  });

  test('pack source ouvre le modal avec URL', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-radar').click();
    await expect(page.getByTestId('radar-pack')).toBeVisible();

    const first = page.locator('[data-radar-source-url]').first();
    await expect(first).toBeVisible();
    const url = await first.getAttribute('data-radar-source-url');
    expect(url).toBeTruthy();

    await first.click();
    await expect(page.getByTestId('analyze-form')).toBeVisible();
    await expect(page.getByTestId('url-input').locator('input')).toHaveValue(url);
  });

  test('API radar refresh + tendances', async ({ request }) => {
    const radar = await request.post('/api/radar/refresh?days=30&limit=20');
    expect(radar.ok()).toBeTruthy();
    const radarBody = await radar.json();
    expect(Array.isArray(radarBody.ideas)).toBeTruthy();
    expect(radarBody).toHaveProperty('computed_at');

    const trends = await request.get('/api/trends?days=30&limit=10');
    expect(trends.ok()).toBeTruthy();
    const trendsBody = await trends.json();
    expect(trendsBody).toHaveProperty('trends');
    expect(Array.isArray(trendsBody.trends)).toBeTruthy();
  });

  test('filtre theme radar (UI)', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-radar').click();
    await expect(page.getByTestId('radar-list')).toBeVisible({ timeout: 20_000 });

    await page.locator('[data-radar-theme-filter="saas"]').click();
    await expect(page.locator('[data-radar-theme-filter="saas"]')).toHaveClass(/is-active/);

    await page.locator('[data-radar-days="7"]').click();
    await expect(page.locator('[data-radar-days="7"]')).toHaveClass(/is-active/);
    await expect(page.getByTestId('radar-list')).toBeVisible();
  });
});

test.describe('Analyse e2e', () => {
  test('lance une analyse via modal source et voit un resultat', async ({ page }) => {
    await page.goto('/');
    await page.locator('[data-nav="sources"]').click();
    await openAddSourceModal(page);

    await fillAnalyzeUrl(page, MOCK_SITE);
    await page.locator('details.advanced-options summary').click();
    await page.getByTestId('max-pages').selectOption('25');
    await page.getByTestId('depth').selectOption('2');
    await page.getByTestId('analyze-btn').click();

    await expect(page.getByTestId('status')).toContainText(/Analyse lancée|Analyse démarrée|WebSocket|Analyse/i, {
      timeout: 20_000,
    });

    await expect(page.getByTestId('status')).toContainText(/terminée|flux RSS|articles|victoire|préts|prets/i, {
      timeout: 90_000,
    });

    await expect(page.getByTestId('sites-list')).toContainText(/Mock News Site|127\.0\.0\.1/i, {
      timeout: 30_000,
    });
    await expect(page.getByTestId('sites-list')).toContainText(/OK|2 RSS|RSS/i, {
      timeout: 10_000,
    });
  });

  test('API analyze + sites (sans navigateur)', async ({ request }) => {
    const analyze = await request.post('/api/analyze', {
      data: {
        url: MOCK_SITE,
        max_pages: 10,
        depth: 2,
      },
    });
    expect(analyze.ok()).toBeTruthy();
    const created = await analyze.json();
    expect(created.site_id).toBeTruthy();

    let site;
    for (let i = 0; i < 60; i++) {
      const res = await request.get(`/api/sites/${created.site_id}`);
      expect(res.ok()).toBeTruthy();
      site = await res.json();
      if (site.status === 'completed' || site.status === 'error') break;
      await new Promise((r) => setTimeout(r, 1000));
    }

    expect(site.status).toBe('completed');
    const feeds = typeof site.rss_feeds === 'string' ? JSON.parse(site.rss_feeds) : site.rss_feeds;
    expect(Array.isArray(feeds)).toBeTruthy();
    expect(feeds.length).toBeGreaterThan(0);
    expect(site.total_pages_analyzed).toBeGreaterThan(0);

    const pages = await request.get(`/api/sites/${created.site_id}/pages`);
    expect(pages.ok()).toBeTruthy();
    const pagesBody = await pages.json();
    expect(pagesBody.pages.length).toBeGreaterThan(0);
  });
});
