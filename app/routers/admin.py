from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import crud, notifier
from ..auth import hash_password, require_admin
from ..database import get_db
from ..models import User
from ..status_service import build_status
from ..templating import templates

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    status = build_status(db)
    return templates.TemplateResponse(
        "admin/overview.html",
        {"request": request, "status": status, "user": user, "active": "overview"},
    )


# ---------- Группы ----------

@router.get("/groups", response_class=HTMLResponse)
def groups_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    groups = crud.list_groups(db)
    return templates.TemplateResponse(
        "admin/groups.html",
        {"request": request, "groups": groups, "user": user, "active": "groups"},
    )


@router.post("/groups")
def create_group(
    name: str = Form(...),
    description: str = Form(""),
    order: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    crud.create_group(db, name=name.strip(), description=description.strip(), order=order)
    return RedirectResponse(url="/admin/groups", status_code=303)


@router.post("/groups/{group_id}/edit")
def edit_group(
    group_id: int,
    name: str = Form(...),
    description: str = Form(""),
    order: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    group = crud.get_group(db, group_id)
    if group:
        crud.update_group(
            db, group, name=name.strip(), description=description.strip(), order=order
        )
    return RedirectResponse(url="/admin/groups", status_code=303)


@router.post("/groups/{group_id}/delete")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    group = crud.get_group(db, group_id)
    if group:
        crud.delete_group(db, group)
    return RedirectResponse(url="/admin/groups", status_code=303)


# ---------- Устройства ----------

@router.get("/devices", response_class=HTMLResponse)
def devices_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    imported: int | None = None,
    skipped: int | None = None,
):
    devices = crud.list_devices(db)
    groups = crud.list_groups(db)
    return templates.TemplateResponse(
        "admin/devices.html",
        {
            "request": request,
            "devices": devices,
            "groups": groups,
            "user": user,
            "active": "devices",
            "imported": imported,
            "skipped": skipped,
        },
    )


@router.post("/devices/import")
async def import_devices(
    group_id: str = Form(None),
    interval: str = Form(None),
    text: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    content = text or ""
    if file is not None and file.filename:
        raw = await file.read()
        content += "\n" + raw.decode("utf-8", errors="ignore")
    entries, skipped = crud.parse_import(content)
    created = crud.bulk_create_devices(
        db,
        entries,
        group_id=_parse_group_id(group_id),
        interval=_parse_interval(interval),
    )
    return RedirectResponse(
        url=f"/admin/devices?imported={created}&skipped={len(skipped)}",
        status_code=303,
    )


def _parse_group_id(group_id: str | None) -> int | None:
    if group_id is None or group_id == "":
        return None
    return int(group_id)


def _parse_interval(interval: str | None) -> int | None:
    if interval is None or interval == "":
        return None
    return int(interval)


@router.post("/devices")
def create_device(
    name: str = Form(...),
    host: str = Form(...),
    group_id: str = Form(None),
    interval: str = Form(None),
    latency_threshold: str = Form(None),
    enabled: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    crud.create_device(
        db,
        name=name.strip(),
        host=host.strip(),
        group_id=_parse_group_id(group_id),
        interval=_parse_interval(interval),
        latency_threshold=_parse_interval(latency_threshold),
        enabled=enabled is not None,
    )
    return RedirectResponse(url="/admin/devices", status_code=303)


@router.post("/devices/{device_id}/edit")
def edit_device(
    device_id: int,
    name: str = Form(...),
    host: str = Form(...),
    group_id: str = Form(None),
    interval: str = Form(None),
    latency_threshold: str = Form(None),
    enabled: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    device = crud.get_device(db, device_id)
    if device:
        crud.update_device(
            db,
            device,
            name=name.strip(),
            host=host.strip(),
            group_id=_parse_group_id(group_id),
            interval=_parse_interval(interval),
            latency_threshold=_parse_interval(latency_threshold),
            enabled=enabled is not None,
        )
    return RedirectResponse(url="/admin/devices", status_code=303)


@router.post("/devices/{device_id}/delete")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    device = crud.get_device(db, device_id)
    if device:
        crud.delete_device(db, device)
    return RedirectResponse(url="/admin/devices", status_code=303)


# ---------- Настройки ----------

@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    msg: str | None = None,
    err: str | None = None,
):
    app_settings = crud.get_settings(db)
    return templates.TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "s": app_settings,
            "user": user,
            "active": "settings",
            "msg": msg,
            "err": err,
        },
    )


@router.post("/settings")
def save_settings(
    default_interval: int = Form(...),
    fail_threshold: int = Form(...),
    history_retention_days: int = Form(...),
    latency_threshold_ms: int = Form(0),
    alerts_enabled: str = Form(None),
    telegram_bot_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    s = crud.get_settings(db)
    s.default_interval = max(5, default_interval)
    s.fail_threshold = max(1, fail_threshold)
    s.history_retention_days = max(1, history_retention_days)
    s.latency_threshold_ms = max(0, latency_threshold_ms)
    s.alerts_enabled = alerts_enabled is not None
    s.telegram_bot_token = telegram_bot_token.strip()
    s.telegram_chat_id = telegram_chat_id.strip()
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=saved", status_code=303)


@router.post("/settings/test-telegram")
async def test_telegram(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    s = crud.get_settings(db)
    ok, info = await notifier.send_telegram(
        s.telegram_bot_token,
        s.telegram_chat_id,
        "✅ Тест уведомления — сервис мониторинга работает.",
    )
    if ok:
        return RedirectResponse(url="/admin/settings?msg=tg_ok", status_code=303)
    return RedirectResponse(
        url=f"/admin/settings?err={info[:120]}", status_code=303
    )


@router.post("/settings/password")
def change_password(
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=pw", status_code=303)
