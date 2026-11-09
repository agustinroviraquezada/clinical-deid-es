"""The Lambda entry point translates a Function URL event into a FastAPI request."""

import json

import clinical_deid


def _function_url_event(path: str, method: str = "GET") -> dict:
    """Minimal Lambda Function URL event (payload format 2.0)."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "example.lambda-url.eu-west-1.on.aws"},
        "requestContext": {
            "domainName": "example.lambda-url.eu-west-1.on.aws",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "test-request",
            "routeKey": "$default",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


def test_health_through_lambda_handler():
    from clinical_deid.api.lambda_handler import handler

    response = handler(_function_url_event("/api/health"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {
        "status": "ok",
        "version": clinical_deid.__version__,
    }


def test_unknown_path_returns_404():
    from clinical_deid.api.lambda_handler import handler

    response = handler(_function_url_event("/does-not-exist"), None)

    assert response["statusCode"] == 404
