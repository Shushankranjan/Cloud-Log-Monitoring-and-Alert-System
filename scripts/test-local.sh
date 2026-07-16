#!/usr/bin/env bash
# Run a full end-to-end test of the monitoring stack against LocalStack.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

# Use awslocal from the venv — it patches botocore to use query-protocol for
# CloudWatch (which LocalStack expects) instead of smithy-rpc-v2-cbor.
AWSLOCAL="${REPO_ROOT}/.venv/bin/awslocal"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
ENDPOINT_URL="http://localhost:4566"

PROJECT_NAME="${PROJECT_NAME:-cloud-log-monitor}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
SAMPLE_APP_NAME="${PROJECT_NAME}-sample-app-${ENVIRONMENT}"
SLACK_BOT_NAME="${PROJECT_NAME}-slack-notifier-${ENVIRONMENT}"
ALARM_NAME="${PROJECT_NAME}-high-error-rate-${ENVIRONMENT}"

echo "=== Starting LocalStack ==="
docker compose up -d

echo "=== Waiting for LocalStack to be ready ==="
until curl -sf "${ENDPOINT_URL}/_localstack/health" >/dev/null 2>&1; do
  sleep 2
done
echo "LocalStack is ready"

echo "=== Waiting for mock Slack endpoint to be ready ==="
until docker run --rm --network localstack curlimages/curl:8.6.0 \
  --silent --fail --output /dev/null http://mock-slack:8080 2>/dev/null; do
  sleep 2
done
echo "Mock Slack is ready"

echo "=== Building Lambda packages ==="
./scripts/package.sh

echo "=== Preparing local Terraform variables ==="
cat > terraform/terraform.local.tfvars <<EOF
project_name      = "${PROJECT_NAME}"
environment       = "${ENVIRONMENT}"
aws_region        = "us-east-1"
alert_email       = "test@example.com"
slack_webhook_url = "http://mock-slack:8080"
EOF

echo "=== Deploying with tflocal ==="
cd terraform
"${REPO_ROOT}/.venv/bin/tflocal" init -upgrade
"${REPO_ROOT}/.venv/bin/tflocal" apply -auto-approve -var-file="${REPO_ROOT}/terraform/terraform.local.tfvars"
cd "${REPO_ROOT}"

echo "=== Invoking sample app with error payload ==="
for i in {1..6}; do
  "${AWSLOCAL}" lambda invoke \
    --function-name "${SAMPLE_APP_NAME}" \
    --payload '{"error": true}' \
    /tmp/response.json >/dev/null 2>&1 || true
done

echo "=== Publishing a test alarm to SNS to test the Slack path ==="
SNS_TOPIC_ARN=$("${AWSLOCAL}" sns list-topics \
  --query 'Topics[0].TopicArn' --output text)
"${AWSLOCAL}" sns publish \
  --topic-arn "${SNS_TOPIC_ARN}" \
  --message '{"AlarmName":"local-test-alarm","NewStateValue":"ALARM","NewStateReason":"LocalStack test trigger","Region":"us-east-1","StateChangeTime":"2026-07-15T00:00:00Z"}' \
  >/dev/null 2>&1 || true

sleep 5

echo ""
echo "=== CloudWatch alarm state ==="
"${AWSLOCAL}" cloudwatch describe-alarms \
  --alarm-names "${ALARM_NAME}" \
  --query 'MetricAlarms[0].[AlarmName,StateValue,StateReason]' \
  --output text 2>/dev/null || true

echo ""
echo "=== Sample app logs (last 20 lines) ==="
# logs tail is a v2-only subcommand; the Logs service uses json protocol so the
# system aws CLI v2 works fine here (unlike cloudwatch which needs awslocal).
aws --endpoint-url="${ENDPOINT_URL}" logs tail "/aws/lambda/${SAMPLE_APP_NAME}" --since 10m --format short 2>/dev/null || true

echo ""
echo "=== Slack notifier logs (last 20 lines) ==="
aws --endpoint-url="${ENDPOINT_URL}" logs tail "/aws/lambda/${SLACK_BOT_NAME}" --since 10m --format short 2>/dev/null || true

echo ""
echo "=== Mock Slack captures ==="
docker logs mock-slack --tail 40 2>/dev/null || true

echo ""
echo "=== Test complete ==="
echo "To clean up, run: docker compose down -v"