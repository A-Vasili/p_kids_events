# This module supports customer accounts, staff roles, sign-in, profile details, and permission
# boundaries.
# It keeps this responsibility in one place so nearby pages and services can reuse the same
# behaviour without duplication.

from django.core.management.base import BaseCommand

from accounts.signals import ensure_role_groups


# This management command carries out command from the command line.
# It uses the same project services and safeguards as the website rather than changing records
# through a separate shortcut.
class Command(BaseCommand):
    help = "Create Popadoo role groups and attach their Django permissions."

    # Django calls this method when the management command runs; it validates the requested action
    # and reports a clear result to the operator.
    def handle(self, *args, **options):
        ensure_role_groups(sender=None)
        self.stdout.write(self.style.SUCCESS("Popadoo role groups are ready."))
