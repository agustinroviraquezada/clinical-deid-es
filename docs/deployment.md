# Deployment runbook (AWS Lambda)

How to create the AWS resources of design §9 / ADR-0005 once, by hand, with the AWS CLI. After
this setup, every push to `main` is deployed by `.github/workflows/deploy.yml`.

Everything lives in **`eu-west-1`**. Resource names: ECR repository `clinical-deid`, Lambda
function `clinical-deid`, IAM roles `clinical-deid-github-deploy` and `clinical-deid-lambda`.

## How the pieces fit

```
push to main ──► GitHub Actions (deploy.yml)
                   │ job build-test: docker build + smoke test with the Lambda emulator
                   │                 (no AWS access), hands the image over as an artifact
                   │ job deploy (environment "production", main only):
                   │                 asks GitHub for a short-lived OIDC token
                   ▼
                 AWS STS ── trust policy: only repo …/clinical-deid-es, environment production
                   │ temporary credentials of role clinical-deid-github-deploy
                   ▼
                 ECR (push image :<sha>, tags immutable) ──► Lambda update-function-code
                                                               │
                 Function URL (auth AWS_IAM) ◄─────────────────┘  only signed requests get in
```

No AWS access keys are stored in GitHub: OIDC exchanges a token that GitHub signs for each run
for credentials that expire within an hour. Only the `deploy` job, which runs in the GitHub
environment `production`, can request that token. The environment only accepts `main`.

## Test the image locally (no AWS needed)

You need Docker Desktop. The Lambda base image includes the Runtime Interface Emulator (RIE): a
small server that exposes the same "invoke" API as Lambda on port 8080. The handler therefore
runs exactly as it will in AWS. This is the same smoke test that `deploy.yml` runs in CI.

```bash
# 1. Build the image (the first build downloads the Lambda base image, a few hundred MB).
docker build --tag clinical-deid:local .

# 2. Start it in the background; host port 9000 → emulator port 8080.
docker run --detach --rm --name lambda-local --publish 9000:8080 clinical-deid:local

# 3. Send a Lambda Function URL event (payload 2.0) for GET /api/health.
curl -s http://localhost:9000/2015-03-31/functions/function/invocations -d '{
  "version": "2.0", "routeKey": "$default", "rawPath": "/api/health", "rawQueryString": "",
  "headers": {"host": "localhost"},
  "requestContext": {"http": {"method": "GET", "path": "/api/health", "protocol": "HTTP/1.1",
                              "sourceIp": "127.0.0.1", "userAgent": "local"},
                     "requestId": "local", "routeKey": "$default", "stage": "$default"},
  "isBase64Encoded": false}'
# Expected: {"statusCode": 200, "body": "{\"status\":\"ok\",\"version\":\"0.1.0\"}", ...}

# 4. Look at the emulator logs if something fails, then stop the container (--rm removes it).
docker logs lambda-local
docker stop lambda-local
```

You do not need the emulator to try the API itself: `uv run uvicorn clinical_deid.api.app:app
--reload --port 8000` is faster. Use the image test when you change the `Dockerfile`, the
dependencies or `lambda_handler.py`.

On Windows, if Git Bash does not find `docker` (or the build fails with
`docker-credential-desktop ... not found`), open a new terminal after installing Docker Desktop.
You can also add its folder to the PATH:
`export PATH="$(cygpath -u "$LOCALAPPDATA")/Programs/DockerDesktop/resources/bin:$PATH"`.

## Prerequisites

- T1.1 done: account active, AWS Budgets alerts at 50 % and 80 % of €50.
- An administrator IAM user with MFA and **no access keys** (never the root user). `gh` logged in.
- Run the commands from the repository root in Git Bash (or a Codespace).

### CLI sign-in with `aws login`

`aws login` (AWS CLI ≥ 2.32) signs the CLI in through the browser with the same IAM user and MFA
as the console. The CLI then gets temporary credentials that last up to 12 hours, with no keys
stored on disk. The profile name is only a local label, and the command creates it.

