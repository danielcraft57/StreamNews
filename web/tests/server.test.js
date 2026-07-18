const request = require('supertest');

jest.mock('axios');
const axios = require('axios');

const { app } = require('../server');

describe('web API', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test('GET /api/health', async () => {
    const res = await request(app).get('/api/health');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'healthy', service: 'web' });
  });

  test('POST /api/analyze proxies to analyzer', async () => {
    axios.post.mockResolvedValue({
      data: { site_id: 1, url: 'https://example.com', status: 'pending', rss_feeds: [], total_pages_analyzed: 0 }
    });

    const res = await request(app)
      .post('/api/analyze')
      .send({ url: 'https://example.com', max_pages: 10, depth: 2 });

    expect(res.status).toBe(200);
    expect(res.body.site_id).toBe(1);
    expect(axios.post).toHaveBeenCalled();
  });

  test('GET /api/sites/:id/pages proxies to analyzer', async () => {
    axios.get.mockResolvedValue({
      data: { site_id: 7, pages: [{ url: 'https://example.com' }] }
    });

    const res = await request(app).get('/api/sites/7/pages');
    expect(res.status).toBe(200);
    expect(res.body.site_id).toBe(7);
    expect(res.body.pages).toHaveLength(1);
  });

  test('POST /api/websocket accepts messages', async () => {
    const res = await request(app)
      .post('/api/websocket')
      .send({ type: 'analysis_started', site_id: 1 });

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'ok' });
  });

  test('unknown route returns 404', async () => {
    const res = await request(app).get('/api/does-not-exist');
    expect(res.status).toBe(404);
  });
});
