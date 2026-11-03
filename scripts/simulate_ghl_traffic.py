import requests
import json
import sys

# Configuration - Update with your actual values for local testing
APP_URL = "http://localhost:8000"
WEBHOOK_ENDPOINT = f"{APP_URL}/webhooks/ghl/deal-won"

def send_mock_webhook(student_name, ghl_id):
    payload = {
        "name": student_name,
        "ghl_contact_id": ghl_id,
        "cohort": "Alpha"
    }
    try:
        response = requests.post(WEBHOOK_ENDPOINT, json=payload)
        print(f"Sent: {student_name} | Status: {response.status_code} |_ {response.json()}")
    except Exception as e:
        print(f"Error sending webhook: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python simulate_ghl_traffic.py <name> <ghl_id>")
    else:
        send_mock_webhook(sys.argv[1], sys.argv[2])