```bash
aws --version                       # must be 2.32 or newer
aws login --profile deid-admin      # region: eu-west-1; sign in as the IAM user in the browser
aws sts get-caller-identity --profile deid-admin   # Arn: arn:aws:iam::<account>:user/<name>
```

If the CLI offers to configure an AWS MCP server or skills for AI coding agents, answer `never`:
it would give the agent administrator access to the account. When the session expires, run
`aws login --profile deid-admin` again.

### Shell setup (every new terminal)

```bash
export AWS_PROFILE=deid-admin   # every aws command below uses this profile
export AWS_REGION=eu-west-1
# Git Bash rewrites arguments that start with "/" into Windows paths, which would turn
# /aws/lambda/clinical-deid into C:/Program Files/Git/aws/... This turns that off.
export MSYS_NO_PATHCONV=1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "$ACCOUNT_ID"   # check it is the project account before going on
```

## 1. ECR repository (where images are stored)

```bash
# IMMUTABLE: a tag (the commit SHA) can never be overwritten with a different image.
aws ecr create-repository --repository-name clinical-deid \
  --image-scanning-configuration scanOnPush=true \
  --image-tag-mutability IMMUTABLE

# Keep only the 2 most recent images (the current one and one to roll back to). With the model
# inside, each image is ~2.5 GB and ECR storage is billed per GB-month.
aws ecr put-lifecycle-policy --repository-name clinical-deid --lifecycle-policy-text '{
  "rules": [{"rulePriority": 1, "description": "keep last 2 images",
             "selection": {"tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 2},
             "action": {"type": "expire"}}]}'
```

## 2. Let GitHub Actions sign in to AWS (OIDC)

The OIDC provider tells AWS to trust tokens issued by GitHub. You only need it once per account.

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

The deploy role can only be assumed by a job running in the `production` environment of this
repository (`infra/iam/github-oidc-trust.json`). The repository uses GitHub's immutable OIDC
subject format, which includes the numeric owner and repository IDs:
`repo:agustinroviraquezada@46496399/clinical-deid-es@1424460000:environment:production`.
A repository re-created later with the same name gets a new ID, so it cannot use the role. Check
the exact prefix with `gh api repos/<owner>/<repo>/actions/oidc/customization/sub`.
It can only push to the `clinical-deid` repository and update the `clinical-deid` function
(`infra/iam/github-deploy-policy.json`).

The policy files contain the placeholder `ACCOUNT_ID`. `sed` replaces it, and the result is
passed to the CLI directly as a JSON string. Do not use a temporary file: a `/tmp` path from Git
Bash does not exist for the Windows `aws.exe`.

```bash
aws iam create-role --role-name clinical-deid-github-deploy \
  --assume-role-policy-document "$(sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" infra/iam/github-oidc-trust.json)"
aws iam put-role-policy --role-name clinical-deid-github-deploy --policy-name deploy \
  --policy-document "$(sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" infra/iam/github-deploy-policy.json)"
```

If the role already exists and only the trust policy changes:
`aws iam update-assume-role-policy --role-name clinical-deid-github-deploy --policy-document "$(sed …)"`.

### GitHub environment `production`

A GitHub environment groups the deployment settings. Here it restricts deployment to `main`:
a job that declares `environment: production` from any other branch is rejected before it
starts. The OIDC token of that job carries `environment:production`, and AWS checks it.

```bash
REPO=agustinroviraquezada/clinical-deid-es
gh api -X PUT "repos/$REPO/environments/production" --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST "repos/$REPO/environments/production/deployment-branch-policies" \
  -f name=main -f type=branch
```

## 3. First run: push the image only

The repository variables are not secret (an ARN is not a credential). The workflow reads them
with `vars.*`.

