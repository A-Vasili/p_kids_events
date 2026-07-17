# This small service records a plain summary of important management actions in Popadoo’s audit
# history.
# Callers provide only the before-and-after business facts needed for accountability; private
# message bodies and secrets are intentionally excluded.

from __future__ import annotations

from typing import Any

from django.db.models.fields.files import FieldFile

from ..models import AuditEvent


# This function handles serialise value as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def serialise_value(value: Any) -> Any:
    """Convert common model values into JSON-safe audit information."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, FieldFile):
        return value.name or ""
    if hasattr(value, "pk"):
        return {"id": value.pk, "label": str(value)}
    return str(value)


# This function handles model snapshot as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def model_snapshot(instance, fields: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Capture only approved fields; passwords and unrelated data are excluded."""

    return {field: serialise_value(getattr(instance, field, None)) for field in fields}


# This function handles record audit as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def record_audit(
    *,
    actor,
    event_type: str,
    target,
    summary: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Create one human-readable audit event for a completed action."""

    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        event_type=event_type,
        object_type=target.__class__.__name__,
        object_id=str(getattr(target, "pk", "")),
        summary=summary[:300],
        before_data=before or {},
        after_data=after or {},
    )
