# Runtime: Imports the HTTP client used to call the locally running FastAPI endpoint.
# Architecture: Models the outbound request that GoHighLevel would send to PulseOps.
# Plain English: Gives this test script a way to send web requests.
import requests
# Runtime: Imports JSON support for payload-oriented test data.
# Architecture: Keeps the simulator compatible with JSON webhook contracts.
# Plain English: Provides standard-library JSON utilities for this integration test.
import json
# Runtime: Imports command-line argument access.
# Architecture: Lets operators supply a student name and external contact ID at runtime.
# Plain English: Reads values typed after the script name.
import sys

# Configuration - Update with your actual values for local testing
# Runtime: Stores the base address of the local API process.
# Architecture: Points the simulator at the FastAPI application under test.
# Plain English: Names the server this script will contact.
APP_URL = "http://localhost:8000"
# Runtime: Builds the webhook route from the shared base URL.
# Architecture: Targets the GoHighLevel deal-won adapter used by onboarding.
# Plain English: Chooses the exact endpoint that receives the fake event.
WEBHOOK_ENDPOINT = f"{APP_URL}/webhooks/ghl/deal-won"

# Runtime: Defines a reusable function that sends one synthetic webhook.
# Architecture: Exercises the same HTTP boundary used by the production GHL integration.
# Plain English: Packages all steps needed to pretend a deal was won.
def send_mock_webhook(student_name, ghl_id):
    # Runtime: Creates the JSON-compatible event body passed to requests.
    # Architecture: Supplies the minimum student identity data expected by the API.
    # Plain English: Describes the new student in the fake webhook.
    payload = {
        "name": student_name,
        "ghl_contact_id": ghl_id,
        "cohort": "Alpha"
    }
    # Runtime: Starts exception handling around network and response parsing operations.
    # Architecture: Keeps a local simulator failure from producing an unreadable traceback.
    # Plain English: Attempts the request while preparing to report errors.
    try:
        # Runtime: Sends an HTTP POST and serializes payload as JSON.
        # Architecture: Invokes FastAPI's external webhook contract over HTTP.
        # Plain English: Delivers the pretend deal event to the application.
        response = requests.post(WEBHOOK_ENDPOINT, json=payload)
        # Runtime: Prints status and decoded response returned by the API.
        # Architecture: Makes integration behavior observable during local testing.
        # Plain English: Shows whether the server accepted the event.
        print(f"Sent: {student_name} | Status: {response.status_code} |_ {response.json()}")
    # Runtime: Handles any request or JSON-decoding exception.
    # Architecture: Provides an operator-friendly failure signal for test runs.
    # Plain English: Reports what went wrong instead of hiding it.
    except Exception as e:
        print(f"Error sending webhook: {e}")

# Runtime: Restricts CLI execution to direct invocation rather than module import.
# Architecture: Prevents test requests when another Python module imports this helper.
# Plain English: Runs the command-line portion only when this file is executed.
if __name__ == "__main__":
    # Runtime: Checks that both required positional arguments were supplied.
    # Architecture: Protects the webhook builder from incomplete test input.
    # Plain English: Requires a name and a GHL contact ID.
    if len(sys.argv) < 3:
        print("Usage: python simulate_ghl_traffic.py <name> <ghl_id>")
    # Runtime: Passes command-line values into the webhook function.
    # Architecture: Connects operator input to the simulated integration event.
    # Plain English: Sends the supplied student details.
    else:
        send_mock_webhook(sys.argv[1], sys.argv[2])
