# Runtime: Provides access to command-line arguments.
# Architecture: Lets operators choose which ClickUp task and status to simulate.
# Plain English: Reads values entered after the script name.
import sys
# Runtime: Provides JSON support for webhook-shaped test payloads.
# Architecture: Keeps the simulator aligned with ClickUp's JSON event format.
# Plain English: Supplies standard JSON utilities.
import json
# Runtime: Provides synchronous HTTP requests to the local FastAPI service.
# Architecture: Exercises the ClickUp webhook ingress boundary.
# Plain English: Lets this script send a request to the app.
import requests

# Runtime: Defines the command-line entrypoint as a function.
# Architecture: Keeps setup reusable and import-safe.
# Plain English: Groups the steps for generating one fake event.
def main():
    # Runtime: Validates that a task ID argument exists before indexing argv.
    # Architecture: Prevents malformed test events from reaching the webhook handler.
    # Plain English: Requires the operator to identify a task.
    if len(sys.argv) < 2:
        print("Usage: python scripts/simulate_clickup_webhook.py <task_id> [new_status]")
        # Runtime: Terminates with a non-zero process code for invalid CLI usage.
        # Architecture: Allows automation to detect that the simulator was called incorrectly.
        # Plain English: Stops immediately when no task ID was supplied.
        sys.exit(1)

    # Runtime: Reads the required task identifier from the command line.
    # Architecture: Correlates the simulated event with a Student's ClickUp task.
    # Plain English: Chooses which task changed.
    task_id = sys.argv[1]
    # Runtime: Selects a caller-provided status or a useful default.
    # Architecture: Models ClickUp status transitions without requiring a second argument.
    # Plain English: Uses in_progress unless another status is requested.
    new_status = sys.argv[2] if len(sys.argv) > 2 else "in_progress"

    # Runtime: Builds the nested dictionary that requests will serialize as JSON.
    # Architecture: Mirrors ClickUp's taskStatusUpdated webhook schema.
    # Plain English: Describes the fake status-change event.
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

    # Runtime: Identifies the local ClickUp webhook route.
    # Architecture: Sends test traffic through the same FastAPI adapter as production events.
    # Plain English: Chooses where to post the fake event.
    url = "http://127.0.0.1:8000/webhooks/clickup/task-updated"
    # Runtime: Wraps network access and response decoding in error handling.
    # Architecture: Makes local integration failures visible without an opaque crash.
    # Plain English: Attempts delivery and prepares to report problems.
    try:
        # Runtime: Sends the payload with HTTP POST and JSON serialization.
        # Architecture: Invokes the ClickUp-to-Postgres synchronization boundary.
        # Plain English: Delivers the pretend status update.
        response = requests.post(url, json=payload)
        # Runtime: Prints the HTTP result for quick smoke-test verification.
        # Architecture: Exposes the API contract outcome to operators.
        # Plain English: Shows the server's status code.
        print(f"Status Code: {response.status_code}")
        # Runtime: Decodes and prints the response body.
        # Architecture: Helps verify FastAPI's returned validation or processing result.
        # Plain English: Displays what the server said.
        print(f"Response: {response.json()}")
    # Runtime: Catches transport and response parsing errors.
    # Architecture: Keeps the test utility diagnosable when dependencies are unavailable.
    # Plain English: Prints a short error instead of stopping silently.
    except Exception as e:
        print(f"Error: {e}")

# Runtime: Runs main only for direct command-line use.
# Architecture: Keeps importing the simulator from executing a request.
# Plain English: Starts the simulator when this file is launched.
if __name__ == "__main__":
    main()
