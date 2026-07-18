# This file provides small presentation helpers used by management templates.
# The helpers turn stored values into consistent labels or display choices without moving
# permission decisions into HTML.

from django import template

from accounts.permissions import (
    CHAT_RESPONDER_GROUP,
    OWNER_GROUP,
    PRICING_GROUP,
    WORKER_GROUP,
    is_administrator,
)

register = template.Library()


# Reuse prefetched groups on management lists instead of querying per row.
def _group_names(user) -> set[str]:
    """Reuse prefetched groups on management lists instead of querying per row."""

    prefetched = getattr(user, "_prefetched_objects_cache", {}).get("groups")
    if prefetched is not None:
        return {group.name for group in prefetched}
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(user.groups.values_list("name", flat=True))


# Return whether the account’s cached group-name set contains the requested group, avoiding another
# query for each template check.
@register.filter
def in_group(user, group_name: str) -> bool:
    return group_name in _group_names(user)


# Expose the shared Administrator predicate to templates without duplicating its
# authenticated-superuser rule.
@register.filter
def is_administrator_account(user) -> bool:
    return is_administrator(user)


# Expose Owner status to templates only for non-superusers whose cached group names include Owners.
@register.filter
def is_owner_account(user) -> bool:
    return bool(not getattr(user, "is_superuser", False) and OWNER_GROUP in _group_names(user))


# Expose Worker status to templates when the cached group names include Workers.
@register.filter
def is_worker_account(user) -> bool:
    return WORKER_GROUP in _group_names(user)


# Expose Customer status to templates only for non-superusers whose cached groups include neither
# Owners nor Workers.
@register.filter
def is_customer_account(user) -> bool:
    group_names = _group_names(user)
    return bool(
        not getattr(user, "is_superuser", False)
        and OWNER_GROUP not in group_names
        and WORKER_GROUP not in group_names
    )


# Label a management account as Administrator, Owner, Worker, or Customer from its superuser flag
# and protected group memberships.
@register.filter
def management_role(user) -> str:
    if getattr(user, "is_superuser", False):
        return "Administrator"
    group_names = _group_names(user)
    if OWNER_GROUP in group_names:
        return "Owner"
    if WORKER_GROUP in group_names:
        return "Worker"
    return "Customer"


# This check answers whether the current account or record has pricing access.
# The result keeps the same business interpretation wherever the condition is displayed or
# enforced.
@register.filter
def has_pricing_access(user) -> bool:
    return PRICING_GROUP in _group_names(user)


# This check answers whether the current account or record has chat access.
# The result keeps the same business interpretation wherever the condition is displayed or
# enforced.
@register.filter
def has_chat_access(user) -> bool:
    return CHAT_RESPONDER_GROUP in _group_names(user)


# Map stored workflow statuses to the badge style used by management templates, with unknown values
# falling back to the muted variant.
@register.filter
def status_css(value: str) -> str:
    mapping = {
        "active": "success",
        "accepted": "success",
        "assigned": "success",
        "confirmed": "success",
        "completed": "success",
        "inactive": "muted",
        "cancelled": "danger",
        "declined": "danger",
        "manual_review": "warning",
        "pending": "warning",
        "pending_acceptance": "warning",
        "submitted": "info",
        "contacted": "info",
        "unassigned": "warning",
    }
    return mapping.get(str(value), "muted")


# Turn stored machine-friendly action names into readable labels.
@register.filter
def audit_event_label(value: str) -> str:
    """Turn stored machine-friendly action names into readable labels."""

    return str(value or "").replace("_", " ").strip().title()
