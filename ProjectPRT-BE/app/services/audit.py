from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_audit_event(
    db: Session,
    entity_type: str,
    entity_id: UUID,
    action: str,
    performed_by: str,
    details_json: Optional[dict[str, Any]] = None,
) -> AuditLog:
    audit_log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=performed_by,
        details_json=details_json,
    )
    db.add(audit_log)
    # NOTE: commit/refresh is handled by the calling function.
    return audit_log
