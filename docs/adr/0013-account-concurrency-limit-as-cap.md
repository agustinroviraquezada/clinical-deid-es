# ADR-0013 · Account concurrency limit as the cap, no reserved concurrency

- **Status:** Accepted · 28 Nov 2026
- **Amends:** NFR-04 and the T4.3 "Done when" criterion (reserved concurrency configured)

## Context
NFR-04 and design §8 (OWASP LLM10) cap parallel executions with Lambda reserved concurrency (5).
The account's applied limit is 10 concurrent executions, and AWS keeps at least 10 of them
unreserved, so `put-function-concurrency` is refused (`minimum value of [10]`). Raising the
limit needs an AWS Support case, and Service Quotas only accepts values above the default of
1,000. The submission is due on 29 Nov 2026 and the Support cases already open for this account
have not been answered.

## Decision
No reserved concurrency is set. The account limit of 10 concurrent executions is the cap on
parallel copies of the function. T4.3 is complete with the other controls: 413 above 10,000
characters, security headers and CSP, and the no-text-in-logs test.

## Alternatives considered
Open a Support case for the limit increase: no answer likely before the deadline, and the
current limit already bounds the burst. Keep T4.3 open: it would track a control that the
account cannot have, not pending work.

## Consequences
A burst can run up to 10 copies instead of 5, which doubles the worst-case compute cost per
second; Bedrock is not reachable from the Lambda today (#23), so no token cost is at stake. The
login, the attempt limit, the per-request LLM call cap and time budget, and the AWS Budgets
alerts remain in place. If the account limit is ever raised, reserved concurrency 5 must be set
before the cascade is turned on (docs/deployment.md §4 and §8).
