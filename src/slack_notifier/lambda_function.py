import json
import os
import urllib.request

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]


def lambda_handler(event, context):
    """
    Receives an SNS message (typically from CloudWatch Alarms) and posts a
    formatted notification to Slack.
    """
    try:
        sns_message = event["Records"][0]["Sns"]["Message"]
    except (KeyError, IndexError):
        sns_message = json.dumps(event, indent=2)

    # If the SNS message is a JSON CloudWatch alarm, pretty-print key fields.
    try:
        alarm = json.loads(sns_message)
        if "AlarmName" in alarm:
            text = (
                f"*CloudWatch Alarm: {alarm.get('AlarmName')}*\n"
                f"• State: {alarm.get('NewStateValue')}\n"
                f"• Reason: {alarm.get('NewStateReason')}\n"
                f"• Region: {alarm.get('Region')}\n"
                f"• Time: {alarm.get('StateChangeTime')}"
            )
        else:
            text = sns_message
    except json.JSONDecodeError:
        text = sns_message

    payload = {
        "username": "cloudwatch-alerts",
        "icon_emoji": ":warning:",
        "text": text,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        response.read()

    return {"statusCode": 200, "body": "Notification sent to Slack"}
