from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..status_service import build_status

router = APIRouter(prefix="/api")


@router.get("/status")
def status(db: Session = Depends(get_db)):
    data = build_status(db)
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    return data


@router.get("/device/{device_id}/history")
def device_history(
    device_id: int,
    hours: int = 24,
    db: Session = Depends(get_db),
):
    device = crud.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    hours = max(1, min(hours, 720))  # ограничиваем 1ч..30д
    return {
        "id": device.id,
        "name": device.name,
        "host": device.host,
        "hours": hours,
        "points": crud.latency_history(db, device_id, hours=hours),
    }
