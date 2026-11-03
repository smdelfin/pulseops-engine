import os
from pathlib import Path
import requests
from dotenv import load_dotenv

# Explicitly load .env from the project root
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
CLICKUP_LIST_ID = os.getenv("CLICKUP_DEFAULT_LIST_ID")

HEADERS = {
    "Authorization": CLICKUP_API_TOKEN,
    "Content-Type": "application/json"
}

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

def seed_clickup():
    if not CLICKUP_API_TOKEN or not CLICKUP_LIST_ID:
        print("[ERROR] Please set CLICKUP_API_TOKEN and CLICKUP_DEFAULT_LIST_ID in your .env file.")
        return

    url = f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task"

    for student in STUDENTS_TEST_DATA:
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

        resp = requests.post(url, json=payload, headers=HEADERS)
        if resp.status_code == 200:
            task_id = resp.json().get("id")
            print(f"[SUCCESS] Created task for {student['name']} (Task ID: {task_id})")
        else:
            print(f"[FAILED] Could not create {student['name']}: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    seed_clickup()