```bash
gh variable set AWS_DEPLOY_ROLE_ARN --body "arn:aws:iam::$ACCOUNT_ID:role/clinical-deid-github-deploy"
gh variable set ECR_REPOSITORY --body clinical-deid
gh workflow run deploy.yml --ref main
sleep 5 && gh run watch   # "found no in progress runs": check with gh run list --workflow deploy.yml
```

`LAMBDA_FUNCTION_NAME` is not set yet, so the run builds, tests and pushes the image, then skips
the Lambda update. Each run tags its image `<commit SHA>-<run id>-<attempt>`, so re-runs never
collide with the immutable tags. Copy the URI of the most recently pushed image:

```bash
export IMAGE_URI=$(aws ecr describe-images --repository-name clinical-deid \
  --query 'sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]' --output text \
  | sed "s|^|$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/clinical-deid:|")
echo "$IMAGE_URI"
```

## 4. Lambda function and its Function URL

The execution role is the identity the function runs as. For the hello world it can only write
its own logs. Bedrock permission for a single model is added in section 8 (T3.5).

```bash
aws iam create-role --role-name clinical-deid-lambda \
  --assume-role-policy-document file://infra/iam/lambda-trust.json
aws iam attach-role-policy --role-name clinical-deid-lambda \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create the log group ourselves so that logs expire after 14 days. Otherwise Lambda creates
# it on the first call and keeps the logs forever (privacy by design and cost).
aws logs create-log-group --log-group-name /aws/lambda/clinical-deid
aws logs put-retention-policy --log-group-name /aws/lambda/clinical-deid --retention-in-days 14

# A new role takes a few seconds to become usable.
sleep 10

aws lambda create-function --function-name clinical-deid \
  --package-type Image --code ImageUri="$IMAGE_URI" \
  --role "arn:aws:iam::$ACCOUNT_ID:role/clinical-deid-lambda" \
  --architectures x86_64 --memory-size 512 --timeout 30
aws lambda wait function-active --function-name clinical-deid

# AWS_IAM: only requests signed with credentials of this account are accepted (design §9).
aws lambda create-function-url-config --function-name clinical-deid --auth-type AWS_IAM
```

512 MB is enough for the hello world. With the model, see section 7.4 (2,048 MB, 120 s).

**Reserved concurrency (design §8, OWASP LLM10).** This caps how many copies of the function
run at the same time, and with it the cost of a burst of requests. New accounts often have a
total limit of only 10 concurrent executions, and AWS requires 10 of them to stay unreserved.
Apply it once the quota increase requested in T1.1 is granted:

```bash
aws lambda put-function-concurrency --function-name clinical-deid \
  --reserved-concurrent-executions 5
```

Check it (read-only). The answer must show `"ReservedConcurrentExecutions": 5`; an empty
answer means no reservation is set yet. Requests beyond the cap get a 429 from the URL.

**Status (27 Nov 2026).** Not applied yet. The account's applied limit is 10 concurrent
executions (`aws lambda get-account-settings`), so `put-function-concurrency` fails with
`InvalidParameterValueException ... minimum value of [10]`. Service Quotas only accepts values
above the default of 1,000, so the increase back to the default is requested through an AWS
Support "Service limit increase" case (Lambda, EU (Ireland), Concurrent executions, 1,000).
Until it is granted, the account limit of 10 is the implicit cap on parallel executions. Once
granted, run the two commands above. Every `aws` command here assumes the right profile and
region, for example `export AWS_PROFILE=deid-admin AWS_REGION=eu-west-1` after `aws login`.

```bash
aws lambda get-function-concurrency --function-name clinical-deid
```

## 5. Turn on continuous deployment

```bash
gh variable set LAMBDA_FUNCTION_NAME --body clinical-deid
gh workflow run deploy.yml --ref main && gh run watch
```

From now on every push to `main` deploys automatically.

## 6. Check `/api/health`

