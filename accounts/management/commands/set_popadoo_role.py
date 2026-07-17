# This module supports customer accounts, staff roles, sign-in, profile details, and permission
# boundaries.
# It keeps this responsibility in one place so nearby pages and services can reuse the same
# behaviour without duplication.

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from accounts.models import WorkerProfile
from accounts.permissions import CHAT_RESPONDER_GROUP, OWNER_GROUP, PRICING_GROUP, WORKER_GROUP


# This management command carries out command from the command line.
# It uses the same project services and safeguards as the website rather than changing records
# through a separate shortcut.
class Command(BaseCommand):
    """Local administration helper for assigning an existing account's role."""

    help = "Assign an existing user to a Popadoo customer, worker, delegated worker, or owner role."

    # This business action carries out add arguments.
    # It validates the live records and permissions before changing anything, then keeps related
    # updates together so partial results are not left behind.
    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "role",
            choices=("customer", "worker", "pricing-manager", "chat-responder", "pricing-chat-responder", "owner"),
        )

    # Django calls this method when the management command runs; it validates the requested action
    # and reports a clear result to the operator.
    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("No user exists with that username.") from exc

        if user.is_superuser:
            raise CommandError(
                "Administrator accounts are protected and cannot be assigned a business role."
            )

        role = options["role"]
        owners, _ = Group.objects.get_or_create(name=OWNER_GROUP)
        workers, _ = Group.objects.get_or_create(name=WORKER_GROUP)
        pricing, _ = Group.objects.get_or_create(name=PRICING_GROUP)
        chat_responders, _ = Group.objects.get_or_create(name=CHAT_RESPONDER_GROUP)

        owners.user_set.remove(user)
        workers.user_set.remove(user)
        pricing.user_set.remove(user)
        chat_responders.user_set.remove(user)

        profile = getattr(user, "worker_profile", None)
        if profile:
            profile.is_active_worker = False
            profile.save(update_fields=["is_active_worker", "updated_at"])

        if role == "owner":
            user.is_staff = False
            user.is_superuser = False
            user.save(update_fields=["is_staff", "is_superuser"])
            owners.user_set.add(user)
        elif role in {"worker", "pricing-manager", "chat-responder", "pricing-chat-responder"}:
            workers.user_set.add(user)
            profile, _ = WorkerProfile.objects.get_or_create(user=user)
            profile.is_active_worker = True
            profile.save(update_fields=["is_active_worker", "updated_at"])
            if role in {"pricing-manager", "pricing-chat-responder"}:
                pricing.user_set.add(user)
            if role in {"chat-responder", "pricing-chat-responder"}:
                chat_responders.user_set.add(user)

        self.stdout.write(self.style.SUCCESS(f"{user.username} is now a {role}."))
