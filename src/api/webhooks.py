import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from src.core.config import settings
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.queue_service import QueueService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseOps-Engine API")
queue_service = QueueService()


@app.get("/health")
async def health():
    return {"status": "ok"}


class GHLWebhook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    ghl_contact_id: str = Field(min_length=1, max_length=200)
    cohort: Optional[str] = Field(default="Default", max_length=200)


class ClickUpHistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field: str
    after: dict


class ClickUpWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    event: str
    history_items: list[ClickUpHistoryItem] = []


def _verify_signature(raw_body: bytes, received: str | None, secret: str) -> None:
    if not received:
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received.removeprefix("sha256=")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@app.post("/webhooks/ghl/deal-won")
async def ghl_deal_won(request: Request):
    raw_body = await request.body()
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    payload = GHLWebhook.model_validate_json(raw_body)

    async with SessionLocal() as session:
        try:
            result = await session.execute(
                select(Student)
                .where(Student.ghl_contact_id == payload.ghl_contact_id)
                .with_for_update()
            )
            student = result.scalar_one_or_none()
            if student is None:
                student = Student(
                    name=payload.name,
                    ghl_contact_id=payload.ghl_contact_id,
                    status="queued",
                )
                session.add(student)
                await session.flush()
            elif student.clickup_task_id or student.status in {"queued", "processing", "completed"}:
                await session.rollback()
                return {"status": "duplicate", "student_id": student.id}
            else:
                student.status = "queued"

            await session.commit()
            student_id = student.id
        except Exception:
            await session.rollback()
            logger.exception("Failed to persist GHL webhook")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    try:
        await queue_service.push_message(json.dumps({"id": student_id}))
    except Exception:
        async with SessionLocal() as session:
            result = await session.execute(select(Student).where(Student.id == student_id).with_for_update())
            queued_student = result.scalar_one_or_none()
            if queued_student and not queued_student.clickup_task_id:
                queued_student.status = "pending"
                await session.commit()
        logger.exception("Failed to enqueue student provisioning")
        raise HTTPException(status_code=503, detail="Provisioning queue unavailable")

    return {"status": "accepted", "student_id": student_id}


@app.post("/webhooks/clickup/task-updated")
async def clickup_task_updated(request: Request):
    raw_body = await request.body()
    _verify_signature(
        raw_body,
        request.headers.get("X-Webhook-Signature"),
        settings.CLICKUP_WEBHOOK_SECRET,
    )
    payload = ClickUpWebhook.model_validate_json(raw_body)
    new_status = next(
        (
            item.after.get("status")
            for item in payload.history_items
            if item.field == "status"
        ),
        None,
    )
    if not new_status:
        return {"status": "ignored", "reason": "non-status update"}

    async with SessionLocal() as session:
        result = await session.execute(
            select(Student).where(Student.clickup_task_id == payload.task_id).with_for_update()
        )
        student = result.scalar_one_or_none()
        if not student:
            return {"status": "ignored", "reason": "task not tracked"}
        student.status = new_status
        await session.commit()
    return {"status": "synchronized", "task_id": payload.task_id, "new_status": new_status}