```bash
export FUNCTION_URL=$(aws lambda get-function-url-config --function-name clinical-deid \
  --query FunctionUrl --output text)

# Unsigned request: must be rejected (403) because the URL is closed.
curl -s -o /dev/null -w "%{http_code}\n" "${FUNCTION_URL}api/health"

# Request signed with your AWS credentials (SigV4): must return {"status":"ok",...}.
# awscurl cannot read an `aws login` session directly, so export the session's temporary
# credentials as environment variables (eval loads them without printing them).
# The version is pinned because this tool runs with your AWS credentials.
eval "$(aws configure export-credentials --profile "$AWS_PROFILE" --format env)"
uvx awscurl==0.45 --service lambda --region "$AWS_REGION" "${FUNCTION_URL}api/health"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION
```

## 7. Model in the image (T2.6)

From T2.6 the image contains the fine-tuned model, and the API exposes `POST /api/deidentify`.
The image grows from ~200 MB to ~2.5 GB (CPU-only torch, transformers and the ~500 MB model).

### 7.1 Read-only Hugging Face token for GitHub Actions

The model repository is private, so `deploy.yml` needs a token to download it. Create a
**fine-grained** token on huggingface.co (Settings → Access Tokens) with only *Read access to
contents* of `ahrovira/clinical-deid-es-meddocan`, then store it as a repository secret. `gh`
asks for the value and does not echo it, so it never ends up in your shell history:

```bash
gh secret set HF_TOKEN
```

Without this secret the `build-test` job fails at "Download the pinned model".

### 7.2 Build and test the image locally

The Dockerfile copies `./model` (git-ignored). Download the pinned revision into it; `hf auth
login` (or an `HF_TOKEN` variable) must be set up first:

```bash
uvx --from huggingface-hub==2.4.0 hf download "$(jq -r .repo_id config/model.json)" \
  config.json model.safetensors tokenizer.json tokenizer_config.json \
  --revision "$(jq -r .revision config/model.json)" --local-dir model

docker build --provenance=false --sbom=false --tag clinical-deid:local .
docker run --detach --rm --name lambda-local --publish 9000:8080 clinical-deid:local
```

Then send the same event as the `deploy.yml` smoke test (`POST /api/deidentify` with a synthetic
note). The first call loads the model, so it is slow; the next ones show the warm latency.

The API also runs without Docker: `MODEL_PATH=model uv run uvicorn clinical_deid.api.app:app
--port 8000`, then `curl -s localhost:8000/api/deidentify -H 'Content-Type: application/json'
-d '{"text": "Paciente Lucía Fernández, ingresó el 12/03/2025."}'`.

### 7.3 Keep fewer images in ECR

Images are now ~2.5 GB each, so keep 2 instead of 5: re-run the `put-lifecycle-policy` command of
step 1 (now `"countNumber": 2`). It replaces the existing policy.

### 7.4 Memory and timeout

Lambda gives CPU in proportion to memory, so more memory means faster inference. The model loads
on the first request after a cold start (`get_cascade()` in `app.py`). The first request after a
**new image is deployed** is much slower than later cold starts. Lambda fetches the image from
ECR lazily, chunk by chunk, and loading torch plus the ~500 MB model reads many chunks. In the
measurement below that request took more than 60 s. The timeout is therefore 120 s; you only pay
for the time actually used.

```bash
aws lambda update-function-configuration --function-name clinical-deid   --memory-size 2048 --timeout 120 --query '[MemorySize,Timeout]'
aws lambda wait function-updated --function-name clinical-deid
```

New accounts may be limited to 3,008 MB; an error mentioning `MemorySize` means that quota.

### 7.5 Measure cold and warm latency (AC-03)

Any configuration change makes Lambda start new instances, so the next request is a cold start.
Each run below sends one cold request and five warm ones, then reads Lambda's own `REPORT` lines.
Because the model loads lazily, the cold cost shows up in the first request's `Duration`;
`Init Duration` only covers importing the code.

