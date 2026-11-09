# Deployment runbook (AWS Lambda)

How to create the AWS resources of design §9 / ADR-0005 once, by hand, with the AWS CLI. After
this setup, every push to `main` is deployed by `.github/workflows/deploy.yml`.

Everything lives in **`eu-west-1`**. Resource names: ECR repository `clinical-deid`, Lambda
function `clinical-deid`, IAM roles `clinical-deid-github-deploy` and `clinical-deid-lambda`.

## How the pieces fit

```
push to main ──► GitHub Actions (deploy.yml)
                   │ 1. docker build + smoke test with the Lambda emulator
                   │ 2. asks GitHub for a short-lived OIDC token
                   ▼
                 AWS STS ── trust policy: only repo …/clinical-deid-es, branch main
                   │ temporary credentials of role clinical-deid-github-deploy
                   ▼
                 ECR (push image :<sha>) ──► Lambda update-function-code
                                                │
                 Function URL (auth AWS_IAM) ◄──┘  only signed requests get in
```

No AWS access keys are stored in GitHub: OIDC exchanges a token that GitHub signs for each run
for credentials that expire within an hour.

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
- AWS CLI v2 configured with an administrator identity (not the root user), and `gh` logged in.
- Run the commands from the repository root in Git Bash (or a Codespace).

```bash
export AWS_REGION=eu-west-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "$ACCOUNT_ID"   # check it is the project account before going on
```

## 1. ECR repository (where images are stored)

```bash
aws ecr create-repository --repository-name clinical-deid \
  --image-scanning-configuration scanOnPush=true

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

The deploy role can only be assumed from `main` of this repository (`infra/iam/github-oidc-trust.json`).
It can only push to the `clinical-deid` repository and update the `clinical-deid` function
(`infra/iam/github-deploy-policy.json`).

```bash
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" infra/iam/github-oidc-trust.json > /tmp/trust.json
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" infra/iam/github-deploy-policy.json > /tmp/deploy-policy.json

aws iam create-role --role-name clinical-deid-github-deploy \
  --assume-role-policy-document file:///tmp/trust.json
aws iam put-role-policy --role-name clinical-deid-github-deploy \
  --policy-name deploy --policy-document file:///tmp/deploy-policy.json
```

## 3. First run: push the image only

The repository variables are not secret (an ARN is not a credential). The workflow reads them
with `vars.*`.

```bash
gh variable set AWS_DEPLOY_ROLE_ARN --body "arn:aws:iam::$ACCOUNT_ID:role/clinical-deid-github-deploy"
gh variable set ECR_REPOSITORY --body clinical-deid
gh workflow run deploy.yml --ref main
gh run watch
```

`LAMBDA_FUNCTION_NAME` is not set yet, so the run builds, tests and pushes the image, then skips
the Lambda update. Copy the image URI:

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
uvx awscurl --service lambda --region "$AWS_REGION" "${FUNCTION_URL}api/health"
```

## Later lifecycle (design §9)

- **20 Nov:** switch the URL to `--auth-type NONE` (`aws lambda update-function-url-config`)
  together with the app login (ADR-0006).
- **After the grade:** delete the function, the image repository and both roles.
