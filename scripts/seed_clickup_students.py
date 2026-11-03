# Runtime: Provides environment-variable access for deployment credentials.
# Architecture: Reads secrets and IDs supplied by Docker or local configuration.
# Plain English: Lets the script find ClickUp settings without hardcoding them.
import os
from pathlib import Path
# Runtime: Provides reliable filesystem path construction across operating systems.
# Architecture: Locates the project-level .env file independently of the shell directory.
# Plain English: Helps build the path to the configuration file.
import requests
# Runtime: Provides HTTP calls to ClickUp's REST API.
# Architecture: Implements the outbound integration used to create student tasks.
# Plain English: Sends the seed records to ClickUp.
from dotenv import load_dotenv
# Runtime: Loads key/value pairs from a local .env file into the process environment.
# Architecture: Supports the same configuration convention used by the application.
# Plain English: Makes local secrets available to this script.

# Explicitly load .env from the project root
# Runtime: Resolves the repository root and appends the conventional environment filename.
# Architecture: Makes configuration loading independent of the current working directory.
# Plain English: Finds the project's .env file.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
# Runtime: Reads variables from the resolved dotenv file.
# Architecture: Supplies ClickUp credentials without changing application code.
# Plain English: Loads local configuration into the environment.
load_dotenv(dotenv_path=ENV_PATH)

# Runtime: Reads the ClickUp API token from process configuration.
# Architecture: Authenticates outbound requests to the ClickUp integration.
# Plain English: Gets the secret needed to call ClickUp.
CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
# Runtime: Reads the target ClickUp list identifier.
# Architecture: Determines where onboarding tasks will be created.
# Plain English: Gets the destination list.
CLICKUP_LIST_ID = os.getenv("CLICKUP_DEFAULT_LIST_ID")

# Runtime: Builds common HTTP headers for every ClickUp request.
# Architecture: Applies authentication and JSON content negotiation consistently.
# Plain English: Tells ClickUp who is calling and what format is sent.
HEADERS = {
    "Authorization": CLICKUP_API_TOKEN,
    "Content-Type": "application/json"
}

# Runtime: Defines deterministic sample records for local/demo onboarding.
# Architecture: Exercises the same task fields used by the operational student workflow.
# Plain English: Lists fake students that will become ClickUp tasks.
STUDENTS_TEST_DATA = [
    {
        "name": "Marcus Vance",
        "email": "marcus.vance@example.com",
        "phone": "+1-415-555-0192",
        "program": "High-Ticket Agency Sprint",
        "cohort": "Cohort 8",
        "deal_value": "$8,500",
        "payment_plan": "Paid in Full",
        "health_score": 95,
        "health_status": "Green (On Track)",
        "priority": 3,  # Normal
        "csm": "Sarah Lin"
    },
    {
        "name": "Elena Rostova",
        "email": "elena.rostova@example.com",
        "phone": "+1-312-555-0144",
        "program": "Scale Mastermind",
        "cohort": "Cohort 8",
        "deal_value": "$7,500",
        "payment_plan": "3-Pay Plan ($2,500/mo)",
        "health_score": 88,
        "health_status": "Green (On Track)",
        "priority": 3,
        "csm": "Jordan Bell"
    },
    {
        "name": "Derek Chen",
        "email": "derek.chen@example.com",
        "phone": "+1-206-555-0187",
        "program": "Remote Closer Academy",
        "cohort": "Cohort 9",
        "deal_value": "$6,000",
        "payment_plan": "Paid in Full",
        "health_score": 64,
        "health_status": "Amber (Missed 1 Touchpoint)",
        "priority": 2,  # High
        "csm": "Sarah Lin"
    },
    {
        "name": "Chloe Davenport",
        "email": "chloe.d@example.com",
        "phone": "+1-646-555-0112",
        "program": "High-Ticket Agency Sprint",
        "cohort": "Cohort 8",
        "deal_value": "$9,000",
        "payment_plan": "4-Pay Plan ($2,250/mo)",
        "health_score": 42,
        "health_status": "Red Alert (Payment Failed)",
        "priority": 1,  # Urgent
        "csm": "Alex Rivera"
    },
    {
        "name": "Liam O'Connor",
        "email": "liam.oc@example.com",
        "phone": "+1-617-555-0199",
        "program": "Executive RevOps Intensive",
        "cohort": "Cohort 1",
        "deal_value": "$12,000",
        "payment_plan": "Paid in Full",
        "health_score": 98,
        "health_status": "Green (Power User)",
        "priority": 3,
        "csm": "Alex Rivera"
    },
    {
        "name": "Fatima Al-Mansoor",
        "email": "fatima.m@example.com",
        "phone": "+1-713-555-0165",
        "program": "Scale Mastermind",
        "cohort": "Cohort 8",
        "deal_value": "$8,000",
        "payment_plan": "2-Pay Plan ($4,000/mo)",
        "health_score": 75,
        "health_status": "Amber (Delayed Milestone)",
        "priority": 2,
        "csm": "Jordan Bell"
    },
    {
        "name": "Julian Mercado",
        "email": "julian.mercado@example.com",
        "phone": "+1-305-555-0128",
        "program": "Remote Closer Academy",
        "cohort": "Cohort 9",
        "deal_value": "$6,000",
        "payment_plan": "Paid in Full",
        "health_score": 35,
        "health_status": "Red Alert (2 Weeks Inactive)",
        "priority": 1,
        "csm": "Sarah Lin"
    },
    {
        "name": "Sophie Tremblay",
        "email": "sophie.t@example.com",
        "phone": "+1-438-555-0176",
        "program": "High-Ticket Agency Sprint",
        "cohort": "Cohort 8",
        "deal_value": "$6,000",
        "payment_plan": "3-Pay Plan ($2,000/mo)",
        "health_score": 91,
        "health_status": "Green (On Track)",
        "priority": 3,
        "csm": "Jordan Bell"
    },
    {
        "name": "Trevor Brooks",
        "email": "trevor.b@example.com",
        "phone": "+1-512-555-0131",
        "program": "Executive RevOps Intensive",
        "cohort": "Cohort 1",
        "deal_value": "$11,000",
        "payment_plan": "Financing ($1,100/mo)",
        "health_score": 20,
        "health_status": "Red Alert (Dispute / Cancellation)",
        "priority": 1,
        "csm": "Alex Rivera"
    },
    {
        "name": "Aaliyah Patel",
        "email": "aaliyah.patel@example.com",
        "phone": "+1-404-555-0149",
        "program": "Scale Mastermind",
        "cohort": "Cohort 9",
        "deal_value": "$7,500",
        "payment_plan": "Paid in Full",
        "health_score": 100,
        "health_status": "Green (Perfect Attendance)",
        "priority": 3,
        "csm": "Sarah Lin"
    }
]