```bash
export FUNCTION_URL=$(aws lambda get-function-url-config --function-name clinical-deid   --query FunctionUrl --output text)
eval "$(aws configure export-credentials --profile "$AWS_PROFILE" --format env)"

# Force a cold start without changing the code.
aws lambda update-function-configuration --function-name clinical-deid   --description "latency run $(date +%s)" --query LastUpdateStatus
aws lambda wait function-updated --function-name clinical-deid

for i in 1 2 3 4 5 6; do
  time uvx awscurl==0.45 --service lambda --region "$AWS_REGION"     -X POST -H 'Content-Type: application/json'     -d '{"text": "Paciente Lucía Fernández, de 54 años, ingresó el 12/03/2025 en Teruel."}'     "${FUNCTION_URL}api/deidentify" > /dev/null
done
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION

# Lambda's measurements: Duration, Billed Duration, Max Memory Used, Init Duration (cold only).
# Wait a few seconds after the last request: logs reach CloudWatch with a short delay.
aws logs filter-log-events --log-group-name /aws/lambda/clinical-deid   --filter-pattern REPORT --start-time $(( ($(date +%s) - 900) * 1000 ))   --query 'events[].message' --output text
```

`time` reports the whole client round trip (`real`): `uvx` start-up, SigV4 signing and the
network from Spain, about 1 s. `Duration` is the time spent inside Lambda.

**Results (18 Nov 2026, synthetic 70-character note, `eu-west-1`):**

| Memory | Cold request: Lambda / client | Warm request: Lambda / client (median of 5) | Max memory used |
| --- | --- | --- | --- |
| 3,008 MB | 7.0 s / 8.5 s | 87 ms / 1.1 s | 935 MB |
| 2,048 MB | 9.1 s (7.9 s + 1.2 s init) / 10.7 s | 122 ms / 1.2 s | 936 MB |

The very first request after the T2.6 deployment (3,008 MB, 60 s timeout) hit the timeout at
60 s: that is the lazy image fetch described in 7.4, and it does not happen again until the next
deployment.

**Chosen memory: 2,048 MB, timeout 120 s.** Both sizes meet AC-03 (< 10 s excluding cold
starts) by a wide margin. Cost is practically the same, because Lambda bills memory × duration:
about 0.25 GB·s per warm request at 2,048 MB versus 0.26 GB·s at 3,008 MB. 2,048 MB is the smaller
reservation that still leaves more than 1 GB of headroom over the ~935 MB used. It is about
35 ms slower warm, which is invisible next to the ~1 s client round trip, and about 2 s slower
on a cold start. Design §9 proposed 3,008 MB "to tune after measuring": this is that tuning.

## 8. Turn on the LLM in the cascade (T3.5)

Until now the function runs **model only**: `LLM_ENABLED` is unset (default `false`), so every
uncertain entity is masked without calling an LLM. This section lets the Lambda role call
Claude Haiku 4.5 on Bedrock and then switches the cascade on. Nothing in the image changes:
the same code reads `LLM_ENABLED` at start-up.

### 8.1 Prerequisite: Bedrock works for the account

Bedrock must answer for your administrator user first. In the console (Bedrock → Playground,
`eu-west-1`) send one message to Claude Haiku 4.5, or from the CLI:

```bash
aws bedrock-runtime converse --model-id eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --messages '[{"role":"user","content":[{"text":"Responde solo: ok"}]}]' \
  --query 'output.message.content[0].text'
```

Do this with your own user, not the Lambda role. The first call to an Anthropic model on
the account also activates the model (the Marketplace subscription), and that step needs
permissions the Lambda role deliberately does not have. If it fails with `Error 002: Access
to Bedrock models is not allowed for this account`, the account is still blocked; stop here.

### 8.2 Why the policy names several EU regions

The model ID starts with `eu.`: it is a **cross-region inference profile**. The request goes
to `eu-west-1`, and Bedrock may serve it from another EU region that has capacity. The data
stays in the EU. This is the one accepted exception to the single-region rule (`eu-west-1`):
no resource is created elsewhere, but the inference may run in another EU region.

