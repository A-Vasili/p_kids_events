# This service applies catalogue changes made through the management area.
# It protects packages, experiences, and categories that are already referenced by bookings while
# still allowing safe archive and restore actions.
# Audit records explain important management changes without copying unnecessary customer
# information.

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from party_builder.models import AddonExperience, Category, GuestPriceTier, PartyPackage

from .audit import model_snapshot, record_audit


# This class groups the information and behaviour needed for removal result.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
@dataclass(frozen=True)
class RemovalResult:
    action: str
    message: str


CATALOGUE_AUDIT_FIELDS = {
    Category: (
        "name", "slug", "description", "parent", "image", "image_alt_text",
        "display_order", "is_active",
    ),
    PartyPackage: (
        "name", "slug", "category", "short_description", "base_price",
        "duration_minutes", "included_guest_count", "included_experiences",
        "is_default", "is_active", "display_order", "image", "image_alt_text",
    ),
    GuestPriceTier: (
        "package", "label", "min_guests", "max_guests", "total_price",
        "is_default", "is_active", "display_order",
    ),
    AddonExperience: (
        "name", "slug", "category", "short_description", "price",
        "duration_minutes", "icon", "is_featured", "is_active",
        "display_order", "image", "image_alt_text",
    ),
}


# This function handles fields for as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _fields_for(instance) -> tuple[str, ...]:
    for model, fields in CATALOGUE_AUDIT_FIELDS.items():
        if isinstance(instance, model):
            return fields
    return tuple()


# This function handles schedule old image cleanup as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _schedule_old_image_cleanup(instance, old_image_name: str) -> None:
    """Delete a replaced file only after the database transaction succeeds."""

    new_name = getattr(getattr(instance, "image", None), "name", "")
    if not old_image_name or old_image_name == new_name:
        return
    storage = instance._meta.get_field("image").storage
    transaction.on_commit(lambda: storage.delete(old_image_name))


# This function handles record default replacement as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _record_default_replacement(*, actor, previous, replacement) -> None:
    """Record which catalogue record took over as the default selection."""

    record_audit(
        actor=actor,
        event_type="catalogue_default_changed",
        target=replacement,
        summary=f"{actor} replaced default {previous} with {replacement}.",
        before={
            "default_object_type": previous._meta.label,
            "default_object_id": previous.pk,
        },
        after={
            "default_object_type": replacement._meta.label,
            "default_object_id": replacement.pk,
        },
    )


