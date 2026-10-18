import {createHash, timingSafeEqual} from 'node:crypto';

const digest = value => createHash('sha256').update(value).digest();

// Never accept a target URL or user HTML: this endpoint only renders a constant page.
export function createHandler(runBrowser, env = process.env) {
  let busy = false;
  return async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (req.method !== 'POST') {
      res.setHeader('Allow', 'POST');
      return res.status(405).json({error: 'POST_REQUIRED'});
    }
    const secret = env.FLIGHT_PROBE_TOKEN || '';
    if (env.FLIGHT_PROBE_ENABLED !== '1' || secret.length < 32) {
      return res.status(503).json({error: 'PROBE_DISABLED'});
    }
    const supplied = req.headers.authorization || '';
    if (typeof supplied !== 'string' || !timingSafeEqual(digest(supplied), digest(`Bearer ${secret}`))) {
      return res.status(401).json({error: 'UNAUTHORIZED'});
    }
    if (busy) return res.status(409).json({error: 'PROBE_BUSY'});
    busy = true;
    const start = Date.now();
    try {
      const result = await runBrowser();
      if (result.title !== 'Journey Note browser probe') throw new Error('Unexpected title');
      return res.status(200).json({ok: true, browser: result.version,
        elapsed_ms: Date.now() - start, flight_search_verified: false});
    } catch {
      // Do not return stack traces, filesystem paths, or environment values.
      return res.status(502).json({error: 'BROWSER_PROBE_FAILED', flight_search_verified: false});
    } finally {
      busy = false;
    }
  };
}

export async function probeBrowser(puppeteer, chromium) {
  let browser;
  try {
    browser = await puppeteer.launch({
      args: puppeteer.defaultArgs({args: chromium.args, headless: 'shell'}),
      executablePath: await chromium.executablePath(),
      headless: 'shell', timeout: 12000, protocolTimeout: 5000,
      defaultViewport: {width: 800, height: 600}
    });
    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on('request', request => request.abort());
    await page.setContent('<!doctype html><title>Journey Note browser probe</title><p>Browser ready</p>',
      {timeout: 5000, waitUntil: 'domcontentloaded'});
    return {title: await page.title(), version: await browser.version()};
  } finally {
    if (browser) {
      let timer;
      try {
        await Promise.race([browser.close(), new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error('close timeout')), 2000);
        })]);
      } catch {
        browser.process()?.kill('SIGKILL');
      } finally { clearTimeout(timer); }
    }
  }
}