IAM checks two things on each call: the profile, and the foundation model in the region
that serves it. `infra/iam/lambda-bedrock-policy.json` therefore allows:

1. `bedrock:InvokeModel` on the EU profile of this one model, and
2. `bedrock:InvokeModel` on the same foundation model in each EU destination region, **only
   when the call comes through that profile** (`bedrock:InferenceProfileArn` condition).

There is no `*`: the role cannot call any other model, any other profile, or the foundation
model directly. Check that the regions in the file match the profile's current routing
(AWS may add regions); add any missing ARN to the file:

```bash
aws bedrock get-inference-profile \
  --inference-profile-identifier eu.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --query 'models[].modelArn' --output text | tr '\t' '\n'
```

### 8.3 Attach the policy to the Lambda role

An *inline* policy lives inside the role and is deleted with it. `sed` fills in the account
ID, as in step 2.

```bash
aws iam put-role-policy --role-name clinical-deid-lambda --policy-name bedrock-invoke \
  --policy-document "$(sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" infra/iam/lambda-bedrock-policy.json)"
aws iam get-role-policy --role-name clinical-deid-lambda --policy-name bedrock-invoke \
  --query 'PolicyDocument.Statement[].Resource'
```

### 8.4 Switch the cascade on

Environment variables belong to the function's configuration, not to the image, so
`deploy.yml` (which only updates the code) keeps them. **`--environment` replaces all
variables**, so always pass the full set. Since T4.2 the set includes the two login secrets
(section 9). An inline `Variables={LLM_ENABLED=true,...}` would delete them and lock every
user out. Use the JSON file of section 9 instead:

1. Add the LLM variables to the file next to the two secrets. The values are the defaults of
   design §10: `"LLM_ENABLED": "true"`, `"MAX_LLM_SENTENCES": "8"`, `"LLM_TIME_BUDGET_S": "45"`.
2. Apply the file with the same command as in section 9.2.
3. Delete the file.

`LLM_TIME_BUDGET_S` stops new LLM calls once 45 s have passed in one request (the remaining
uncertain entities are masked). The worst case, 45 s + one call (12 s) + a cold start, stays
under the 120 s timeout.

To go back to model only (for example if costs or errors rise), apply the same file with
`LLM_ENABLED` set to `"false"`, keeping the two secrets. It takes effect on the next request; no deployment is needed.

### 8.5 Check the cascade at the URL

Send a note with a doubtful entity. `metrics.n_llm` greater than 0 and entities with
`"source": "llm"` show that Bedrock answered:

```bash
export FUNCTION_URL=$(aws lambda get-function-url-config --function-name clinical-deid \
  --query FunctionUrl --output text)
eval "$(aws configure export-credentials --profile "$AWS_PROFILE" --format env)"
uvx awscurl==0.45 --service lambda --region "$AWS_REGION" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"text": "Paciente Lucía Fernández, de 54 años, ingresó el 12/03/2025 en Teruel. Remitida por la Dra. Ana Gil desde el centro de salud Delicias."}' \
  "${FUNCTION_URL}api/deidentify"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION
```

If `n_llm` is above 0 but no entity has `"source": "llm"`, every call failed and the fail-safe
masked them (the output is still safe). The usual cause is `AccessDeniedException`: compare
the regions in the policy with step 8.2.

### 8.6 Check that the logs hold metadata only

```bash
aws logs filter-log-events --log-group-name /aws/lambda/clinical-deid \
  --filter-pattern deidentify --start-time $(( ($(date +%s) - 900) * 1000 )) \
  --query 'events[].message' --output text
```

Each line must look like `deidentify chars=… entities=… n_llm=… latency_ms=…`. Searching for
a word of the note must return nothing:

```bash
aws logs filter-log-events --log-group-name /aws/lambda/clinical-deid \
  --filter-pattern '"Teruel"' --start-time $(( ($(date +%s) - 900) * 1000 )) \
  --query 'length(events)'   # expected: 0
```

