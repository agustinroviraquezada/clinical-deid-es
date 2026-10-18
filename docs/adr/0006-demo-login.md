# ADR-0006 · Login with a single in-house demo account

- **Status:** Accepted · 18 Oct 2026

## Context
The TFM specification requires a test username and password if there is a login, and the public URL needs a barrier against abuse.

## Decision
One demo account: hashed password in an environment variable, signed `HttpOnly`/`Secure`/`SameSite=Strict` cookie, attempt limit.

## Alternatives considered
Amazon Cognito: robust but 4–6 h. Browser basic auth: quick but demonstrates little.

## Consequences
2–3 h. Covers the OWASP authentication risk. Lambda's in-memory counters are approximate (demo limitation).
