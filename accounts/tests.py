# This file protects customer accounts, staff roles, sign-in, profile details, and permission
# boundaries with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import CustomerProfile
from .permissions import (
    can_access_full_management,
    is_administrator,
    is_owner,
    role_context,
)


User = get_user_model()


# This group of tests protects the account tests behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class AccountTests(TestCase):
    # This test protects the business rule described by “sign up creates profile and signs user
    # in”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_sign_up_creates_profile_and_signs_user_in(self):
        response = self.client.post(
            reverse("accounts:accounts_sign_up"),
            {
                "username": "parent1",
                "first_name": "Test",
                "last_name": "Parent",
                "email": "parent@example.com",
                "phone": "+30 6900000000",
                "password1": "A-complex-password-248!",
                "password2": "A-complex-password-248!",
                "privacy_consent": "on",
            },
        )
        self.assertRedirects(response, reverse("accounts:accounts_customer_dashboard"))
        user = User.objects.get(username="parent1")
        self.assertTrue(CustomerProfile.objects.filter(user=user).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    # This test protects the business rule described by “groups are bootstrapped”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_groups_are_bootstrapped(self):
        self.assertTrue(Group.objects.filter(name="Owners").exists())
        self.assertTrue(Group.objects.filter(name="Workers").exists())
        self.assertTrue(Group.objects.filter(name="Pricing Managers").exists())

    # This test protects the business rule described by “guest cannot open dashboard”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_guest_cannot_open_dashboard(self):
        response = self.client.get(reverse("accounts:accounts_customer_dashboard"))
        self.assertEqual(response.status_code, 302)

    # This test protects the business rule described by “signed in account selector is in upper
    # stripe”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_signed_in_account_selector_is_in_upper_stripe(self):
        user = User.objects.create_user("nav-user", password="pass-12345")
        self.client.force_login(user)
        response = self.client.get(reverse("core:core_home"))
        html = response.content.decode("utf-8")
        header = html.split("<header", 1)[1].split("</header>", 1)[0]

        self.assertLess(
            header.index("header-utility-stripe"),
            header.index("header-main-row"),
        )
        utility = header.split("header-utility-stripe", 1)[1].split("header-main-row", 1)[0]
        self.assertIn("header-account-selector", utility)
        self.assertIn("custom-language-picker", utility)
        self.assertIn("book-now-button", header)

    # This test protects the business rule described by “account name is escaped before
    # rendering”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_account_name_is_escaped_before_rendering(self):
        user = User.objects.create_user(
            "escaped-user",
            password="pass-12345",
            first_name="<script>alert(1)</script>",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:core_home"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    # This test protects the business rule described by “sql like username does not bypass
    # authentication”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_sql_like_username_does_not_bypass_authentication(self):
        User.objects.create_user("real-user", password="safe-pass-12345")
        response = self.client.post(
            reverse("accounts:accounts_sign_in"),
            {"username": "' OR 1=1 --", "password": "anything"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    # This test protects the business rule described by “sign up uses named grid cells for
    # alignment”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_sign_up_uses_named_grid_cells_for_alignment(self):
        response = self.client.get(reverse("accounts:accounts_sign_up"))
        self.assertContains(response, "form-field--username")
        self.assertContains(response, "form-field--first_name")
        self.assertContains(response, "form-field--privacy_consent")
        self.assertContains(response, "form-check-row")

    # This test protects the business rule described by “navigation role context reuses one group
    # lookup for customers”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_navigation_role_context_reuses_one_group_lookup_for_customers(self):
        user = User.objects.create_user("role-context-user", password="pass-12345")
        request = RequestFactory().get("/")
        request.user = user

        with CaptureQueriesContext(connection) as captured:
            context = role_context(request)

        self.assertFalse(context["nav_is_owner"])
        self.assertFalse(context["nav_is_worker"])
        self.assertEqual(len(captured), 1)

    # This test protects the business rule described by “administrator and owner are separate
    # roles”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_administrator_and_owner_are_separate_roles(self):
        administrator = User.objects.create_superuser(
            "role-admin", "role-admin@example.test", "Admin-pass-2026!"
        )
        owner = User.objects.create_user("role-owner", password="Owner-pass-2026!")
        Group.objects.get(name="Owners").user_set.add(owner)

        self.assertTrue(is_administrator(administrator))
        self.assertFalse(is_owner(administrator))
        self.assertTrue(can_access_full_management(administrator))

        self.assertFalse(is_administrator(owner))
        self.assertTrue(is_owner(owner))
        self.assertTrue(can_access_full_management(owner))

    # This test protects the business rule described by “role context exposes separate management
    # flags”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_role_context_exposes_separate_management_flags(self):
        administrator = User.objects.create_superuser(
            "context-admin", "context-admin@example.test", "Admin-pass-2026!"
        )
        request = RequestFactory().get("/")
        request.user = administrator
        context = role_context(request)

        self.assertTrue(context["nav_is_administrator"])
        self.assertFalse(context["nav_is_owner"])
        self.assertTrue(context["nav_can_access_full_management"])
        self.assertTrue(context["nav_can_create_owner"])

