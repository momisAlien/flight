# Vercel public-price observation — 2026-10-18

Fixed test: ICN → NRT, 2027-01-18 outbound / 2027-01-24 return,
one adult, economy. This was executed by Vercel Chromium, not the local PC.
Protected preview branch only; main and the local working app remain unchanged.

## Google: actual displayed prices received

Observed at 2026-10-18 21:00:04 KST, request duration 10,507ms.
38 visible cards, 33 recognized prices. Five cards did not yield a recognized
price; they are not silently counted as successful observations.

Observed cheapest card: KRW 386,787, ZIPAIR Tokyo, nonstop outbound ICN 13:05 →
NRT 15:30, 2h25m. The card says round-trip FROM total; its return itinerary,
seller final total, and complete inventory were not verified. Do not label this
as the guaranteed market minimum or a final bookable round-trip fare.

Other observed cards: Peach KRW394,387; Air Busan KRW439,687;
Jin Air KRW446,687; Air Busan KRW449,687. These are dated observations, not live
prices. No fabricated prices, CSV input, or local history was used.

## Naver: prices not received

First navigation succeeded but no cards appeared (~35.8 seconds).
A bounded diagnostic run at 21:02:11 KST completed after 54,795ms:
- Search conditions and page shell loaded correctly.
- Browser's own calls to flight-api.naver.com returned HTTP503 for
  /flight/international/searchFlights and /graphql.
- Diagnostic counters: 66 fetch/XHR starts, 66 responses. These include the
  website's internal requests/retries; the collector did not replay private APIs.
- No observed 401/403/429, CAPTCHA or login challenge. HTTP503 alone does not
  prove whether this is a temporary outage or a cloud-origin restriction.
- Stopped further probes. Added early stop on these price-server 5xx responses.

No proxies, stealth flags, account sessions, CAPTCHA handling or blocked-request
bypasses were used. Only rendered DOM cards were parsed; network diagnostics
retained host/path/status, never request headers, bodies, cookies or query tokens.

## Remaining

MyRealTrip has not been tested on Vercel and its key was not uploaded. The existing
calendar integration rejects a single departure date; this fixed-date test must
not silently expand the user's range. Durable search jobs/results, multi-city
top20, time filters and the actual application UI are not integrated into this
preview. Production main remains the previous failed deployment.

All temporary provider probes are disabled after this stage. Older immutable
preview URLs have team-login protection and expire their temporary gate at
2026-10-19 00:00 KST. No paid plan/resources were enabled.

Validation: 10 focused Node tests; real Google/Naver execution described above.
Install/test commands and preview URL are in deploy/vercel-probe/README.md.
