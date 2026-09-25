# SoilHealth authenticated dashboard

This project replaces the static demo with a read-only dashboard. Only `public/`
is published. Three Netlify Functions serve login, session/logout/telemetry,
and authenticated ingestion. Site-wide Netlify Blobs hold sessions and the latest
reading. No MQTT password or firmware is shipped to the browser.

## Data path

ESP32 -> HiveMQ TLS -> existing Python receiver/SQLite -> `cloud_bridge.py`
over HTTPS -> authenticated Netlify API -> dashboard.

Keep the receiver and bridge running on the computer. The bridge forwards the
latest fresh non-retained reading every 30 seconds. The dashboard polls every
15 seconds while visible and marks data stale after 45 seconds. It does not
relabel old readings as current after reconnecting. Full history remains in the
local SQLite database; the cloud stores the latest reading only. Charts collect
up to 120 distinct readings while the page is open.

All readings are labelled **Bench test — probes in air** by the backend.
Change that label only after the physical test context changes. Calibration is
still unverified. No control endpoint, automatic irrigation or ML advice exists.

## Security and configuration

- `DASHBOARD_USERNAME`: fixed read-only account.
- `DASHBOARD_PASSWORD_HASH`: salt plus scrypt hash, never the plaintext password.
- `INGEST_KEY_HASH`: SHA-256 hash of the independent random bridge key.
- Random server-stored sessions expire after eight hours. Cookies use HttpOnly,
  Secure, SameSite=Strict and the `__Host-` prefix. Logout deletes the session.
- Changing the password hash invalidates existing sessions on their next request.
- Login/logout enforce same-origin requests. There is no wildcard CORS access.
- Netlify rate-limit declarations protect login and upload routes; verify deployment
  processing applied them. Server validation checks telemetry and rejects stale
  or retained input. The bridge key cannot read data; dashboard cookies cannot
  upload data. Broker credentials do not establish signed device identity.
- This is a single-account implementation, with no self-service signup/password
  recovery, MFA, or claim of independent security certification.

Private credentials and the bridge configuration are outside this project in
`work/soilhealth-private/`. Never upload that folder, receiver databases,
`secrets.h`, or compiled firmware. Use Netlify CLI deployment, not Netlify Drop,
because server functions must be bundled.

## Checks

Run `node tests/security.test.mjs` and `node tests/api.test.mjs`.
Rebuild changed functions with `./build-functions.ps1` before deploying. This
uses the official esbuild executable directly and emits `.mjs` bundles into
`netlify/prebuilt/`. Netlify then packages those bundles without spawning a
second local bundler. The source functions remain in `netlify/functions/`.
Tests cover password checks, origin checks, expiry/revocation, separation of read
and upload access, telemetry validation, stale status, and logout.

The existing receiver tests remain in `../soilhealth-iot/receiver/test_receiver.py`.
