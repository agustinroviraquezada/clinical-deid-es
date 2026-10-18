# ADR-0005 · Deployment on AWS Lambda with a container image

- **Status:** Accepted · 17 Oct 2026

## Context
Total budget of €50, little AWS experience, low-traffic demo, public access only from submission to grading. App Runner no longer accepts new customers since 30 Apr 2026.

## Decision
Lambda with a container image (ECR) and a Function URL in eu-west-1, model baked into the image, CD with GitHub Actions and OIDC. URL auth `AWS_IAM` during development and `NONE` from 20 Nov.

## Alternatives considered
ECS Express Mode: load balancer and Fargate are billed per hour. Lightsail: little RAM on cheap plans. EC2: too much administration.

## Consequences
Near-zero cost at rest; slow cold starts (accepted: they do not count towards the 10 s limit). Risk: reduced quotas on new accounts.
