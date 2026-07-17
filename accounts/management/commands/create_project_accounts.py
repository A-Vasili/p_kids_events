# This module supports customer accounts, staff roles, sign-in, profile details, and permission
# boundaries.
# It keeps this responsibility in one place so nearby pages and services can reuse the same
# behaviour without duplication.

from __future__ import annotations

import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import CustomerProfile, WorkerProfile
from accounts.permissions import OWNER_GROUP, PRICING_GROUP, WORKER_GROUP
from accounts.signals import ensure_role_groups


User = get_user_model()


# This management command carries out command from the command line.
# It uses the same project services and safeguards as the website rather than changing records
# through a separate shortcut.
class Command(BaseCommand):
    help = (
        "Create one owner, five workers, and ten customers with generated "
        "temporary passwords."
    )

    # This action carries out add arguments.
    # It validates the live records and permissions before changing anything, then keeps related
    # updates together so partial results are not left behind.
    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Generate new passwords for matching existing demo accounts.",
        )

    # This method handles temporary password for the surrounding command.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @staticmethod
    def _temporary_password() -> str:
        """Return a strong, readable temporary password without hardcoding it."""

        alphabet = string.ascii_letters + string.digits + "!@#$%"
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(18))
            if (
                any(char.islower() for char in password)
                and any(char.isupper() for char in password)
                and any(char.isdigit() for char in password)
                and any(char in "!@#$%" for char in password)
            ):
                return password

    # This action carries out the create or update user.
    # It validates the live records and permissions before changing anything, then keeps related
    # updates together so partial results are not left behind.
    def _create_or_update_user(
        self,
        *,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        reset_passwords: bool,
    ):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        if not created:
            # Existing accounts keep their password unless the administrator
            # deliberately asks for a reset.
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False

        password = None
        if created or reset_passwords:
            password = self._temporary_password()
            user.set_password(password)

        user.save()
        CustomerProfile.objects.get_or_create(user=user)
        return user, password

    # Django calls this method when the management command runs; it validates the requested action
    # and reports a clear result to the operator.
    @transaction.atomic
    def handle(self, *args, **options):
        ensure_role_groups(sender=None)
        reset_passwords = options["reset_passwords"]

        owner_group = Group.objects.get(name=OWNER_GROUP)
        worker_group = Group.objects.get(name=WORKER_GROUP)
        pricing_group = Group.objects.get(name=PRICING_GROUP)

        existing_other_owners = (
            User.objects.filter(groups=owner_group)
            .exclude(username="owner_demo")
            .distinct()
        )
        if existing_other_owners.exists():
            raise CommandError(
                "Another owner already exists. Review owner accounts before "
                "running this demonstration setup command."
            )

        credentials = []

        # Demonstration accounts now use the hosted project identity so generated profiles do not display the original company name.
        owner, password = self._create_or_update_user(
            username="owner_demo",
            email="owner@pkidsevents.test",
            first_name="P Kids Events",
            last_name="Owner",
            reset_passwords=reset_passwords,
        )
        owner.groups.clear()
        owner_group.user_set.add(owner)
        if password:
            credentials.append(("Owner", owner.username, password))

        for number in range(1, 6):
            username = f"worker{number:02d}"
            worker, password = self._create_or_update_user(
                username=username,
                email=f"{username}@pkidsevents.test",
                first_name="Worker",
                last_name=f"{number:02d}",
                reset_passwords=reset_passwords,
            )
            worker.groups.clear()
            worker_group.user_set.add(worker)
            profile, _ = WorkerProfile.objects.get_or_create(user=worker)
            profile.display_name = worker.get_full_name()
            profile.is_active_worker = True
            profile.save(
                update_fields=["display_name", "is_active_worker", "updated_at"]
            )
            if password:
                credentials.append(("Worker", worker.username, password))

        for number in range(1, 11):
            username = f"customer{number:02d}"
            customer, password = self._create_or_update_user(
                username=username,
                email=f"{username}@example.test",
                first_name="Customer",
                last_name=f"{number:02d}",
                reset_passwords=reset_passwords,
            )
            customer.groups.clear()
            # Customers must not retain a staff profile from an earlier role.
            profile = getattr(customer, "worker_profile", None)
            if profile:
                profile.is_active_worker = False
                profile.save(update_fields=["is_active_worker", "updated_at"])
            if password:
                credentials.append(("Customer", customer.username, password))

        # This project keeps pricing delegation empty initially. The owner can
        # grant it later through the protected worker-management page.
        pricing_group.user_set.clear()

        self.stdout.write(self.style.SUCCESS(
            "Project accounts are ready: 1 owner, 5 workers, and 10 customers."
        ))

        if credentials:
            self.stdout.write("\nTemporary credentials (shown once):")
            for role, username, password in credentials:
                self.stdout.write(f"{role:8}  {username:12}  {password}")
            self.stdout.write(
                "\nStore these securely and change them before deployment."
            )
        else:
            self.stdout.write(
                "No passwords were changed. Use --reset-passwords to generate new ones."
            )
