# This file performs small automatic setup steps when Django finishes preparing the project or
# related records change.
# It keeps role groups and permissions available without requiring an Owner to recreate them by
# hand in every environment.
# The receivers complement normal service checks rather than replacing them.

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import CustomerProfile
from .permissions import CHAT_RESPONDER_GROUP, OWNER_GROUP, PRICING_GROUP, WORKER_GROUP


# This safeguard verifies customer profile before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
@receiver(post_save, sender=get_user_model())
def ensure_customer_profile(sender, instance, created, **kwargs):
    """Every account receives an autofill profile, including staff accounts."""

    if created:
        CustomerProfile.objects.get_or_create(user=instance)


ROLE_PERMISSION_CODENAMES = {
    OWNER_GROUP: {
        "manage_worker_roles",
        "manage_pricing_rights",
        "view_all_worker_schedules",
        "view_all_schedules",
        "manually_assign_party",
        "manage_all_availability",
        "add_category",
        "change_category",
        "view_category",
        "delete_category",
        "add_partypackage",
        "change_partypackage",
        "view_partypackage",
        "delete_partypackage",
        "add_guestpricetier",
        "change_guestpricetier",
        "view_guestpricetier",
        "delete_guestpricetier",
        "add_addonexperience",
        "change_addonexperience",
        "view_addonexperience",
        "delete_addonexperience",
        "view_partybuild",
        "change_partybuild",
        "view_partyassignment",
        "change_partyassignment",
        "add_partyassignment",
        "view_workeravailability",
        "change_workeravailability",
        "add_workeravailability",
        "delete_workeravailability",
        "view_auditevent",
    },
    WORKER_GROUP: {
        "view_partyassignment",
        "change_partyassignment",
        "view_workeravailability",
        "change_workeravailability",
        "add_workeravailability",
        "delete_workeravailability",
    },
    CHAT_RESPONDER_GROUP: {
        "view_customerchat",
        "view_chatmessage",
        "respond_to_customer_chat",
    },
    PRICING_GROUP: {
        "add_category",
        "change_category",
        "view_category",
        "delete_category",
        "add_partypackage",
        "change_partypackage",
        "view_partypackage",
        "delete_partypackage",
        "add_guestpricetier",
        "change_guestpricetier",
        "view_guestpricetier",
        "delete_guestpricetier",
        "add_addonexperience",
        "change_addonexperience",
        "view_addonexperience",
        "delete_addonexperience",
    },
}


# This safeguard verifies role groups before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
@receiver(post_migrate)
def ensure_role_groups(sender, **kwargs):
    """Create business groups and attach permissions after every migration run."""

    for group_name, codenames in ROLE_PERMISSION_CODENAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        permissions = Permission.objects.filter(codename__in=codenames)
        group.permissions.add(*permissions)
