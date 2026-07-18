# This file protects party packages, add-ons, checkout, reviews, recommendations, and customer
# booking records with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import PackageOptionsForm, PartyDetailsForm
from .models import AddonExperience, PartyBuild, PartyPackage
from .services import CHECKOUT_SESSION_KEY, calculate_party_quote


# This group of tests protects the party checkout tests behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class PartyCheckoutTests(TestCase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.package = PartyPackage.objects.get(slug="basic-popadoo-party")
        cls.larger_package = PartyPackage.objects.get(slug="popadoo-plus-party")
        cls.addon = AddonExperience.objects.get(slug="face-painting")

    # This method handles select options for the surrounding party checkout tests.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def select_options(self, package=None, addons=None):
        selected_package = package or self.package
        return self.client.post(
            reverse("party_builder:party_builder_package_options"),
            {
                "package": str(selected_package.pk),
                "addons": [str(item.pk) for item in (addons or [])],
            },
        )

    # Apply the submit details business action to the selected records. Validation completes before
    # any persistent change, so failures leave the existing state intact.
    def submit_details(self):
        return self.client.post(
            reverse("party_builder:party_builder_customer_details"),
            {
                "contact_name": "Test Parent",
                "contact_email": "parent@example.com",
                "contact_phone": "+30 690 000 0000",
                "event_date": (
                    timezone.localdate() + timedelta(days=14)
                ).isoformat(),
                "event_time": "16:30",
                "event_address": "Agiou Ioannou 102, Agia Paraskevi",
                "postal_code": "153 42",
                "notes": "Rainbow theme",
            },
        )

    # Verify that descriptive namespaced urls. The required outcome is
    # party_builder:party_builder_package_options equals '/party-builder/',
    # party_builder:party_builder_customer_details equals '/party-builder/details/', and
    # party_builder:party_builder_simulated_checkout equals '/party-builder/checkout/'.
    def test_descriptive_namespaced_urls(self):
        self.assertEqual(
            reverse("party_builder:party_builder_package_options"),
            "/party-builder/",
        )
        self.assertEqual(
            reverse("party_builder:party_builder_customer_details"),
            "/party-builder/details/",
        )
        self.assertEqual(
            reverse("party_builder:party_builder_simulated_checkout"),
            "/party-builder/checkout/",
        )

    # Verify that options page contains capacity packages addons and status. The test client sends
    # GET to party_builder:party_builder_package_options; the required outcome is HTTP 200, renders
    # 'Up to 10 children', and renders 'Up to 50 children'.
    def test_options_page_contains_capacity_packages_addons_and_status(self):
        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Up to 10 children")
        self.assertContains(response, "Up to 50 children")
        self.assertContains(response, self.addon.name)
        self.assertContains(response, 'aria-live="polite"')
        self.assertNotContains(response, 'name="guest_tier"')

    # Verify that the public party forms no longer accept a guest tier or exact child count; package
    # and add-on selection remain the supported inputs.
    def test_forms_no_longer_collect_a_tier_or_exact_child_count(self):
        self.assertNotIn("guest_tier", PackageOptionsForm().fields)
        self.assertNotIn("guest_count", PartyDetailsForm().fields)

    # Verify that quote uses package and database addon prices. The required outcome is
    # quote.package_price equals Decimal('255.00'), quote.addon_price equals self.addon.price, and
    # quote.total_price equals Decimal('255.00') + self.addon.price.
    def test_quote_uses_package_and_database_addon_prices(self):
        quote = calculate_party_quote(self.larger_package, [self.addon])
        self.assertEqual(quote.package_price, Decimal("255.00"))
        self.assertEqual(quote.addon_price, self.addon.price)
        self.assertEqual(
            quote.total_price,
            Decimal("255.00") + self.addon.price,
        )

    # Verify that later steps redirect when cart is missing. The test client sends GET to
    # party_builder:party_builder_customer_details; the required outcome is redirects to target and
    # redirects to target.
    def test_later_steps_redirect_when_cart_is_missing(self):
        details_response = self.client.get(
            reverse("party_builder:party_builder_customer_details")
        )
        checkout_response = self.client.get(
            reverse("party_builder:party_builder_simulated_checkout")
        )
        target = reverse("party_builder:party_builder_package_options")
        self.assertRedirects(details_response, target)
        self.assertRedirects(checkout_response, target)

    # Verify that legacy tier session key is removed. The test client sends GET to
    # party_builder:party_builder_package_options; the required outcome is HTTP 200 and
    # self.client.session checkout session key omits 'guest_tier_id'.
    def test_legacy_tier_session_key_is_removed(self):
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": self.package.pk,
            "guest_tier_id": 999999,
            "addon_ids": [],
        }
        session.save()

        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "guest_tier_id",
            self.client.session[CHECKOUT_SESSION_KEY],
        )

    # Verify that complete checkout saves capacity snapshot and safe card metadata. The test client
    # sends POST to party_builder:party_builder_simulated_checkout; the required outcome is
    # redirects to party_builder:party_builder_customer_details, redirects to
    # party_builder:party_builder_simulated_checkout, and redirects to build.get_absolute_url().
    def test_complete_checkout_saves_capacity_snapshot_and_safe_card_metadata(self):
        self.assertRedirects(
            self.select_options(package=self.larger_package, addons=[self.addon]),
            reverse("party_builder:party_builder_customer_details"),
        )
        self.assertRedirects(
            self.submit_details(),
            reverse("party_builder:party_builder_simulated_checkout"),
        )

        response = self.client.post(
            reverse("party_builder:party_builder_simulated_checkout"),
            {
                "cardholder_name": "Test Parent",
                "card_number": "4242 4242 4242 4242",
                "expiry_month": "12",
                "expiry_year": str(timezone.localdate().year + 2),
                "security_code": "123",
                "billing_postal_code": "153 42",
                "simulation_consent": "on",
            },
        )

        build = PartyBuild.objects.get()
        self.assertRedirects(response, build.get_absolute_url())
        self.assertIsNone(build.guest_tier)
        self.assertEqual(build.guest_count, self.larger_package.included_guest_count)
        self.assertEqual(build.guest_tier_label, "Up to 15 children")
        self.assertEqual(build.party_size_display, "Up to 15 children")
        self.assertEqual(build.package_price, Decimal("255.00"))
        self.assertEqual(build.addon_price, self.addon.price)
        self.assertEqual(build.total_price, Decimal("255.00") + self.addon.price)
        self.assertEqual(build.card_brand, "Visa")
        self.assertEqual(build.card_last_four, "4242")
        self.assertNotIn("4242424242424242", str(build.__dict__))
        self.assertFalse(hasattr(build, "security_code"))

    # Verify that an unapproved test card number returns the checkout form with the demo-card
    # guidance and does not create a PartyBuild.
    def test_invalid_test_card_is_rejected(self):
        self.select_options()
        self.submit_details()
        response = self.client.post(
            reverse("party_builder:party_builder_simulated_checkout"),
            {
                "cardholder_name": "Test Parent",
                "card_number": "1234 5678 9012 3456",
                "expiry_month": "12",
                "expiry_year": str(timezone.localdate().year + 2),
                "security_code": "123",
                "billing_postal_code": "153 42",
                "simulation_consent": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Use an approved demo number such as 4242 4242 4242 4242.",
        )
        self.assertFalse(PartyBuild.objects.exists())

    # Verify that details step uses custom date and time controls. The test client sends GET to
    # party_builder:party_builder_customer_details; the required outcome is renders
    # 'data-date-picker', renders 'data-time-picker', and renders 'type="hidden" name="event_date"'.
    def test_details_step_uses_custom_date_and_time_controls(self):
        self.select_options()
        response = self.client.get(
            reverse("party_builder:party_builder_customer_details")
        )
        self.assertContains(response, "data-date-picker")
        self.assertContains(response, "data-time-picker")
        self.assertContains(response, 'type="hidden" name="event_date"')
        self.assertContains(response, 'type="hidden" name="event_time"')
        self.assertNotContains(response, 'name="guest_count"')
        self.assertNotContains(response, 'type="date"')
        self.assertNotContains(response, 'type="time"')
