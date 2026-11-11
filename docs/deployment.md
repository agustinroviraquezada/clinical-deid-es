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

# Keep only the 5 most recent images so storage stays almost free.
aws ecr put-lifecycle-policy --repository-name clinical-deid --lifecycle-policy-text '{
  "rules": [{"rulePriority": 1, "description": "keep last 5 images",
             "selection": {"tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 5},
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
its own logs. Bedrock permission for a single model is added in week 3.

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

512 MB is enough for the hello world. Design §9 proposes 3,008 MB once the model is in the image.

**Reserved concurrency (design §8, OWASP LLM10).** This caps how many copies of the function
run at the same time, and with it the cost of a burst of requests. New accounts often have a
total limit of only 10 concurrent executions, and AWS requires 10 of them to stay unreserved.
Apply it once the quota increase requested in T1.1 is granted:

```bash
aws lambda put-function-concurrency --function-name clinical-deid \
  --reserved-concurrent-executions 5
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
# The version is pinned because this tool runs with your AWS credentials.
uvx awscurl==0.45 --profile "$AWS_PROFILE" --service lambda --region "$AWS_REGION" \
  "${FUNCTION_URL}api/health"
```

## Troubleshooting (seen during the first deployment)

| Error | Cause | Fix |
| --- | --- | --- |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` (deploy job) | The trust policy `sub` does not match GitHub's OIDC subject | Use the immutable format shown in step 2, then `update-assume-role-policy` |
| `The image manifest, config or layer media type … is not supported` (`create-function`) | The image was pushed as a manifest list with attestations | `deploy.yml` builds with `--provenance=false --sbom=false`; push a new image |
| `The image tag … already exists … immutable` | A run tried to reuse an existing tag | Tags include the run id (`<sha>-<run id>-<attempt>`); use the current `deploy.yml` |
| `ExpiredToken` / expired session | The `aws login` session ended | `aws login --profile deid-admin` |
| Path like `C:/Program Files/Git/aws/lambda/...` | Git Bash path conversion | `export MSYS_NO_PATHCONV=1` |

## Later lifecycle (design §9)

- **20 Nov:** switch the URL to `--auth-type NONE` (`aws lambda update-function-url-config`)
  together with the app login (ADR-0006).
- **After the grade:** delete the function, the image repository, the log group, both roles,
  the OIDC provider and the GitHub environment.
