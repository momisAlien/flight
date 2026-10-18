# Vercel runtime check (NOT the flight application)

This is an isolated Preview deployment to validate browser packaging before migrating
the Python/Selenium task queue. Do not promote this branch to production.
No personal DB, provider key, search history or flight prices are included.

2026-10-18: actual dashboard confirms Hobby; production commit d80173c failed with
FASTAPI_ENTRYPOINT_NOT_FOUND. Framework FastAPI, root directory empty, Node 24.
Root vercel.json on this branch deliberately routes to this separate service.
The local flexible-flights app and remote main remain unchanged.

## Checks

Windows PowerShell (from the repository):
```powershell
cd deploy/vercel-probe
npm.cmd ci --ignore-scripts
npm.cmd test
```
macOS/Linux (from the repository):
```bash
cd deploy/vercel-probe
npm ci --ignore-scripts
npm test
```
Tests use fake browser objects, not live Chrome. They exit automatically.
Preview URL is supplied by Vercel after deployment; no local server is started here.

## Actual browser execution gate

After confirming Hobby and remaining usage in the dashboard, configure Preview-only
FLIGHT_PROBE_ENABLED=1 and a random FLIGHT_PROBE_TOKEN of at least 32 characters.
Never commit or paste the token in chat. POST /api/browser with Authorization:
Bearer <token>. Requests only render a constant inline page; arbitrary URLs and HTML
are never used. Chrome closes in finally; the endpoint has a 30-second Vercel limit.
The in-memory busy guard is per-instance, NOT a global rate limit. Disable the probe
again after one run; this is not a public search API or production endpoint.

Successful response must explicitly report flight_search_verified=false. Real
provider prices, durable storage, multi-instance jobs and free quota behavior remain
separate unverified steps. Do not claim browser packaging equals flight search.

References:
- https://vercel.com/docs/services
- https://vercel.com/kb/guide/deploying-puppeteer-with-nextjs-on-vercel
- https://github.com/Sparticuz/chromium
- https://pptr.dev/supported-browsers (Chromium 153 / Puppeteer 25.11)
