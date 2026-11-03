import sys
import json
import requests

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/simulate_clickup_webhook.py <task_id> [new_status]")
        sys.exit(1)

    task_id = sys.argv[1]
    new_status = sys.argv[2] if len(sys.argv) > 2 else "in_progress"

    payload = {
        "event": "taskStatusUpdated",
        "task_id": task_id,
        "history_items": [
            {
                "field": "status",
                "after": {"status": new_status, "type": "custom"}
            }
        ]
    }

    url = "http://127.0.0.1:8000/webhooks/clickup/task-updated"
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
