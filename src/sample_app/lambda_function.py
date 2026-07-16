import json
import uuid
import datetime


def log_json(level, service, message, error=None, extra=None):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "level": level,
        "service": service,
        "message": message,
        "requestId": str(uuid.uuid4()),
    }
    if error:
        entry["error"] = error
    if extra:
        entry.update(extra)
    print(json.dumps(entry), flush=True)


def lambda_handler(event, context):
    service = "sample-app"
    log_json("INFO", service, "Processing request", extra={"event": event})

    if event.get("error"):
        log_json(
            "ERROR",
            service,
            "Simulated failure for testing",
            error="SimulatedError",
        )
        raise RuntimeError("Simulated error for alert testing")

    log_json("INFO", service, "Request completed successfully")
    return {"statusCode": 200, "body": json.dumps({"ok": True})}