Bedrock itself keeps no prompts: model invocation logging is off by default in the account
(Bedrock → Settings). Leave it off.

## 9. Demo login secrets (T4.2)

The login (design §7, ADR-0006) needs two environment variables on the function. Without them
every login fails (fail closed), so set them before the URL is opened.

- `DEMO_PASSWORD_HASH`: the argon2 hash of the demo password. The password itself is never stored.
- `SESSION_SECRET`: a random key that signs the session cookie. Anyone who knows it can forge a
  session, so it is as secret as the password.

Neither value ever goes in the repo, the chat or the shell history. Keep the password in a
password manager: the evaluator receives it privately with the submission (ADR-0012), never in the README.

### 9.1 Generate the values

From the repo root (a relative path fails from any other folder):

```bash
cd "/g/Mi unidad/BrAIn/TFM/clinical-deid-es"
uv run python scripts/hash_password.py   # asks twice, no echo; prints $argon2id$...
openssl rand -hex 32                     # 64 hex characters: the SESSION_SECRET
```

### 9.2 Set them on the function

**`--environment` replaces every variable.** First list the names already set (read-only).
Every name listed must go in the file too, or it is deleted. `null` means there are none:

```bash
aws lambda get-function-configuration --function-name clinical-deid \
  --query 'keys(Environment.Variables)'
```

Write the values to a temporary JSON file **outside the repo** with an editor, not with `echo`,
so they stay out of the shell history. The `$` signs in the hash also need no escaping in a file:

```bash
notepad ~/lambda-env.json
```

```json
{
  "Variables": {
    "DEMO_PASSWORD_HASH": "<the $argon2id$... line>",
    "SESSION_SECRET": "<the 64 hex characters>"
  }
}
```

Apply the file, then delete it at once:
- The AWS CLI is a Windows program, so it needs a Windows path after `file://`. It does not find a
  Git Bash path (`file://$HOME/...` → `/c/Users/...`).
- The `--query` prints only the variable **names**. Without it, the CLI would print the secrets.

```bash
aws lambda update-function-configuration --function-name clinical-deid \
  --environment file://C:/Users/<your user>/lambda-env.json \
  --query '{Status: LastUpdateStatus, Variables: keys(Environment.Variables)}'
rm ~/lambda-env.json
aws lambda wait function-updated --function-name clinical-deid
```

To change the password or revoke every session (for example after the grade or if a cookie
leaks), repeat 9.1–9.2 with a new hash or a new `SESSION_SECRET`.

### 9.3 Check the login at the URL

While the URL is still `AWS_IAM`, sign the requests with awscurl as in step 6.

```bash
export FUNCTION_URL=$(aws lambda get-function-url-config --function-name clinical-deid \
  --query FunctionUrl --output text)
eval "$(aws configure export-credentials --profile "$AWS_PROFILE" --format env)"

# Without a session: expected {"detail":"Not authenticated"}
uvx awscurl==0.45 --service lambda --region "$AWS_REGION" -X POST \
  -H 'Content-Type: application/json' -d '{"text":"Hola"}' "${FUNCTION_URL}api/deidentify"; echo
```

Run this line **on its own** and type the password. If it is pasted together with the following
lines, `read` takes the next pasted line as the password:

```bash
read -rs -p "Demo password: " PW; echo
```

```bash
uvx awscurl==0.45 --service lambda --region "$AWS_REGION" -X POST -i \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"demo\",\"password\":\"$PW\"}" "${FUNCTION_URL}api/login" \
  | grep -i -E 'HTTP/|set-cookie|status'
unset PW AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION
```

Expected output:
- `{"status":"ok"}`.
- `Set-Cookie: deid_session=…; HttpOnly; Max-Age=3600; Path=/; SameSite=strict; Secure`.
- The security headers next to them (CSP, `x-frame-options: DENY`, HSTS).

