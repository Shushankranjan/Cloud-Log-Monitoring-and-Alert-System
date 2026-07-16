# Cloud Log Monitoring & Alert System — PRD

## 1. Overview
A lightweight, AWS-native log monitoring and alerting system. Applications send structured logs to **Amazon CloudWatch Logs**. We use **CloudWatch Metrics**, **Alarms**, **Logs Insights**, and **Dashboards** to detect errors and visualize system health. Notifications are delivered via **SNS** to **email** and **Slack**.

## 2. Goals
- Centralize application logs from Lambda, Fargate, and API Gateway.
- Automatically detect errors and high failure rates.
- Notify the team via email and Slack within minutes.
- Provide a single dashboard for log volume, error count, and error rate.

## 3. Non-Goals
- Full SIEM or security-threat detection.
- Application Performance Monitoring (APM) / distributed tracing.
- ML-based anomaly detection.
- Multi-cloud or on-premise ingestion.

## 4. Components

| Component | AWS Service | Purpose |
|---|---|---|
| Log ingestion | **CloudWatch Logs** | Collect logs from Lambda, Fargate, API Gateway |
| Log parsing | **CloudWatch Logs Metric Filters** | Turn log events into metrics (e.g., `ERROR` count) |
| Query / search | **CloudWatch Logs Insights** | Ad-hoc error investigation |
| Visualization | **CloudWatch Dashboards** | Real-time charts and logs tables |
| Alerting | **CloudWatch Alarms → SNS** | Trigger notifications |
| Notifications | **SNS + Lambda / HTTPS** | Email and Slack messages |

## 5. Recommended Log Format
Use structured JSON logs so metric filters and dashboards are reliable:

```json
{
  "timestamp": "2026-07-15T10:00:00Z",
  "level": "ERROR",
  "service": "payment-service",
  "message": "Payment processing failed",
  "error": "TimeoutError",
  "requestId": "abc-123"
}
```

## 6. Alerting Rules

| Alarm | Source | Condition | Severity |
|---|---|---|---|
| High error rate | Metric filter on `level = ERROR` | > 5 errors in 5 minutes | High |
| High 5xx rate | API Gateway access logs | > 1% 5xx in 5 minutes | High |
| Lambda failures | Lambda `Errors` metric | > 3 failures in 5 minutes | Medium |

## 7. Notifications
- **Email**: SNS email subscription.
- **Slack**: SNS → Lambda / HTTPS endpoint → Slack webhook.
- Each alert includes the alarm name, reason, timestamp, and a link to the CloudWatch Dashboard.

## 8. Error Analysis
- **Dashboard widgets**:
  - Error count over time.
  - Error rate percentage.
  - Top error messages (via Logs Insights).
  - Errors grouped by service.
- **Investigation workflow**:
  1. Alarm fires.
  2. Click the link in Slack/email.
  3. Open the dashboard and filter by service and time range.
  4. Run a Logs Insights query to inspect raw error logs.

## 9. Milestones
1. Instrument applications to emit JSON logs.
2. Create CloudWatch log groups with retention (e.g., 14 days).
3. Set up metric filters for `ERROR` and `5xx` patterns.
4. Build a CloudWatch Dashboard.
5. Create CloudWatch Alarms and an SNS topic for email + Slack.
6. Write a runbook for common alerts.
7. Test end-to-end with a simulated error.

## 10. Success Metrics
- Logs appear in CloudWatch within 1 minute.
- Alerts trigger within 2–5 minutes of a threshold breach.
- Dashboard reflects current health in real time.
- All `ERROR` logs are queryable by service and request ID.
