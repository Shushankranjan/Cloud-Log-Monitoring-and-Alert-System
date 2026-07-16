#!/usr/bin/env python3
"""Simple real-time AWS/LocalStack dashboard for the Cloud Log Monitor stack."""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3

REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
MOCK_SLACK_URL = os.getenv("MOCK_SLACK_URL", "http://localhost:8081")

ALARM_NAME = os.getenv("ALARM_NAME", "cloud-log-monitor-high-error-rate-dev")
LOG_GROUP = os.getenv("LOG_GROUP", "/aws/lambda/cloud-log-monitor-sample-app-dev")
NAMESPACE = os.getenv("METRIC_NAMESPACE", "cloud-log-monitor/dev")
METRIC_NAME = os.getenv("METRIC_NAME", "ErrorCount")


def boto_client(service):
    """Create a boto3 client using the default credential chain.

    Set AWS_ENDPOINT_URL (e.g. http://localhost:4566) to talk to LocalStack.
    Otherwise credentials are read from the standard AWS sources.
    """
    kwargs = {"region_name": REGION}
    endpoint_url = os.getenv("AWS_ENDPOINT_URL")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client(service, **kwargs)


def get_alarm_state():
    try:
        cw = boto_client("cloudwatch")
        resp = cw.describe_alarms(AlarmNames=[ALARM_NAME])
        alarm = resp["MetricAlarms"][0]
        return {
            "name": alarm["AlarmName"],
            "state": alarm["StateValue"],
            "reason": alarm["StateReason"],
            "threshold": alarm["Threshold"],
        }
    except Exception as exc:
        return {"name": ALARM_NAME, "state": "UNKNOWN", "reason": str(exc), "threshold": None}


def get_error_trend():
    """Return the last 30 minutes of ErrorCount in 5-minute Sum periods."""
    try:
        cw = boto_client("cloudwatch")
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=30)
        resp = cw.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "e1",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": NAMESPACE,
                            "MetricName": METRIC_NAME,
                        },
                        "Period": 300,
                        "Stat": "Sum",
                    },
                }
            ],
            StartTime=start,
            EndTime=end,
        )
        results = resp.get("MetricDataResults", [])
        if results:
            timestamps = results[0].get("Timestamps", [])
            values = results[0].get("Values", [])
            return [
                {"timestamp": ts.isoformat(), "value": val}
                for ts, val in zip(timestamps, values)
            ]
        return []
    except Exception as exc:
        return [{"error": str(exc)}]


def get_error_metric(trend):
    """Current error count derived from the most recent trend data point."""
    if trend and "value" in trend[-1]:
        return {"value": trend[-1]["value"], "timestamp": trend[-1]["timestamp"]}
    return {"value": 0, "timestamp": None}


