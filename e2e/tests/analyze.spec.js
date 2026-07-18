const { test, expect } = require('@playwright/test');

const MOCK_SITE = process.env.E2E_MOCK_URL || 'http://127.0.0.1:8765/';

test.describe('StreamNews UI', () => {
  test('affiche la page d\'accueil', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /StreamNews/i })).toBeVisible();
    await expect(page.getByTestId('analyze-form')).toBeVisible();
    await expect(page.getByTestId('sites-list')).toBeVisible();
  });

  test('API health repond', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toEqual({ status: 'healthy', service: 'web' });
  });
});

test.describe('Analyse e2e', () => {
  test('lance une analyse sur le site mock et voit un resultat', async ({ page }) => {
    await page.goto('/');

    await page.getByTestId('url-input').fill(MOCK_SITE);
    await page.getByTestId('max-pages').selectOption('25');
    await page.getByTestId('depth').selectOption('2');
    await page.getByTestId('analyze-btn').click();

    // Accuse de reception API
    await expect(page.getByTestId('status')).toContainText(/Analyse lancée|Analyse démarrée|WebSocket/i, {
      timeout: 20_000,
    });

    // Fin d'analyse via WS ou refresh liste
    await expect(page.getByTestId('status')).toContainText(/terminée|flux RSS/i, {
      timeout: 90_000,
    });

    await expect(page.getByTestId('sites-list')).toContainText(MOCK_SITE.replace(/\/$/, ''), {
      timeout: 30_000,
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

    // Attendre le statut completed cote API
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
