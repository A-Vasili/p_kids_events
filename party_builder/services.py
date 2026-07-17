# This file contains the trusted business actions for this feature.
# Keeping these actions outside views means the same permission, validation, history, and
# all-or-nothing database rules apply wherever the action is used.
# The surrounding pages collect intent, while these services decide what may safely change.

from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, MutableMapping

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    AddonExperience,
    PartyBuild,
    PartyBuildAddon,
    PartyPackage,
    generate_unique_review_code,
)


CHECKOUT_SESSION_KEY = "party_builder_checkout"
AUTHORIZED_BUILD_SESSION_KEY = "party_builder_builds"


# This function handles positive integer as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _positive_integer(value: object) -> int | None:
    """Convert a session value to a database ID without accepting booleans."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


# This function handles public packages as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def public_packages():
    """Return packages that are safe to show or select on the public website.

    Catalogue records can stay in the database after an administrator archives
    them because completed bookings still need their history.  The public site
    therefore checks both the item and its category tree instead of relying on
    the package's own active flag alone.
    """

    return PartyPackage.objects.filter(
        is_active=True,
        category__is_active=True,
    ).filter(Q(category__parent__isnull=True) | Q(category__parent__is_active=True))


# This function handles public addons as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def public_addons():
    """Return experiences that are safe to show or keep in a public cart."""

    return AddonExperience.objects.filter(
        is_active=True,
        category__is_active=True,
    ).filter(Q(category__parent__isnull=True) | Q(category__parent__is_active=True))


# This function handles checkout state as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def checkout_state(session: MutableMapping) -> dict[str, Any]:
    """Return a safe copy of the in-progress party stored in this browser.

    Sessions can outlive catalogue changes, so every caller treats missing or
    malformed values as an empty party instead of trusting old browser data.
    """

    state = session.get(CHECKOUT_SESSION_KEY, {})
    clean_state = dict(state) if isinstance(state, dict) else {}
    if "guest_tier_id" in clean_state:
        # Guest tiers remain in the database for old bookings, but they no
        # longer control a new cart. Removing the old key also prevents stale
        # tier prices from influencing later checkout code.
        clean_state.pop("guest_tier_id", None)
        session[CHECKOUT_SESSION_KEY] = clean_state
        if hasattr(session, "modified"):
            session.modified = True
    return clean_state


# This function handles save checkout state as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def save_checkout_state(session: MutableMapping, state: Mapping[str, Any]) -> None:
    """Store only the small set of choices needed to continue the builder.

    Old browsers may still carry a guest-tier ID. New bookings use the package
    itself for capacity and price, so that legacy key is discarded safely.
    """

    clean_state = dict(state)
    clean_state.pop("guest_tier_id", None)
    session[CHECKOUT_SESSION_KEY] = clean_state
    if hasattr(session, "modified"):
        session.modified = True


# This function handles clear checkout state as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def clear_checkout_state(session: MutableMapping) -> None:
    """Remove the unfinished party without affecting login or other session data."""

    session.pop(CHECKOUT_SESSION_KEY, None)
    if hasattr(session, "modified"):
        session.modified = True


# This helper prepares resolve active package for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def resolve_active_package(session: MutableMapping) -> PartyPackage | None:
    """Resolve the selected package, with a predictable public fallback.

    An administrator may archive a package while a customer is browsing. In
    that case the builder quietly falls back to the current default rather than
    exposing an inactive item or failing with stale session data.
    """

    state = checkout_state(session)
    raw_package_id = state.get("package_id")
    package = None
    package_id = _positive_integer(raw_package_id)
    if package_id is not None:
        package = public_packages().filter(pk=package_id).first()
    if package is None:
        available_packages = public_packages()
        package = (
            available_packages.filter(is_default=True).first()
            or available_packages.order_by("display_order", "name").first()
        )

    clean_package_id = package.pk if package else None
    if state and state.get("package_id") != clean_package_id:
        state["package_id"] = clean_package_id
        save_checkout_state(session, state)

    return package


# This function handles active session addons as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def active_session_addons(session: MutableMapping) -> list[AddonExperience]:
    """Return active selected experiences and remove stale or duplicate IDs."""

    state = checkout_state(session)
    raw_ids = state.get("addon_ids", [])
    ids: list[int] = []
    if isinstance(raw_ids, (list, tuple)):
        for value in raw_ids:
            parsed = _positive_integer(value)
            if parsed is not None and parsed not in ids:
                ids.append(parsed)
    available_by_id = public_addons().in_bulk(ids)
    # Preserve the customer's original order while removing records that are
    # no longer public.  This also makes the cleaned session deterministic.
    addons = [available_by_id[item_id] for item_id in ids if item_id in available_by_id]
    clean_ids = [addon.pk for addon in addons]
    if raw_ids != clean_ids:
        state["addon_ids"] = clean_ids
        save_checkout_state(session, state)
    return addons


# This function handles select package as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def select_package(session: MutableMapping, package: PartyPackage) -> dict[str, Any]:
    """Use a capacity-based package without losing valid extras or details."""

    if not public_packages().filter(pk=package.pk).exists():
        raise ValueError("Only publicly available packages can start a party.")
    state = checkout_state(session)
    state.update(
        {
            "package_id": package.pk,
            "addon_ids": [addon.pk for addon in active_session_addons(session)],
        }
    )
    state.pop("guest_tier_id", None)
    state.pop("details_need_review", None)
    save_checkout_state(session, state)
    return checkout_state(session)


# This business action carries out add addon to session.
# It validates the live records and permissions before changing anything, then keeps related
# updates together so partial results are not left behind.
def add_addon_to_session(
    session: MutableMapping, addon: AddonExperience
) -> dict[str, Any]:
    """Add one active experience to the same cart used by the party builder."""

    if not public_addons().filter(pk=addon.pk).exists():
        raise ValueError("Only publicly available experiences can be added to a party.")
    state = checkout_state(session)
    ids = [item.pk for item in active_session_addons(session)]
    if addon.pk not in ids:
        ids.append(addon.pk)
    state["addon_ids"] = ids
    save_checkout_state(session, state)
    return state


# This class groups the information and behaviour needed for party quote.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
@dataclass(frozen=True, slots=True)
class PartyQuote:
    """Immutable price result used by every checkout step."""

    package_price: Decimal
    addon_price: Decimal
    total_price: Decimal


# This class groups the information and behaviour needed for safe payment result.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
@dataclass(frozen=True, slots=True)
class SafePaymentResult:
    """Non-sensitive payment metadata that may safely be persisted."""

    card_brand: str
    card_last_four: str


# This helper prepares calculate party quote for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def calculate_party_quote(
    package: PartyPackage,
    addons: Iterable[AddonExperience],
) -> PartyQuote:
    """Calculate a trusted quote from the package and active database prices."""

    addon_total = sum((addon.price for addon in addons), Decimal("0.00"))
    return PartyQuote(
        package_price=package.base_price,
        addon_price=addon_total,
        total_price=package.base_price + addon_total,
    )


# This business action carries out create completed party build.
# It validates the live records and permissions before changing anything, then keeps related
# updates together so partial results are not left behind.
@transaction.atomic
def create_completed_party_build(
    *,
    package: PartyPackage,
    addons: Iterable[AddonExperience],
    details: Mapping[str, Any],
    payment: SafePaymentResult,
    customer=None,
) -> PartyBuild:
    """Create the simulated order and all trusted price snapshots atomically."""

    selected_addons = list(addons)
    quote = calculate_party_quote(package, selected_addons)

    build_values = {
        "customer": customer if getattr(customer, "is_authenticated", False) else None,
        "package": package,
        # GuestPriceTier remains for old bookings, but new bookings use the
        # chosen package as the authoritative capacity and price.
        "guest_tier": None,
        "contact_name": details["contact_name"],
        "contact_email": details["contact_email"],
        "contact_phone": details["contact_phone"],
        "event_date": details["event_date"],
        "event_time": details.get("event_time"),
        "event_address": details.get("event_address", ""),
        "postal_code": details.get("postal_code", ""),
        "guest_count": package.included_guest_count,
        "notes": details.get("notes", ""),
        "guest_tier_label": f"Up to {package.included_guest_count} children",
        "package_price": quote.package_price,
        "addon_price": quote.addon_price,
        "total_price": quote.total_price,
        "payment_status": PartyBuild.PaymentStatus.SIMULATED,
        "card_brand": payment.card_brand,
        "card_last_four": payment.card_last_four,
        "payment_reference": f"SIM-{secrets.token_hex(6).upper()}",
        "checkout_completed_at": timezone.now(),
        "status": PartyBuild.Status.SUBMITTED,
    }

    # The random space is large, but a nested savepoint makes the rare race
    # between two identical candidates recoverable instead of failing checkout.
    for _attempt in range(32):
        code = generate_unique_review_code()
        try:
            with transaction.atomic():
                build = PartyBuild.objects.create(review_code=code, **build_values)
            break
        except IntegrityError:
            if PartyBuild.objects.filter(review_code=code).exists():
                continue
            raise
    else:
        raise RuntimeError("Unable to allocate a unique party review code.")

    PartyBuildAddon.objects.bulk_create(
        PartyBuildAddon(
            build=build,
            addon=addon,
            unit_price=addon.price,
        )
        for addon in selected_addons
    )

    # Assignment happens only after the checkout transaction commits successfully.
    from operations.services.assignment import offer_assignment

    transaction.on_commit(lambda: offer_assignment(build.pk), robust=True)
    return build
