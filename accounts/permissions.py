# This file gives the rest of Popadoo one consistent way to understand account roles and delegated
# privileges.
# It separates Administrators, Owners, Workers, Pricing Managers, and Chat Responders so one
# privilege never silently grants unrelated access.
# Views, navigation, and services reuse these decisions, while protected views still perform their
# own checks.

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

# These shared names keep role or choice wording consistent wherever the same business rule is
# checked.
OWNER_GROUP = "Owners"
# These shared names keep role or choice wording consistent wherever the same business rule is
# checked.
WORKER_GROUP = "Workers"
# These shared names keep role or choice wording consistent wherever the same business rule is
# checked.
PRICING_GROUP = "Pricing Managers"
# These shared names keep role or choice wording consistent wherever the same business rule is
# checked.
CHAT_RESPONDER_GROUP = "Chat Responders"


# Return group membership without assuming the user is authenticated.
def user_in_group(user: AbstractBaseUser, group_name: str) -> bool:
    """Return group membership without assuming the user is authenticated."""

    return bool(
        getattr(user, "is_authenticated", False)
        and user.groups.filter(name=group_name).exists()
    )


# Return true only for an authenticated superuser; membership in the Owner group does not make a
# business owner an Administrator.
def is_administrator(user: AbstractBaseUser) -> bool:
    """Identify system administrators without treating them as Owners."""

    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_superuser", False)
    )


# Return true only for an authenticated, non-superuser account in the Owner group, keeping Owners
# distinct from Django Administrators.
def is_owner(user: AbstractBaseUser) -> bool:
    """Identify business Owners, which are deliberately not superusers."""

    return bool(
        getattr(user, "is_authenticated", False)
        and not getattr(user, "is_superuser", False)
        and user_in_group(user, OWNER_GROUP)
    )


# This permission helper answers whether the current account is allowed to access full management.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def can_access_full_management(user: AbstractBaseUser) -> bool:
    """Allow Administrators and Owners into the complete business panel."""

    return bool(is_administrator(user) or is_owner(user))


# This permission helper answers whether the current account is allowed to create owner.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def can_create_owner(user: AbstractBaseUser) -> bool:
    """Only an Administrator may create another protected Owner account."""

    return is_administrator(user)


# Return true only for an authenticated, active account in the Worker group whose WorkerProfile is
# also marked active.
def is_worker(user: AbstractBaseUser) -> bool:
    """Return true only for an active worker, never for an Administrator."""

    if not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False):
        return False
    if not user_in_group(user, WORKER_GROUP):
        return False
    profile = getattr(user, "worker_profile", None)
    return bool(profile and profile.is_active_worker)


# This permission helper answers whether the current account is allowed to manage pricing.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def can_manage_pricing(user: AbstractBaseUser) -> bool:
    """Allow full managers and explicitly delegated worker pricing managers."""

    return bool(
        can_access_full_management(user)
        or (
            user_in_group(user, PRICING_GROUP)
            and user.has_perm("party_builder.change_partypackage")
            and user.has_perm("party_builder.change_addonexperience")
        )
    )



# This permission helper answers whether the current account is allowed to respond to customer
# chat.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def can_respond_to_customer_chat(user: AbstractBaseUser) -> bool:
    """Allow full managers and explicitly delegated active workers to reply."""

    return bool(
        can_access_full_management(user)
        or (
            is_worker(user)
            and user_in_group(user, CHAT_RESPONDER_GROUP)
            and user.has_perm("communications.respond_to_customer_chat")
        )
    )

# This permission helper answers whether the current account is allowed to access operations.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def can_access_operations(user: AbstractBaseUser) -> bool:
    """Allow full managers to redirect safely and workers to use the staff portal."""

    return bool(can_access_full_management(user) or is_worker(user))


# This permission helper answers whether the current account is allowed to manage workers.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def can_manage_workers(user: AbstractBaseUser) -> bool:
    """Require full management access and the worker-role permission."""

    return bool(
        can_access_full_management(user)
        and user.has_perm("accounts.manage_worker_roles")
    )


# This context helper prepares the separate navigation flags used to show customer, worker,
# pricing, chat, and full-management links accurately.
# The flags improve navigation only; each protected view still performs its own permission check.
def role_context(request):
    """Expose navigation flags using one group lookup for the current request.

    These flags decide which links are shown. Private views and services still
    repeat the permission checks because hiding a link is not security.
    """

    user = request.user
    empty = {
        "nav_is_administrator": False,
        "nav_is_owner": False,
        "nav_is_worker": False,
        "nav_can_access_operations": False,
        "nav_can_manage_pricing": False,
        "nav_can_access_management": False,
        "nav_can_access_full_management": False,
        "nav_can_respond_to_chat": False,
        "nav_can_create_owner": False,
    }
    if not getattr(user, "is_authenticated", False):
        return empty

    group_names = set(user.groups.values_list("name", flat=True))
    administrator = bool(user.is_superuser)
    owner = bool(not administrator and OWNER_GROUP in group_names)
    profile = getattr(user, "worker_profile", None) if WORKER_GROUP in group_names else None
    worker = bool(WORKER_GROUP in group_names and profile and profile.is_active_worker)
    full_management = administrator or owner
    pricing = bool(
        full_management
        or (
            PRICING_GROUP in group_names
            and user.has_perm("party_builder.change_partypackage")
            and user.has_perm("party_builder.change_addonexperience")
        )
    )
    chat_responder = bool(
        full_management
        or (
            worker
            and CHAT_RESPONDER_GROUP in group_names
            and user.has_perm("communications.respond_to_customer_chat")
        )
    )
    return {
        "nav_is_administrator": administrator,
        "nav_is_owner": owner,
        "nav_is_worker": worker,
        "nav_can_access_operations": full_management or worker,
        "nav_can_manage_pricing": pricing,
        "nav_can_access_management": full_management or pricing or chat_responder,
        "nav_can_access_full_management": full_management,
        "nav_can_create_owner": administrator,
        "nav_can_respond_to_chat": chat_responder,
    }
