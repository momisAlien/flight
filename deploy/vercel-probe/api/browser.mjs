import {createHandler, probeBrowser} from '../lib/probe.mjs';

export default createHandler(async () => {
  const [{default: puppeteer}, {default: chromium}] = await Promise.all([
    import('puppeteer-core'), import('@sparticuz/chromium')
  ]);
  return probeBrowser(puppeteer, chromium);
}, {...process.env, FLIGHT_PROTECTED_PREVIEW: '1'});