# This function handles save catalogue form as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def save_catalogue_form(form, *, actor):
    """Save a catalogue form while keeping default records usable and unique.

    The checkout always needs one active default package and each package needs
    one active default guest tier. When an administrator replaces or unchecks a
    current default, this service promotes a safe replacement in the same
    transaction. If no replacement exists, the form receives a clear error
    instead of leaving the public checkout in a broken state.
    """

    instance = form.instance
    creating = instance.pk is None
    fields = _fields_for(instance)
    before = {}
    old_image_name = ""
    original = None
    if not creating:
        original = instance.__class__.objects.select_for_update().get(pk=instance.pk)
        before = model_snapshot(original, fields)
        if hasattr(original, "image"):
            old_image_name = original.image.name

    if "remove_image" in form.cleaned_data and form.cleaned_data["remove_image"]:
        instance.image = None
        instance.image_alt_text = ""

    instance = form.save(commit=False)
    instance.full_clean()

    if isinstance(instance, PartyPackage):
        other_active = PartyPackage.objects.select_for_update().filter(
            is_active=True
        ).exclude(pk=instance.pk)
        had_default = bool(original and original.is_default)

        # The first active package becomes the default automatically. This makes
        # a newly installed catalogue usable without a separate setup action.
        if creating and instance.is_active and not PartyPackage.objects.filter(is_default=True).exists():
            instance.is_default = True

        # A current default cannot simply disappear. Promote the next active
        # package or explain why the requested change cannot be completed.
        if had_default and (not instance.is_default or not instance.is_active):
            replacement = other_active.order_by("display_order", "name").first()
            if replacement is None:
                raise ValidationError(
                    "Create or activate another package before removing the current default."
                )
            # Clear the old row before promoting the replacement. The unique
            # database constraint then remains valid throughout normal saves.
            PartyPackage.objects.filter(pk=instance.pk).update(is_default=False)
            replacement.is_default = True
            replacement.save(update_fields=["is_default"])
            _record_default_replacement(
                actor=actor, previous=original, replacement=replacement
            )

        if instance.is_default:
            if not instance.is_active:
                raise ValidationError("The default package must remain active.")
            PartyPackage.objects.exclude(pk=instance.pk).filter(is_default=True).update(
                is_default=False
            )

    if isinstance(instance, GuestPriceTier):
        original_package = original.package if original else instance.package
        had_default = bool(original and original.is_default)
        other_active_old_package = GuestPriceTier.objects.select_for_update().filter(
            package=original_package,
            is_active=True,
        ).exclude(pk=instance.pk)

        if creating and instance.is_active and not GuestPriceTier.objects.filter(
            package=instance.package,
            is_default=True,
        ).exists():
            instance.is_default = True

        # Moving or editing the old default must leave its original package with
        # a usable default tier.
        leaves_original_default = had_default and (
            not instance.is_default
            or not instance.is_active
            or instance.package_id != original_package.pk
        )
        if leaves_original_default:
            replacement = other_active_old_package.order_by(
                "display_order", "min_guests"
            ).first()
            if replacement is None:
                raise ValidationError(
                    "Create or activate another tier before removing the current default tier."
                )
            GuestPriceTier.objects.filter(pk=instance.pk).update(is_default=False)
            replacement.is_default = True
            replacement.save(update_fields=["is_default"])
            _record_default_replacement(
                actor=actor, previous=original, replacement=replacement
            )

        if instance.is_default:
            if not instance.is_active:
                raise ValidationError("The default tier must remain active.")
            GuestPriceTier.objects.filter(
                package=instance.package,
                is_default=True,
            ).exclude(pk=instance.pk).update(is_default=False)

    instance.save()
    if hasattr(form, "save_m2m"):
        form.save_m2m()

    _schedule_old_image_cleanup(instance, old_image_name)
    after = model_snapshot(instance, fields)
    changed_image = before.get("image") != after.get("image") if before else bool(after.get("image"))
    event_type = f"{instance._meta.model_name}_{'created' if creating else 'updated'}"
    record_audit(
        actor=actor,
        event_type=event_type,
        target=instance,
        summary=f"{actor} {'created' if creating else 'updated'} {instance}.",
        before=before,
        after=after,
    )

    # Extra focused events make the audit screen easier to filter than a long
    # list of generic updates. The complete before/after snapshot remains on
    # the main create/update event.
    if "is_active" in after and before.get("is_active") != after.get("is_active"):
        state = "activated" if after["is_active"] else "deactivated"
        record_audit(
            actor=actor,
            event_type=f"{instance._meta.model_name}_{state}",
            target=instance,
            summary=f"{actor} {state} {instance}.",
            before={"is_active": before.get("is_active")},
            after={"is_active": after.get("is_active")},
        )

    if "is_default" in after and before.get("is_default") != after.get("is_default"):
        record_audit(
            actor=actor,
            event_type="catalogue_default_changed",
            target=instance,
            summary=f"{actor} changed the default selection for {instance}.",
            before={"is_default": before.get("is_default")},
            after={"is_default": after.get("is_default")},
        )

    price_field = next(
        (name for name in ("base_price", "total_price", "price") if name in after),
        None,
    )
    if price_field and before.get(price_field) != after.get(price_field):
        record_audit(
            actor=actor,
            event_type="catalogue_price_changed",
            target=instance,
            summary=f"{actor} changed the price for {instance}.",
            before={price_field: before.get(price_field)},
            after={price_field: after.get(price_field)},
        )

    if changed_image:
        record_audit(
            actor=actor,
            event_type="catalogue_image_changed",
            target=instance,
            summary=f"{actor} changed the image for {instance}.",
            before={"image": before.get("image", "")},
            after={"image": after.get("image", "")},
        )
    return instance


# This function handles archive as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _archive(instance, *, actor, reason: str) -> RemovalResult:
    before = {"is_active": instance.is_active}
    instance.is_active = False
    if isinstance(instance, PartyPackage) and instance.is_default:
        replacement = PartyPackage.objects.filter(is_active=True).exclude(pk=instance.pk).order_by(
            "display_order", "name"
        ).first()
        if replacement is None:
            raise ValidationError(
                "Create or activate another package before archiving the default package."
            )
        instance.is_default = False
        instance.save(update_fields=["is_default"])
        replacement.is_default = True
        replacement.save(update_fields=["is_default"])
        _record_default_replacement(
            actor=actor, previous=instance, replacement=replacement
        )
        update_fields = ["is_active"]
    elif isinstance(instance, GuestPriceTier) and instance.is_default:
        replacement = GuestPriceTier.objects.filter(
            package=instance.package, is_active=True
        ).exclude(pk=instance.pk).order_by("display_order", "min_guests").first()
        if replacement is None:
            raise ValidationError(
                "Create or activate another tier before archiving the default tier."
            )
        instance.is_default = False
        instance.save(update_fields=["is_default"])
        replacement.is_default = True
        replacement.save(update_fields=["is_default"])
        _record_default_replacement(
            actor=actor, previous=instance, replacement=replacement
        )
        update_fields = ["is_active"]
    else:
        update_fields = ["is_active"]
    instance.save(update_fields=update_fields)
    record_audit(
        actor=actor,
        event_type=f"{instance._meta.model_name}_archived",
        target=instance,
        summary=f"{actor} archived {instance} because it is used by historical data.",
        before=before,
        after={"is_active": False, "reason": reason},
    )
    return RemovalResult("archived", f"{instance} was archived because {reason}")


