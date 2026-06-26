from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import User
from ..status_service import build_status
from ..templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    status = build_status(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "status": status, "user": user},
    )
