"""Lógica pura de Agile Core Studio (sin Streamlit), para poder probarla con pytest.

Incluye: contraseñas (PBKDF2), checklists, descripción de eventos de auditoría,
Diagrama de Flujo Acumulado (CFD) e historial de actividad.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import math
import re
import secrets
import uuid

import pandas as pd

STATUS_LABEL = {"To Do": "Por hacer", "In Progress": "En progreso", "Review": "Revisión", "Done": "Hecho"}

# ─────────────────────────────────────────────────────────────────────────────
# Contraseñas
# ─────────────────────────────────────────────────────────────────────────────
PBKDF2_ITERATIONS = 240_000
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Devuelve 'pbkdf2_sha256$iteraciones$sal$hash'. Nunca se guarda la contraseña."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def username_error(username: str) -> str | None:
    if not USERNAME_RE.match(username or ""):
        return "El usuario debe tener 3-30 caracteres: letras, números, punto, guion o guion bajo."
    return None


def password_error(password: str) -> str | None:
    if len(password or "") < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if password.isdigit() or password.isalpha():
        return "Combina letras y números en la contraseña."
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Checklists
# ─────────────────────────────────────────────────────────────────────────────
def _clean_text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()[:200]


def _is_true(value) -> bool:
    # Las celdas nuevas de st.data_editor pueden llegar como None/NaN: no cuentan como hechas.
    if hasattr(value, "item"):
        value = value.item()
    return value is True


def merge_checklist(old: list[dict] | None, rows: list[dict]) -> list[dict]:
    """Convierte filas del editor ({'Hecho','Elemento'}) en ítems, conservando el id
    del ítem anterior con el mismo texto. Elimina filas vacías."""
    pool: dict[str, list[str]] = {}
    for item in old or []:
        pool.setdefault(item.get("text", ""), []).append(item.get("id"))
    result = []
    for row in rows:
        text = _clean_text(row.get("Elemento"))
        if not text:
            continue
        ids = pool.get(text) or []
        item_id = ids.pop(0) if ids else uuid.uuid4().hex[:10]
        result.append({"id": item_id, "text": text, "done": _is_true(row.get("Hecho"))})
    return result


def checklist_progress(items: list[dict] | None) -> tuple[int, int]:
    items = items or []
    return sum(1 for i in items if i.get("done")), len(items)


def checklist_diff(old: list[dict] | None, new: list[dict] | None) -> list[str]:
    old_by_id = {i["id"]: i for i in old or []}
    new_by_id = {i["id"]: i for i in new or []}
    changes = []
    for item in new or []:
        before = old_by_id.get(item["id"])
        if before is None:
            changes.append(f"añadió «{item['text']}»")
        elif bool(before.get("done")) != bool(item.get("done")):
            changes.append(f"{'completó' if item.get('done') else 'reabrió'} «{item['text']}»")
    for item in old or []:
        if item["id"] not in new_by_id:
            changes.append(f"quitó «{item['text']}»")
    return changes


# ─────────────────────────────────────────────────────────────────────────────
# Cambios de tarjeta
# ─────────────────────────────────────────────────────────────────────────────
FIELD_LABELS = {
    "title": "Título", "description": "Descripción", "priority": "Prioridad", "assignee": "Responsable",
    "due_date": "Fecha límite", "tags": "Etiquetas", "story_points": "Story points", "scrum_role": "Rol",
    "sprint_id": "Sprint",
}


def task_changes(old: dict, new: dict, sprint_names: dict | None = None) -> list[str]:
    """Lista legible de campos que cambiaron (la descripción no se copia completa)."""
    sprint_names = sprint_names or {}
    out = []
    for field, label in FIELD_LABELS.items():
        if field not in new:
            continue
        a, b = old.get(field), new.get(field)
        if (a or None) == (b or None) or str(a) == str(b):
            continue
        if field == "description":
            out.append("Descripción modificada")
        elif field == "sprint_id":
            out.append(f"Sprint: {sprint_names.get(a, 'Product Backlog')} → {sprint_names.get(b, 'Product Backlog')}")
        else:
            out.append(f"{label}: {a if a not in (None, '') else '—'} → {b if b not in (None, '') else '—'}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Registro de actividad
# ─────────────────────────────────────────────────────────────────────────────
ACTION_CATEGORY = {
    "task_create": "Creación", "task_update": "Edición", "task_move": "Movimiento", "task_delete": "Eliminación",
    "checklist": "Checklist", "sprint_create": "Sprint", "sprint_start": "Sprint", "sprint_close": "Sprint",
    "sprint_delete": "Sprint", "sprint_retro": "Sprint", "demo_seed": "Sistema",
    "user_login": "Acceso", "user_register": "Acceso", "user_logout": "Acceso", "login_failed": "Acceso",
}
CATEGORY_ICON = {"Creación": "✚", "Edición": "✎", "Movimiento": "⇄", "Eliminación": "✕", "Checklist": "☑",
                 "Sprint": "⚑", "Acceso": "⚿", "Sistema": "⚙"}


def describe_event(ev: dict) -> str:
    title = f"«{ev.get('entity_title')}»" if ev.get("entity_title") else ""
    frm, to = STATUS_LABEL.get(ev.get("from_status"), ev.get("from_status")), STATUS_LABEL.get(ev.get("to_status"), ev.get("to_status"))
    action = ev.get("action")
    text = {
        "task_create": f"creó la tarjeta {title}",
        "task_update": f"editó {title}",
        "task_move": f"movió {title} de {frm} a {to}",
        "task_delete": f"eliminó {title}",
        "checklist": f"actualizó la checklist de {title}",
        "sprint_create": f"creó el sprint {title}",
        "sprint_start": f"inició el sprint {title}",
        "sprint_close": f"cerró el sprint {title}",
        "sprint_delete": f"eliminó el sprint {title}",
        "sprint_retro": f"guardó la retrospectiva de {title}",
        "demo_seed": "cargó los datos de ejemplo",
        "user_login": "inició sesión",
        "user_register": "creó su cuenta",
        "user_logout": "cerró sesión",
        "login_failed": "intento de acceso fallido",
    }.get(action, action or "acción desconocida")
    return " ".join(text.split())


def _ts(value):
    if not value:
        return None
    try:
        ts = pd.to_datetime(value, utc=True)
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts


def activity_frame(events: list[dict], days: int, today: dt.date) -> pd.DataFrame:
    """Eventos por día y categoría en los últimos `days` días (con ceros)."""
    dates = [today - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]
    counts: dict[tuple, int] = {}
    for ev in events:
        ts = _ts(ev.get("created_at"))
        if ts is None:
            continue
        d = ts.date()
        if dates[0] <= d <= today:
            cat = ACTION_CATEGORY.get(ev.get("action"), "Otros")
            counts[(d, cat)] = counts.get((d, cat), 0) + 1
    cats = sorted({c for _, c in counts}) or ["Movimiento"]
    rows = [{"Día": pd.Timestamp(d), "Tipo": c, "Eventos": counts.get((d, c), 0)} for d in dates for c in cats]
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Diagrama de Flujo Acumulado (CFD)
# ─────────────────────────────────────────────────────────────────────────────
def status_timeline(task: dict, task_events: list[dict]) -> tuple[list[tuple], bool]:
    """Secuencia [(momento, estado)] de una tarjeta.

    Usa el registro de actividad cuando existe. Para la parte anterior al registro
    (tarjetas antiguas o de ejemplo) reconstruye con created_at / started_at /
    completed_at. Devuelve también si hubo que reconstruir.
    """
    logged = sorted(
        ((ts, ev["to_status"]) for ev in task_events
         if ev.get("to_status") and (ts := _ts(ev.get("created_at"))) is not None),
        key=lambda x: x[0],
    )
    created, started, completed = _ts(task.get("created_at")), _ts(task.get("started_at")), _ts(task.get("completed_at"))
    current = task.get("status")
    fallback = []
    if created is not None:
        fallback.append((created, "To Do"))
    if started is not None:
        # Sin registro, el estado intermedio más probable es el actual (p. ej. Revisión).
        mid = current if not logged and current in ("In Progress", "Review") and completed is None else "In Progress"
        fallback.append((started, mid))
    if completed is not None:
        fallback.append((completed, "Done"))
    fallback.sort(key=lambda x: x[0])

    if not logged:
        return fallback, bool(fallback)
    first = logged[0][0]
    before = [p for p in fallback if p[0] < first]
    return before + logged, bool(before)


def cfd_frame(tasks: list[dict], events: list[dict], statuses: list[str],
              start: dt.date, end: dt.date) -> tuple[pd.DataFrame, int]:
    """Tarjetas por estado al final de cada día entre `start` y `end`.

    Devuelve (DataFrame largo [Día, Estado, Tarjetas, Orden], nº de tarjetas reconstruidas).
    Los estados que no están en `statuses` se asignan al anterior válido (p. ej.
    'Review' cuenta como 'In Progress' en Scrum).
    """
    by_task: dict[str, list[dict]] = {}
    for ev in events:
        if ev.get("entity") == "task" and ev.get("entity_id"):
            by_task.setdefault(str(ev["entity_id"]), []).append(ev)

    order_all = ["To Do", "In Progress", "Review", "Done"]

    def fit(status):
        if status in statuses:
            return status
        idx = order_all.index(status) if status in order_all else 0
        for s in reversed(order_all[:idx]):
            if s in statuses:
                return s
        return statuses[0]

    timelines, rebuilt = [], 0
    for t in tasks:
        tl, was_rebuilt = status_timeline(t, by_task.get(str(t.get("id")), []))
        if tl:
            timelines.append(tl)
            rebuilt += was_rebuilt
    rows = []
    for day in pd.date_range(start, end):
        day_end = pd.Timestamp(day.date() + dt.timedelta(days=1), tz="UTC")
        counts = dict.fromkeys(statuses, 0)
        for tl in timelines:
            state = None
            for ts, status in tl:
                if ts < day_end:
                    state = status
                else:
                    break
            if state is not None:
                counts[fit(state)] += 1
        for i, s in enumerate(statuses):
            rows.append({"Día": day, "Estado": STATUS_LABEL.get(s, s), "Tarjetas": counts[s], "Orden": i})
    return pd.DataFrame(rows), rebuilt
