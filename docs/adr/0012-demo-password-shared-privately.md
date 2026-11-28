# ADR-0012 · Demo password shared privately, not in the README

- **Status:** Accepted · 28 Nov 2026
- **Amends:** ADR-0006 and FR-08 (test username and password in the README)

## Context
FR-08 and ADR-0006 put the demo username and password in the README so that the evaluator can
sign in. The repository is public, so a password in the README is a password for anyone. The login
is the main barrier in front of the public Function URL: Lambda reserved concurrency could not be
set (account quota of 10, #26), and every request costs compute and, once the cascade is on,
Bedrock tokens. The TFM specification asks for test credentials when there is a login; it does not
require them to be public.

## Decision
The README gives the username (`demo`) and states that the password is shared privately with the
evaluator, through the submission form or a direct message. The password is never written to the
repository, issues or pull requests.

## Alternatives considered
Password in the README, as decided before: simplest for the evaluator, but it turns the login into
an open door while there is no concurrency cap. Rotating the password after the grade: still
leaves the demo open during the whole evaluation period.

## Consequences
The login keeps working as an abuse barrier during the evaluation. The evaluator needs one extra
step (reading the password from the submission), and the submission checklist (T5.4) must include
it; if it is forgotten, the evaluator cannot use the demo. The T5.1 "Done when" criterion is read
as "test username in the README, password delivered privately".
