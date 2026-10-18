import {createHandler,probeBrowser} from './probe.mjs';
import {inspectProvider} from './provider.mjs';
export function providerHandler(provider) {
  return createHandler(async()=>{
    const [{default:puppeteer},{default:chromium}]=await Promise.all([
      import('puppeteer-core'),import('@sparticuz/chromium')]);
    return probeBrowser(puppeteer,chromium,page=>inspectProvider(page,provider));
  },{...process.env,FLIGHT_PROTECTED_PREVIEW:'0'},Date.now,'provider');
}
