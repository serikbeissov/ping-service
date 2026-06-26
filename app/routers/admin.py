from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import crud, notifier
from ..auth import hash_password, require_admin, require_user
from ..database import get_db
from ..models import User, utcnow
from ..status_service import build_status
from ..templating import templates

PERIODS = {"24h": 24, "7d": 168, "30d": 720}


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}с"
    if seconds < 3600:
        return f"{seconds // 60}м {seconds % 60}с"
    if seconds < 86400:
        return f"{seconds // 3600}ч {(seconds % 3600) // 60}м"
    return f"{seconds // 86400}д {(seconds % 86400) // 3600}ч"

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
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


def _norm_check_type(value: str | None) -> str:
    return value if value in ("icmp", "tcp", "http") else "icmp"


@router.post("/devices")
def create_device(
    name: str = Form(...),
    host: str = Form(...),
    group_id: str = Form(None),
    interval: str = Form(None),
    latency_threshold: str = Form(None),
    check_type: str = Form("icmp"),
    port: str = Form(None),
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
        check_type=_norm_check_type(check_type),
        port=_parse_interval(port),
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
    check_type: str = Form("icmp"),
    port: str = Form(None),
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
            check_type=_norm_check_type(check_type),
            port=_parse_interval(port),
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


# ---------- Инциденты и SLA ----------

@router.get("/incidents", response_class=HTMLResponse)
def incidents_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    period: str = "7d",
):
    hours = PERIODS.get(period, 168)
    until = utcnow()
    since = until - timedelta(hours=hours)
    period_seconds = (until - since).total_seconds()

    devices = crud.list_devices(db)
    groups = crud.list_groups(db)
    dev_by_id = {d.id: d for d in devices}
    downtime = crud.downtime_seconds(db, since, until, kind="down")

    def avail(seconds: float) -> float:
        return round(max(0.0, 100.0 * (period_seconds - seconds) / period_seconds), 3)

    # SLA по разделам
    def device_row(d):
        dt = downtime.get(d.id, 0.0)
        return {
            "name": d.name,
            "host": d.host,
            "availability": avail(dt),
            "downtime": _fmt_duration(dt),
            "down_seconds": dt,
        }

    report = []
    grouped_ids = set()
    for g in groups:
        rows = [device_row(d) for d in g.devices]
        grouped_ids.update(d.id for d in g.devices)
        if rows:
            total_dt = sum(r["down_seconds"] for r in rows)
            report.append(
                {
                    "name": g.name,
                    "rows": rows,
                    "avg": round(sum(r["availability"] for r in rows) / len(rows), 3),
                    "downtime": _fmt_duration(total_dt),
                }
            )
    ungrouped = [device_row(d) for d in devices if d.id not in grouped_ids]
    if ungrouped:
        total_dt = sum(r["down_seconds"] for r in ungrouped)
        report.append(
            {
                "name": "Без раздела",
                "rows": ungrouped,
                "avg": round(sum(r["availability"] for r in ungrouped) / len(ungrouped), 3),
                "downtime": _fmt_duration(total_dt),
            }
        )

    # журнал инцидентов
    incidents = []
    for inc in crud.list_incidents(db, since=since, limit=300):
        d = dev_by_id.get(inc.device_id)
        end = inc.ended_at or until
        incidents.append(
            {
                "name": d.name if d else f"#{inc.device_id}",
                "host": d.host if d else "",
                "kind": inc.kind,
                "started_at": inc.started_at,
                "ended_at": inc.ended_at,
                "ongoing": inc.ended_at is None,
                "duration": _fmt_duration((end - inc.started_at).total_seconds()),
            }
        )

    return templates.TemplateResponse(
        "admin/incidents.html",
        {
            "request": request,
            "user": user,
            "active": "incidents",
            "period": period if period in PERIODS else "7d",
            "report": report,
            "incidents": incidents,
        },
    )


# ---------- Пользователи (только admin) ----------

def _norm_role(value: str | None) -> str:
    return "viewer" if value == "viewer" else "admin"


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    msg: str | None = None,
    err: str | None = None,
):
    users = crud.list_users(db)
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "user": user,
            "active": "users",
            "msg": msg,
            "err": err,
        },
    )


@router.post("/users")
def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    username = username.strip()
    if not username or len(password) < 4:
        return RedirectResponse(url="/admin/users?err=Заполните+поля", status_code=303)
    if crud.get_user(db, username):
        return RedirectResponse(
            url="/admin/users?err=Пользователь+уже+существует", status_code=303
        )
    crud.create_user(db, username, hash_password(password), _norm_role(role))
    return RedirectResponse(url="/admin/users?msg=created", status_code=303)


@router.post("/users/{user_id}/edit")
def edit_user(
    user_id: int,
    role: str = Form(None),
    new_password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse(url="/admin/users?err=Не+найден", status_code=303)
    # нельзя снять последнего администратора
    new_role = _norm_role(role)
    if (
        target.role == "admin"
        and new_role != "admin"
        and crud.count_admins(db) <= 1
    ):
        return RedirectResponse(
            url="/admin/users?err=Нужен+хотя+бы+один+администратор", status_code=303
        )
    fields = {"role": new_role}
    if new_password:
        if len(new_password) < 4:
            return RedirectResponse(
                url="/admin/users?err=Пароль+слишком+короткий", status_code=303
            )
        fields["password_hash"] = hash_password(new_password)
    crud.update_user(db, target, **fields)
    return RedirectResponse(url="/admin/users?msg=updated", status_code=303)


@router.post("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse(url="/admin/users?err=Не+найден", status_code=303)
    if target.id == user.id:
        return RedirectResponse(
            url="/admin/users?err=Нельзя+удалить+себя", status_code=303
        )
    if target.role == "admin" and crud.count_admins(db) <= 1:
        return RedirectResponse(
            url="/admin/users?err=Нужен+хотя+бы+один+администратор", status_code=303
        )
    crud.delete_user(db, target)
    return RedirectResponse(url="/admin/users?msg=deleted", status_code=303)


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