# Runtime: Defines the batch seeding operation.
# Architecture: Provides a repeatable integration fixture for the ClickUp-backed workflow.
# Plain English: Creates tasks for all sample students.
def seed_clickup():
    # Runtime: Validates both required configuration values before making API calls.
    # Architecture: Prevents unauthenticated or misrouted writes to ClickUp.
    # Plain English: Stops with guidance when setup is incomplete.
    if not CLICKUP_API_TOKEN or not CLICKUP_LIST_ID:
        print("[ERROR] Please set CLICKUP_API_TOKEN and CLICKUP_DEFAULT_LIST_ID in your .env file.")
        return

    # Runtime: Interpolates the configured list ID into ClickUp's task-creation endpoint.
    # Architecture: Routes all seeded onboarding records to one operational list.
    # Plain English: Chooses the ClickUp URL used for creating tasks.
    url = f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task"

    # Runtime: Iterates through each fixture record to create one external task.
    # Architecture: Translates database-like student data into ClickUp work items.
    # Plain English: Processes students one at a time.
    for student in STUDENTS_TEST_DATA:
        # Runtime: Formats profile and operational fields as ClickUp Markdown.
        # Architecture: Produces a human-readable task body for CSMs.
        # Plain English: Writes the details people will see in the task.
        markdown_body = f"""### Student Onboarding & Health Profile
* **Email:** `{student['email']}`
* **Phone:** `{student['phone']}`
* **Program:** {student['program']} ({student['cohort']})
* **Deal Value:** {student['deal_value']} ({student['payment_plan']})
* **Assigned CSM:** **{student['csm']}**

---
### Operational Signals
* **Health Score:** `{student['health_score']}/100`
* **Current Status:** `{student['health_status']}`
* **Automated Escalation Rule:** {"Active - Escalate to Slack" if student['health_score'] < 50 else "Normal Pacing"}
"""
        # Runtime: Builds the JSON request body, including tags and priority.
        # Architecture: Maps health signals into ClickUp's task-management model.
        # Plain English: Describes the task to be created.
        payload = {
            "name": f"Student: {student['name']} - {student['cohort']}",
            "markdown_content": markdown_body,
            "priority": student["priority"],
            "tags": [
                student["cohort"].lower().replace(" ", "-"),
                "high-ticket",
                "red-flag" if student["health_score"] < 50 else "healthy"
            ]
        }

        # Runtime: Sends one authenticated task-create request to ClickUp.
        # Architecture: Performs the external side effect for this fixture record.
        # Plain English: Asks ClickUp to create the student's task.
        resp = requests.post(url, json=payload, headers=HEADERS)
        # Runtime: Branches on ClickUp's successful HTTP response.
        # Architecture: Separates confirmed provisioning from API failures.
        # Plain English: Checks whether task creation worked.
        if resp.status_code == 200:
            # Runtime: Extracts ClickUp's generated task identifier from JSON.
            # Architecture: Provides the correlation key used by later synchronization.
            # Plain English: Captures the new task ID.
            task_id = resp.json().get("id")
            print(f"[SUCCESS] Created task for {student['name']} (Task ID: {task_id})")
        else:
            # Runtime: Prints status and response text for failed API calls.
            # Architecture: Preserves operational diagnostics without retrying this fixture.
            # Plain English: Explains why this task was not created.
            print(f"[FAILED] Could not create {student['name']}: {resp.status_code} - {resp.text}")

# Runtime: Guards the batch operation from running during module import.
# Architecture: Makes this utility safe to reuse from tests or other scripts.
# Plain English: Starts seeding only when launched directly.
if __name__ == "__main__":
    # Runtime: Invokes the synchronous batch function.
    # Architecture: Begins the ClickUp fixture creation lifecycle.
    # Plain English: Runs the seeder.
    seed_clickup()