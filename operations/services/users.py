# This service manages sensitive account and staff-role changes requested from the management
# area.
# It protects historical records, keeps delegated roles independent, and records important changes
# in the audit history.
# Centralising these actions prevents a page from accidentally bypassing worker, pricing, or
# chat-access rules.

from __future__ import annotations

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import WorkerProfile
from accounts.permissions import (
    CHAT_RESPONDER_GROUP,
    OWNER_GROUP,
    PRICING_GROUP,
    WORKER_GROUP,
    can_access_full_management,
    is_administrator,
)

from ..models import AuditEvent
from .audit import record_audit

User = get_user_model()


# Compute require business manager for the surrounding analytics or service workflow. Centralizing
# the calculation keeps date, status, and filtering rules consistent across callers.
def _require_business_manager(actor) -> None:
    if not can_access_full_management(actor):
        raise PermissionDenied("Administrator or Owner access is required.")


# Compute require worker manager for the surrounding analytics or service workflow. Centralizing the
# calculation keeps date, status, and filtering rules consistent across callers.
def _require_worker_manager(actor) -> None:
    _require_business_manager(actor)
    if not actor.has_perm("accounts.manage_worker_roles"):
        raise PermissionDenied("Worker-management permission is required.")


# Return true only for a non-superuser account in the Owner group.
def is_owner_account(user) -> bool:
    """Return true for a protected Owner account, never for a superuser."""

    return bool(not user.is_superuser and user.groups.filter(name=OWNER_GROUP).exists())


# Return whether the account belongs to the Worker group.
def is_worker_account(user) -> bool:
    return user.groups.filter(name=WORKER_GROUP).exists()


# Treat an account as a customer only when it is not a superuser and belongs to neither the Owner
# nor Worker group.
def is_customer_account(user) -> bool:
    """Customers have no protected business role."""

    return bool(
        not user.is_superuser
        and not is_owner_account(user)
        and not is_worker_account(user)
    )


# This safeguard verifies manager can view before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def ensure_manager_can_view(actor, target) -> None:
    """Protect system accounts and stop Owners inspecting other Owners."""

    _require_business_manager(actor)
    if target.is_superuser:
        raise PermissionDenied("Administrator accounts are protected.")
    if is_owner_account(target) and not is_administrator(actor) and target.pk != actor.pk:
        raise PermissionDenied("Owners cannot view another Owner account.")


# This safeguard verifies manager can manage before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def ensure_manager_can_manage(actor, target) -> None:
    """Protect Administrators and Owners from ordinary account mutations."""

    ensure_manager_can_view(actor, target)
    if is_owner_account(target):
        raise PermissionDenied("Owner accounts use Administrator-only controls.")


# Compatibility for older internal imports while the clearer name is adopted.
ensure_owner_can_manage = ensure_manager_can_manage


# Compute reject worker role target for the surrounding analytics or service workflow. Centralizing
# the calculation keeps date, status, and filtering rules consistent across callers.
def _reject_worker_role_target(user) -> None:
    if user.is_superuser or is_owner_account(user):
        raise PermissionDenied("Owner and Administrator accounts cannot be changed here.")