def get_recent_errors(limit=20):
    try:
        logs = boto_client("logs")
        resp = logs.filter_log_events(
            logGroupName=LOG_GROUP,
            filterPattern='{ $.level = "ERROR" }',
            limit=limit,
        )
        events = []
        for ev in resp.get("events", []):
            msg = ev["message"]
            if msg.startswith("{"):
                try:
                    parsed = json.loads(msg)
                    events.append(
                        {
                            "timestamp": datetime.fromtimestamp(
                                ev["timestamp"] / 1000, tz=timezone.utc
                            ).isoformat(),
                            "level": parsed.get("level"),
                            "message": parsed.get("message"),
                            "error": parsed.get("error"),
                            "requestId": parsed.get("requestId"),
                        }
                    )
                    continue
                except json.JSONDecodeError:
                    pass
            events.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        ev["timestamp"] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "level": "ERROR",
                    "message": msg,
                }
            )
        return events
    except Exception as exc:
        return [{"error": str(exc)}]


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cloud Log Monitor Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --ok: #22c55e;
      --alarm: #ef4444;
      --insufficient: #f59e0b;
      --border: #334155;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 2rem;
    }
    h1 { margin-top: 0; }
    .subtitle { color: var(--muted); margin-top: -0.5rem; margin-bottom: 1.5rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .card {
      background: var(--card);
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    .card h2 { margin-top: 0; font-size: 0.95rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .big { font-size: 2.5rem; font-weight: bold; }
    .badge {
      display: inline-block;
      padding: 0.35rem 0.75rem;
      border-radius: 999px;
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #fff;
      background: var(--muted);
    }
    .state-OK { background: var(--ok); }
    .state-ALARM { background: var(--alarm); }
    .state-INSUFFICIENT_DATA { background: var(--insufficient); }
    .state-UNKNOWN { background: var(--muted); }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; color: var(--muted); }
    .reason { margin-top: 0.75rem; line-height: 1.4; }
    .chart-wrapper { position: relative; height: 300px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 0.65rem; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-size: 0.85rem; text-transform: uppercase; }
    .timestamp { white-space: nowrap; color: var(--muted); }
    .last-updated { color: var(--muted); font-size: 0.85rem; margin-top: 1rem; }
    .error-banner { color: var(--alarm); margin-top: 0.5rem; }
  </style>
</head>
<body>
  <h1>Cloud Log Monitor Dashboard</h1>
  <p class="subtitle">AWS mode by default. Set <code>AWS_ENDPOINT_URL=http://localhost:4566</code> for LocalStack. Auto-refreshes every 10s.</p>

  <div class="grid">
    <div class="card">
      <h2>Alarm State</h2>
      <div id="alarm-state" class="badge state-UNKNOWN">-</div>
      <div id="alarm-name" class="mono" style="margin-top: 0.75rem;"></div>
      <div id="alarm-threshold" class="mono"></div>
      <div id="alarm-reason" class="reason"></div>
    </div>

    <div class="card">
      <h2>Current Error Count</h2>
      <div id="error-count" class="big">-</div>
      <div id="error-timestamp" class="mono"></div>
    </div>
  </div>

  <div class="card" style="margin-bottom: 1.5rem;">
    <h2>Error Count Trend (last 30 minutes, 5-min periods)</h2>
    <div class="chart-wrapper">
      <canvas id="error-chart"></canvas>
    </div>
  </div>

  <div class="card">
    <h2>Recent ERROR Logs</h2>
    <table>
      <thead>
        <tr><th>Time</th><th>Message</th><th>Error</th><th>Request ID</th></tr>
      </thead>
      <tbody id="error-logs"></tbody>
    </table>
  </div>

  <div class="last-updated">Last updated: <span id="last-updated">-</span></div>

  <script>
    let chart = null;

    function initChart(labels, data) {
      const ctx = document.getElementById('error-chart').getContext('2d');
      chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'ErrorCount',
            data: data,
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 4,
            pointBackgroundColor: '#ef4444',
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: {
              ticks: { color: '#94a3b8' },
              grid: { color: '#334155' }
            },
            y: {
              ticks: { color: '#94a3b8', stepSize: 1 },
              grid: { color: '#334155' },
              beginAtZero: true
            }
          }
        }
      });
    }

    async function refresh() {
      try {
        const res = await fetch('/api/data');
        const data = await res.json();

        const alarm = data.alarm || {};
        const alarmEl = document.getElementById('alarm-state');
        alarmEl.textContent = alarm.state || 'N/A';
        alarmEl.className = 'badge state-' + (alarm.state || 'UNKNOWN');
        document.getElementById('alarm-name').textContent = alarm.name || '';
        document.getElementById('alarm-threshold').textContent = alarm.threshold ? 'Threshold: ' + alarm.threshold : '';
        document.getElementById('alarm-reason').textContent = alarm.reason || '';

        const metric = data.metric || {};
        document.getElementById('error-count').textContent =
          typeof metric.value === 'number' ? metric.value : 'N/A';
        document.getElementById('error-timestamp').textContent = metric.timestamp || '';

        const trend = Array.isArray(data.trend) ? data.trend : [];
        const labels = trend.map(p => p.timestamp ? new Date(p.timestamp).toLocaleTimeString() : '');
        const values = trend.map(p => typeof p.value === 'number' ? p.value : 0);
        if (chart) {
          chart.data.labels = labels;
          chart.data.datasets[0].data = values;
          chart.update();
        } else {
          initChart(labels, values);
        }

        const logsEl = document.getElementById('error-logs');
        const errors = Array.isArray(data.errors) ? data.errors : [];
        if (errors.length === 0) {
          logsEl.innerHTML = '<tr><td colspan="4" class="mono">No ERROR logs found.</td></tr>';
        } else {
          logsEl.innerHTML = errors.map(e => `
            <tr>
              <td class="timestamp">${e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ''}</td>
              <td>${e.message || ''}</td>
              <td class="mono">${e.error || ''}</td>
              <td class="mono">${e.requestId || ''}</td>
            </tr>
          `).join('');
        }

        document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
      } catch (err) {
        document.getElementById('alarm-state').textContent = 'Error';
        document.getElementById('alarm-state').className = 'badge state-UNKNOWN';
        console.error(err);
      }
    }

    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        elif self.path == "/api/data":
            trend = get_error_trend()
            data = {
                "alarm": get_alarm_state(),
                "metric": get_error_metric(trend),
                "trend": trend,
                "errors": get_recent_errors(),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard")