Other cases:
- A password with `"` or `\` breaks this JSON. Test such a password from the web page instead.
- Five wrong passwords lock the login for 15 minutes (429).

**Done on 28 Nov 2026:** both secrets were set (the function had no variables before) and the check
above passed. T5.4 does **not** need to repeat this section. It only switches the URL to `NONE` and
retests the login from the public URL, without awscurl.

## 10. Make the model public and update its card (T5.1)

No AWS here: this is the Hugging Face Hub. The deployment keeps working during and after these
steps, because `deploy.yml` downloads the weights of the revision pinned in `config/model.json`,
and a new commit that only changes `README.md` does not touch those weights.

1. Regenerate the model card from the committed reports (no token needed, nothing is uploaded):

   ```bash
   uv run python -m modeling.publish.publish_model \
     --run-log modeling/training/runs/run-1.json --card-only model-card.md
   ```

2. Upload it as the repository's `README.md` with a **write** token (create a fine-grained one
   for this repository only, and delete it afterwards). The CLI asks for the token with a hidden
   prompt:

   ```bash
   uvx --from huggingface_hub hf auth login
   uvx --from huggingface_hub hf upload ahrovira/clinical-deid-es-meddocan model-card.md README.md \
     --commit-message "Update model card (T5.1)"
   uvx --from huggingface_hub hf auth logout
   rm model-card.md
   ```

   Alternatively, on the model page: *Files and versions → Add file → Upload files*, renaming the
   file to `README.md` first.

3. Make the repository public: *Settings → Change model visibility → Make public*.

4. Check, from a private browser window (signed out), that
   <https://huggingface.co/ahrovira/clinical-deid-es-meddocan> shows the card and the files.

From now on `publish_model.py` refuses a full upload (it requires a private repository): that is
deliberate, a new training run would be published again as a new private repository.
`config/model.json` is not changed.

## Troubleshooting (seen during the first deployment)

| Error | Cause | Fix |
| --- | --- | --- |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` (deploy job) | The trust policy `sub` does not match GitHub's OIDC subject | Use the immutable format shown in step 2, then `update-assume-role-policy` |
| `The image manifest, config or layer media type … is not supported` (`create-function`) | The image was pushed as a manifest list with attestations | `deploy.yml` builds with `--provenance=false --sbom=false`; push a new image |
| `The image tag … already exists … immutable` | A run tried to reuse an existing tag | Tags include the run id (`<sha>-<run id>-<attempt>`); use the current `deploy.yml` |
| `awscurl: No credentials found` | awscurl does not read `aws login` sessions | Export them first with `aws configure export-credentials` (step 6) |
| `curl` prints `000` | `FUNCTION_URL` is empty (new terminal) | Repeat the shell setup and the `export FUNCTION_URL=…` line |
| `ExpiredToken` / expired session | The `aws login` session ended | `aws login --profile deid-admin` |
| Path like `C:/Program Files/Git/aws/lambda/...` | Git Bash path conversion | `export MSYS_NO_PATHCONV=1` |
| `Unable to load param file file:///c/Users/...` | The Windows AWS CLI does not understand Git Bash paths | Use `file://C:/Users/<user>/...` (section 9.2) |
| `can't open file '.../scripts/hash_password.py'` | Command run outside the repo root | `cd` to the repo root first (section 9.1) |
| Every login returns 401 after a configuration change | An `--environment` update without the two secrets removed them | Set the full set again from the JSON file (section 9.2) |

## Later lifecycle (design §9)

- **27 Nov (T5.4):** switch the URL to `--auth-type NONE` (`aws lambda update-function-url-config`)
  together with the app login (ADR-0006). The login secrets are already set (section 9, done 28 Nov);
  only check that `keys(Environment.Variables)` still lists both before opening.
- **After the grade:** delete the function, the image repository, the log group, both roles
  (with their inline policies), the OIDC provider and the GitHub environment.