# This function handles remove category as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def remove_category(category: Category, *, actor) -> RemovalResult:
    locked = Category.objects.select_for_update().get(pk=category.pk)
    usage = []
    if locked.packages.exists():
        usage.append(f"{locked.packages.count()} package(s)")
    if locked.addons.exists():
        usage.append(f"{locked.addons.count()} add-on(s)")
    if locked.children.exists():
        usage.append(f"{locked.children.count()} subcategory record(s)")
    if usage:
        return _archive(locked, actor=actor, reason="it is used by " + ", ".join(usage) + ".")

    image_name = locked.image.name
    label = str(locked)
    record_audit(
        actor=actor,
        event_type="category_deleted",
        target=locked,
        summary=f"{actor} deleted unused category {label}.",
        before=model_snapshot(locked, _fields_for(locked)),
    )
    storage = locked._meta.get_field("image").storage
    locked.delete()
    if image_name:
        transaction.on_commit(lambda: storage.delete(image_name))
    return RemovalResult("deleted", f"{label} was permanently deleted.")


# This function handles remove package as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def remove_package(package: PartyPackage, *, actor) -> RemovalResult:
    locked = PartyPackage.objects.select_for_update().get(pk=package.pk)
    referenced = locked.builds.exists() or locked.guest_price_tiers.filter(builds__isnull=False).exists()
    if referenced:
        return _archive(locked, actor=actor, reason="completed bookings reference it.")
    if locked.is_default:
        replacement = PartyPackage.objects.filter(is_active=True).exclude(pk=locked.pk).order_by(
            "display_order", "name"
        ).first()
        if replacement is None:
            raise ValidationError(
                "Create or activate another package before deleting the default package."
            )
        locked.is_default = False
        locked.save(update_fields=["is_default"])
        replacement.is_default = True
        replacement.save(update_fields=["is_default"])
        _record_default_replacement(
            actor=actor, previous=locked, replacement=replacement
        )

    image_name = locked.image.name
    label = str(locked)
    record_audit(
        actor=actor,
        event_type="partypackage_deleted",
        target=locked,
        summary=f"{actor} deleted unused package {label}.",
        before=model_snapshot(locked, _fields_for(locked)),
    )
    storage = locked._meta.get_field("image").storage
    locked.delete()
    if image_name:
        transaction.on_commit(lambda: storage.delete(image_name))
    return RemovalResult("deleted", f"{label} was permanently deleted.")


# This function handles remove tier as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def remove_tier(tier: GuestPriceTier, *, actor) -> RemovalResult:
    locked = GuestPriceTier.objects.select_for_update().get(pk=tier.pk)
    if locked.builds.exists():
        return _archive(locked, actor=actor, reason="completed bookings reference it.")
    if locked.is_default:
        replacement = GuestPriceTier.objects.filter(
            package=locked.package, is_active=True
        ).exclude(pk=locked.pk).order_by("display_order", "min_guests").first()
        if replacement is None:
            raise ValidationError(
                "Create or activate another tier before deleting the default tier."
            )
        locked.is_default = False
        locked.save(update_fields=["is_default"])
        replacement.is_default = True
        replacement.save(update_fields=["is_default"])
        _record_default_replacement(
            actor=actor, previous=locked, replacement=replacement
        )
    label = str(locked)
    record_audit(
        actor=actor,
        event_type="guestpricetier_deleted",
        target=locked,
        summary=f"{actor} deleted unused guest tier {label}.",
        before=model_snapshot(locked, _fields_for(locked)),
    )
    locked.delete()
    return RemovalResult("deleted", f"{label} was permanently deleted.")


# This function handles remove addon as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def remove_addon(addon: AddonExperience, *, actor) -> RemovalResult:
    locked = AddonExperience.objects.select_for_update().get(pk=addon.pk)
    if locked.build_items.exists():
        return _archive(locked, actor=actor, reason="completed bookings reference it.")

    image_name = locked.image.name
    label = str(locked)
    record_audit(
        actor=actor,
        event_type="addonexperience_deleted",
        target=locked,
        summary=f"{actor} deleted unused add-on {label}.",
        before=model_snapshot(locked, _fields_for(locked)),
    )
    storage = locked._meta.get_field("image").storage
    locked.delete()
    if image_name:
        transaction.on_commit(lambda: storage.delete(image_name))
    return RemovalResult("deleted", f"{label} was permanently deleted.")