# Create an Owner without granting Django staff or superuser privileges. Rechecks the actor’s
# permission, updates Group and User, commits related changes atomically.
@transaction.atomic
def create_owner_account(
    *,
    actor,
    username: str,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
):
    """Create an Owner without granting Django staff or superuser privileges."""

    if not is_administrator(actor):
        raise PermissionDenied("Only an Administrator can create an Owner.")

    owner_group, _ = Group.objects.get_or_create(name=OWNER_GROUP)
    candidate = User(username=username, email=email.strip().lower())
    password_validation.validate_password(password, user=candidate)
    user = User.objects.create_user(
        username=username,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email.strip().lower(),
        password=password,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    owner_group.user_set.add(user)
    record_audit(
        actor=actor,
        event_type="owner_created",
        target=user,
        summary=f"{actor} created Owner account {user.username}.",
        after={"role": "Owner", "is_active": True},
    )
    return user


# This protected service carries out the “promote to worker” role change.
# It rechecks the acting account and target eligibility, keeps combined roles consistent, and
# records the sensitive change for accountability.
@transaction.atomic
def promote_to_worker(user, actor):
    """Create worker access for the dedicated staff-account workflow."""

    _require_worker_manager(actor)
    _reject_worker_role_target(user)
    if user.groups.filter(name=WORKER_GROUP).exists():
        raise ValidationError("This account is already a worker.")

    worker_group, _ = Group.objects.get_or_create(name=WORKER_GROUP)
    worker_group.user_set.add(user)
    profile, _ = WorkerProfile.objects.get_or_create(user=user)
    before = {"worker": False, "is_active_worker": profile.is_active_worker}
    profile.is_active_worker = True
    profile.save(update_fields=["is_active_worker", "updated_at"])
    record_audit(
        actor=actor,
        event_type="worker_promoted",
        target=user,
        summary=f"{actor} created worker access for {user}.",
        before=before,
        after={"worker": True, "is_active_worker": True},
    )
    return profile


# This protected service carries out the “demote worker” role change.
# It rechecks the acting account and target eligibility, keeps combined roles consistent, and
# records the sensitive change for accountability.
@transaction.atomic
def demote_worker(user, actor):
    """Remove worker and pricing access without deleting staff history."""

    _require_worker_manager(actor)
    _reject_worker_role_target(user)
    if not user.groups.filter(name=WORKER_GROUP).exists():
        raise ValidationError("This account is not currently a worker.")

    had_pricing = user.groups.filter(name=PRICING_GROUP).exists()
    had_chat = user.groups.filter(name=CHAT_RESPONDER_GROUP).exists()
    worker_group = Group.objects.filter(name=WORKER_GROUP).first()
    pricing_group = Group.objects.filter(name=PRICING_GROUP).first()
    chat_group = Group.objects.filter(name=CHAT_RESPONDER_GROUP).first()
    if worker_group:
        worker_group.user_set.remove(user)
    if pricing_group:
        pricing_group.user_set.remove(user)
    if chat_group:
        chat_group.user_set.remove(user)

    profile = getattr(user, "worker_profile", None)
    if profile:
        profile.is_active_worker = False
        profile.save(update_fields=["is_active_worker", "updated_at"])

    record_audit(
        actor=actor,
        event_type="worker_demoted",
        target=user,
        summary=f"{actor} removed worker access from {user}.",
        before={"worker": True, "pricing": had_pricing, "chat_responder": had_chat},
        after={"worker": False, "pricing": False, "chat_responder": False},
    )


# This protected service carries out the “grant pricing management” role change.
# It rechecks the acting account and target eligibility, keeps combined roles consistent, and
# records the sensitive change for accountability.
@transaction.atomic
def grant_pricing_management(user, actor):
    """Grant catalogue access only to an existing worker."""

    _require_worker_manager(actor)
    _reject_worker_role_target(user)
    if not user.groups.filter(name=WORKER_GROUP).exists():
        raise ValidationError("Pricing rights can be granted only to a worker.")
    if user.groups.filter(name=PRICING_GROUP).exists():
        raise ValidationError("This worker already has pricing access.")

    group, _ = Group.objects.get_or_create(name=PRICING_GROUP)
    group.user_set.add(user)
    record_audit(
        actor=actor,
        event_type="pricing_rights_granted",
        target=user,
        summary=f"{actor} granted pricing rights to {user}.",
        before={"pricing": False},
        after={"pricing": True},
    )


# This protected service carries out the “grant chat responder access” role change.
# It rechecks the acting account and target eligibility, keeps combined roles consistent, and
# records the sensitive change for accountability.
@transaction.atomic
def grant_chat_responder_access(user, actor):
    """Grant chat access only to an existing active worker account."""

    _require_worker_manager(actor)
    _reject_worker_role_target(user)
    profile = getattr(user, "worker_profile", None)
    if (
        not user.is_active
        or not user.groups.filter(name=WORKER_GROUP).exists()
        or not profile
        or not profile.is_active_worker
    ):
        raise ValidationError("Chat access can be granted only to an active worker.")
    if user.groups.filter(name=CHAT_RESPONDER_GROUP).exists():
        raise ValidationError("This worker already has chat responder access.")

    group, _ = Group.objects.get_or_create(name=CHAT_RESPONDER_GROUP)
    group.user_set.add(user)
    record_audit(
        actor=actor,
        event_type="chat_responder_access_granted",
        target=user,
        summary=f"{actor} granted customer-chat access to {user}.",
        before={"chat_responder": False},
        after={"chat_responder": True},
    )


# This protected service carries out the “revoke chat responder access” role change.
# It rechecks the acting account and target eligibility, keeps combined roles consistent, and
# records the sensitive change for accountability.
@transaction.atomic
def revoke_chat_responder_access(user, actor):
    """Remove chat delegation without changing worker or pricing access."""

    _require_worker_manager(actor)
    _reject_worker_role_target(user)
    if not user.groups.filter(name=CHAT_RESPONDER_GROUP).exists():
        raise ValidationError("This worker does not currently have chat responder access.")

    group = Group.objects.filter(name=CHAT_RESPONDER_GROUP).first()
    if group:
        group.user_set.remove(user)
    record_audit(
        actor=actor,
        event_type="chat_responder_access_revoked",
        target=user,
        summary=f"{actor} revoked customer-chat access from {user}.",
        before={"chat_responder": True},
        after={"chat_responder": False},
    )


# This protected service carries out the “revoke pricing management” role change.
# It rechecks the acting account and target eligibility, keeps combined roles consistent, and
# records the sensitive change for accountability.
@transaction.atomic
def revoke_pricing_management(user, actor):
    """Remove delegated catalogue access while preserving worker access."""

    _require_worker_manager(actor)
    _reject_worker_role_target(user)
    if not user.groups.filter(name=PRICING_GROUP).exists():
        raise ValidationError("This worker does not currently have pricing access.")

    group = Group.objects.filter(name=PRICING_GROUP).first()
    if group:
        group.user_set.remove(user)
    record_audit(
        actor=actor,
        event_type="pricing_rights_revoked",
        target=user,
        summary=f"{actor} revoked pricing rights from {user}.",
        before={"pricing": True},
        after={"pricing": False},
    )


# This safeguard verifies owner status change before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def _validate_owner_status_change(*, actor, target, active: bool) -> None:
    if not is_owner_account(target):
        return
    if not is_administrator(actor):
        raise PermissionDenied("Only an Administrator can change an Owner account.")
    if not active:
        other_active_owners = User.objects.filter(
            is_active=True,
            is_superuser=False,
            groups__name=OWNER_GROUP,
        ).exclude(pk=target.pk)
        if not other_active_owners.exists():
            raise ValidationError("At least one other active Owner must remain.")


# Ban or unban an eligible account while preserving all business history.
@transaction.atomic
def set_account_banned(*, target, banned: bool, actor):
    """Ban or unban an eligible account while preserving all business history."""

    _require_business_manager(actor)
    if target.is_superuser:
        raise PermissionDenied("Administrator accounts are protected.")
    if target.pk == actor.pk and banned:
        raise ValidationError("You cannot ban the account you are currently using.")
    _validate_owner_status_change(actor=actor, target=target, active=not banned)

    desired_active = not banned
    if target.is_active == desired_active:
        raise ValidationError(
            "This account is already unbanned."
            if desired_active
            else "This account is already banned."
        )

    before = target.is_active
    target.is_active = desired_active
    target.save(update_fields=["is_active"])
    record_audit(
        actor=actor,
        event_type="user_unbanned" if desired_active else "user_banned",
        target=target,
        summary=f"{actor} {'unbanned' if desired_active else 'banned'} {target}.",
        before={"is_active": before},
        after={"is_active": desired_active},
    )
    return target


# Kept as a small compatibility wrapper for existing internal callers.
# This function handles set account active as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def set_account_active(*, target, active: bool, actor):
    return set_account_banned(target=target, banned=not active, actor=actor)


# This safeguard lists the historical records that must be preserved before a customer account can
# be removed permanently.
# When protected history exists, management users are directed toward the safer account-ban
# workflow instead.
def customer_delete_blockers(user) -> list[str]:
    """List the historical records that make destructive deletion unsafe."""

    blockers: list[str] = []
    if user.party_bookings.exists():
        blockers.append("party bookings")
    if user.party_reviews.exists():
        blockers.append("ratings or reviews")
    if hasattr(user, "worker_profile"):
        blockers.append("worker history")
    if user.created_party_assignments.exists():
        blockers.append("created assignments")
    if user.popadoo_audit_events.exists():
        blockers.append("audit actions")
    # Support messages are immutable business history, so the customer account
    # is banned rather than deleted once a chat exists.
    if hasattr(user, "customer_chat"):
        blockers.append("customer chat history")
    return blockers


# Delete only an unused customer; historical accounts must be banned instead. Rechecks the actor’s
# permission, updates AuditEvent, commits related changes atomically.
@transaction.atomic
def delete_unused_customer(*, target, actor) -> None:
    """Delete only an unused customer; historical accounts must be banned instead."""

    _require_business_manager(actor)
    if not is_customer_account(target):
        raise PermissionDenied("Only unused customer accounts can be deleted here.")
    if target.pk == actor.pk:
        raise PermissionDenied("You cannot delete the account you are currently using.")

    blockers = customer_delete_blockers(target)
    if blockers:
        readable = ", ".join(blockers)
        raise ValidationError(
            f"This customer has {readable}. Ban the account instead so history is preserved."
        )

    username = target.username
    target_id = target.pk
    # The audit row stores only a safe identifier. Customer contact details are
    # deliberately excluded because the account is being removed.
    AuditEvent.objects.create(
        actor=actor,
        event_type="unused_customer_deleted",
        object_type="User",
        object_id=str(target_id),
        summary=f"{actor} deleted unused customer account {username}."[:300],
        before_data={"username": username, "role": "Customer"},
        after_data={"deleted": True},
    )
    target.delete()
