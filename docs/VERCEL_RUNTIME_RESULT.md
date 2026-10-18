# Vercel runtime validation — 2026-10-18

## Observed in the authenticated dashboard
- Account: dream30billion-5016's projects, Hobby.
- Production/main d80173c failed FASTAPI_ENTRYPOINT_NOT_FOUND.
- Root directory empty; framework FastAPI; Node 24.x.
- Preview Standard Protection enabled, Require Log In checked, no domain exceptions.
- No paid settings, authentication protections, or production settings changed.

## Actual verification
Branch: codex/vercel-runtime-check. Local flexible-flights and remote main preserved.
The Services configuration generated an empty build (Ready but HTTP 404) on this
project. Explicit static output + a standard Node Function resolved the preview.
Puppeteer 25 asynchronous defaultArgs needed await; failure diagnosed from runtime
logs, fixed and regression tested.

At commit 72e6ca0, clicking the preview's same-origin button returned:
```json
{"ok":true,"browser":"HeadlessChrome/153.0.8010.0","elapsed_ms":2827,"flight_search_verified":false}
```
This is an actual Vercel Function execution, not local Chrome. The browser rendered
only constant HTML and closed. No airline site, login, CAPTCHA or API key was used.
After successful verification, the temporary preview execution gate was disabled.
Older immutable preview deployments retain the time gate until 2026-10-19 00:00 KST
and remain protected by Vercel team login.

6 focused Node tests pass: auth, fail-closed default, success reporting, failure
recovery, concurrency, browser cleanup/async arguments, and preview environment,
origin, branch and expiry gates. npm install and runtime imports passed. No known
vulnerabilities reported by npm audit at install time.

## Not complete
- Production flight-ruddy-nine.vercel.app still points to the failed main deployment.
- This preview is a diagnostic page, not the flight app.
- Naver/Google real-price retrieval from Vercel, MyRealTrip reference API, durable
  results, queue/cancellation, ranking integration, and quota enforcement unverified.
- No claim that the full application runs free on Vercel yet.

Preview:
https://flight-git-codex-vercel-ru-a8ac2f-dream30billion-5016s-projects.vercel.app/

Test instructions: deploy/vercel-probe/README.md (Windows and macOS/Linux).
No local server is needed for this preview. The function closes Chrome when done.
Next: one provider query at a time under existing access restrictions, then durable
job/result design before promoting a functioning flight application to production.
