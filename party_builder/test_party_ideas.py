# This file protects party packages, add-ons, checkout, reviews, recommendations, and customer
# booking records with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.

from datetime import timedelta
from decimal import Decimal
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .forms import PackageOptionsForm
from .models import (
    AddonExperience,
    AddonRating,
    Category,
    GuestPriceTier,
    PartyBuild,
    PartyBuildAddon,
    PartyPackage,
    PartyReview,
)
from .services import CHECKOUT_SESSION_KEY


# This group of tests protects the party ideas tests behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class PartyIdeasTests(TestCase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.main_category = Category.objects.create(
            name="Creative Activities Test",
            slug="creative-activities-test",
            description="Hands-on creative fun",
            is_active=True,
        )
        cls.child_category = Category.objects.create(
            name="Magic Test",
            slug="magic-test",
            parent=cls.main_category,
            is_active=True,
        )
        cls.package = PartyPackage.objects.create(
            name="Creative Starter Test",
            slug="creative-starter-test",
            category=cls.main_category,
            short_description="A colourful craft party",
            base_price=Decimal("210.00"),
            duration_minutes=120,
            included_guest_count=10,
            included_experiences="Craft table\nParty games",
            is_active=True,
            display_order=30,
        )
        cls.tier = GuestPriceTier.objects.create(
            package=cls.package,
            label="1–10 children",
            min_guests=1,
            max_guests=10,
            total_price=Decimal("205.00"),
            is_default=True,
            is_active=True,
        )
        cls.addon = AddonExperience.objects.create(
            name="Magic Workshop Test",
            slug="magic-workshop-test",
            category=cls.child_category,
            short_description="Learn simple magic tricks",
            price=Decimal("55.00"),
            duration_minutes=45,
            is_featured=True,
            is_active=True,
            display_order=30,
        )
        cls.hidden_addon = AddonExperience.objects.create(
            name="Hidden Test Experience",
            slug="hidden-test-experience",
            category=cls.child_category,
            short_description="Not public",
            price=Decimal("20.00"),
            is_active=False,
        )

    # Verify that list is public and contains both catalogue types. The test client sends GET to
    # party_ideas:list; the required outcome is HTTP 200, renders 'self.package.name', and renders
    # 'self.addon.name'.
    def test_list_is_public_and_contains_both_catalogue_types(self):
        response = self.client.get(reverse("party_ideas:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.package.name)
        self.assertContains(response, self.addon.name)
        self.assertNotContains(response, self.hidden_addon.name)

    # Verify that normal search finds name description and parent category. The test client sends
    # GET to party_ideas:list; the required outcome is renders 'self.addon.name'.
    def test_normal_search_finds_name_description_and_parent_category(self):
        for query in ("Magic Workshop", "simple magic", "Creative Activities"):
            with self.subTest(query=query):
                response = self.client.get(reverse("party_ideas:list"), {"q": query})
                self.assertContains(response, self.addon.name)

    # Verify that type price duration and featured filters. The test client sends GET to
    # party_ideas:list; the required outcome is renders 'self.addon.name' and does not expose
    # 'self.package.name'.
    def test_type_price_duration_and_featured_filters(self):
        response = self.client.get(
            reverse("party_ideas:list"),
            {"type": "experience", "min_price": "50", "max_price": "60", "duration": "medium", "featured": "on"},
        )
        self.assertContains(response, self.addon.name)
        self.assertNotContains(response, self.package.name)

    # Verify that parent category includes child items. The test client sends GET to
    # party_ideas:category_detail; the required outcome is renders 'self.addon.name', renders
    # 'self.package.name', and contains a link to party_ideas:category_detail.
    def test_parent_category_includes_child_items(self):
        response = self.client.get(
            reverse("party_ideas:category_detail", args=[self.main_category.slug])
        )
        self.assertContains(response, self.addon.name)
        self.assertContains(response, self.package.name)
        self.assertContains(
            response,
            reverse("party_ideas:category_detail", args=[self.child_category.slug]),
        )

    # This test confirms that a category page offers only tabs that can display records from that
    # category. It prevents customers from being sent to an empty experience or package view.
    def test_category_pages_offer_only_idea_types_that_can_return_results(self):
        package_category = Category.objects.create(
            name="Package Only Test", slug="package-only-test", is_active=True
        )
        PartyPackage.objects.create(
            name="Package Only Party Test",
            slug="package-only-party-test",
            category=package_category,
            short_description="A package-only category",
            base_price=Decimal("190.00"),
            duration_minutes=120,
            included_guest_count=10,
            included_experiences="Games",
            is_active=True,
        )
        experience_category = Category.objects.create(
            name="Experience Only Test", slug="experience-only-test", is_active=True
        )
        AddonExperience.objects.create(
            name="Experience Only Addon Test",
            slug="experience-only-addon-test",
            category=experience_category,
            short_description="An experience-only category",
            price=Decimal("45.00"),
            is_active=True,
        )

        package_response = self.client.get(
            reverse("party_ideas:category_detail", args=[package_category.slug]),
            {"type": "experience"},
        )
        experience_response = self.client.get(
            reverse("party_ideas:category_detail", args=[experience_category.slug]),
            {"type": "package"},
        )

        self.assertEqual(
            [tab["value"] for tab in package_response.context["type_tabs"]],
            ["package"],
        )
        self.assertEqual(package_response.context["filters"]["type"], "package")
        self.assertEqual(
            [tab["value"] for tab in experience_response.context["type_tabs"]],
            ["experience"],
        )
        self.assertEqual(experience_response.context["filters"]["type"], "experience")

    # This test checks the normal list-page tabs when a category filter is active. Moving from a
    # package-only category to Experiences clears the incompatible category instead of showing a
    # result page that can only be empty.
    def test_type_tab_removes_an_incompatible_selected_category(self):
        package_category = Category.objects.create(
            name="Tab Package Test", slug="tab-package-test", is_active=True
        )
        PartyPackage.objects.create(
            name="Tab Package Party Test",
            slug="tab-package-party-test",
            category=package_category,
            short_description="A package used to verify tab links",
            base_price=Decimal("195.00"),
            duration_minutes=120,
            included_guest_count=10,
            included_experiences="Games",
            is_active=True,
        )

        response = self.client.get(
            reverse("party_ideas:list"),
            {"type": "package", "category": package_category.slug},
        )
        tabs = {tab["value"]: tab for tab in response.context["type_tabs"]}

        self.assertIn(f"category={package_category.slug}", tabs["package"]["query"])
        self.assertNotIn("category=", tabs["experience"]["query"])

    # This test protects customers from empty category choices left behind by older catalogue
    # organisation. Categories without active packages or experiences are not shown in browsing or
    # advanced filters.
    def test_empty_categories_are_not_offered_to_customers(self):
        empty_category = Category.objects.create(
            name="Empty Public Test", slug="empty-public-test", is_active=True
        )

        response = self.client.get(reverse("party_ideas:list"))
        filter_slugs = {
            category.slug
            for category in response.context["filter_form"].fields["category"].queryset
        }
        browser_slugs = {category.slug for category in response.context["main_categories"]}

        self.assertNotIn(empty_category.slug, filter_slugs)
        self.assertNotIn(empty_category.slug, browser_slugs)

    # This test verifies the builder's category controls. It keeps package-only and empty choices
    # out of the experience filter while giving each card both its detailed and parent category.
    def test_builder_category_filters_match_parent_and_child_experiences(self):
        empty_category = Category.objects.create(
            name="Empty Builder Test", slug="empty-builder-test", is_active=True
        )
        package_category = Category.objects.create(
            name="Builder Package Test", slug="builder-package-test", is_active=True
        )
        PartyPackage.objects.create(
            name="Builder Package Only Test",
            slug="builder-package-only-test",
            category=package_category,
            short_description="Not an optional experience",
            base_price=Decimal("200.00"),
            duration_minutes=120,
            included_guest_count=10,
            included_experiences="Games",
            is_active=True,
        )

        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )
        category_slugs = {category.slug for category in response.context["addon_categories"]}

        self.assertIn(self.main_category.slug, category_slugs)
        self.assertIn(self.child_category.slug, category_slugs)
        self.assertNotIn(empty_category.slug, category_slugs)
        self.assertNotIn(package_category.slug, category_slugs)
        self.assertContains(
            response,
            f'data-addon-categories="{self.child_category.slug} {self.main_category.slug}"',
        )

    # Verify that child of inactive parent is not public. The test client sends GET to
    # party_ideas:list; the required outcome is does not expose 'hidden.name', HTTP 404, and HTTP
    # 404.
    def test_child_of_inactive_parent_is_not_public(self):
        inactive_parent = Category.objects.create(
            name="Inactive Parent Test", slug="inactive-parent-test", is_active=False
        )
        child = Category.objects.create(
            name="Active Child Hidden Test",
            slug="active-child-hidden-test",
            parent=inactive_parent,
            is_active=True,
        )
        hidden = AddonExperience.objects.create(
            name="Parent Hidden Addon Test",
            slug="parent-hidden-addon-test",
            category=child,
            short_description="Hidden because the parent is inactive",
            price=Decimal("40.00"),
            is_active=True,
        )
        list_response = self.client.get(reverse("party_ideas:list"))
        detail_response = self.client.get(
            reverse("party_ideas:addon_detail", args=[hidden.slug])
        )
        action_response = self.client.post(
            reverse("party_ideas:add_addon", args=[hidden.slug])
        )
        self.assertNotContains(list_response, hidden.name)
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(action_response.status_code, 404)

    # Verify that stale session choices from hidden categories are removed. The test client sends
    # GET to party_builder:party_builder_package_options; the required outcome is HTTP 200,
    # response.context package differs from hidden_package, and does not expose 'hidden_addon.name'.
    def test_stale_session_choices_from_hidden_categories_are_removed(self):
        hidden_parent = Category.objects.create(
            name="Session Hidden Parent", slug="session-hidden-parent", is_active=False
        )
        hidden_child = Category.objects.create(
            name="Session Hidden Child",
            slug="session-hidden-child",
            parent=hidden_parent,
            is_active=True,
        )
        hidden_package = PartyPackage.objects.create(
            name="Session Hidden Package",
            slug="session-hidden-package",
            category=hidden_child,
            short_description="No longer public",
            base_price=Decimal("150.00"),
            duration_minutes=90,
            included_guest_count=8,
            included_experiences="Games",
            is_active=True,
        )
        hidden_addon = AddonExperience.objects.create(
            name="Session Hidden Experience",
            slug="session-hidden-experience",
            category=hidden_child,
            short_description="No longer public",
            price=Decimal("35.00"),
            is_featured=True,
            is_active=True,
            display_order=0,
        )
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": hidden_package.pk,
            "guest_tier_id": None,
            "addon_ids": [hidden_addon.pk],
        }
        session.save()

        response = self.client.get(reverse("party_builder:party_builder_package_options"))
        package_response = self.client.get(
            reverse("party_ideas:package_detail", args=[self.package.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.context["package"], hidden_package)
        self.assertNotContains(response, hidden_addon.name)
        self.assertNotContains(package_response, hidden_addon.name)
        self.assertEqual(self.client.session[CHECKOUT_SESSION_KEY]["addon_ids"], [])

    # Verify that malformed and duplicate session addons are normalized. The test client sends GET
    # to party_builder:party_builder_package_options; the required outcome is HTTP 200, state
    # package ID equals self.package.pk, and state omits 'guest_tier_id'.
    def test_malformed_and_duplicate_session_addons_are_normalized(self):
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": str(self.package.pk),
            "guest_tier_id": str(self.tier.pk),
            "addon_ids": [
                str(self.addon.pk),
                self.addon.pk,
                True,
                -1,
                "not-an-id",
                999999,
            ],
        }
        session.save()

        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )

        self.assertEqual(response.status_code, 200)
        state = self.client.session[CHECKOUT_SESSION_KEY]
        self.assertEqual(state["package_id"], self.package.pk)
        self.assertNotIn("guest_tier_id", state)
        self.assertEqual(state["addon_ids"], [self.addon.pk])

    # Verify that legacy tier session key is removed. The test client sends GET to
    # party_builder:party_builder_package_options; the required outcome is HTTP 200 and
    # self.client.session checkout session key omits 'guest_tier_id'.
    def test_legacy_tier_session_key_is_removed(self):
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": self.package.pk,
            "guest_tier_id": self.tier.pk,
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

    # Verify that package fallback preserves saved contact details. The test client sends GET to
    # party_builder:party_builder_package_options; the required outcome is HTTP 200, state package
    # ID differs from hidden_package.pk, and state details equals saved_details.
    def test_package_fallback_preserves_saved_contact_details(self):
        hidden_package = PartyPackage.objects.create(
            name="Archived Checkout Package",
            slug="archived-checkout-package",
            category=self.main_category,
            short_description="No longer public",
            base_price=Decimal("180.00"),
            duration_minutes=90,
            included_guest_count=8,
            included_experiences="Games",
            is_active=False,
        )
        saved_details = {
            "contact_name": "Saved Parent",
            "contact_email": "saved@example.com",
            "contact_phone": "+30 6900000000",
            "event_date": "2030-01-01",
            "event_time": "10:00",
            "event_address": "Saved address",
            "postal_code": "15342",
            "notes": "Saved note",
        }
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": hidden_package.pk,
            "guest_tier_id": self.tier.pk,
            "addon_ids": [],
            "details": saved_details,
        }
        session.save()

        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )

        self.assertEqual(response.status_code, 200)
        state = self.client.session[CHECKOUT_SESSION_KEY]
        self.assertNotEqual(state["package_id"], hidden_package.pk)
        self.assertEqual(state["details"], saved_details)
        self.assertNotIn("guest_tier_id", state)
        self.assertNotIn("details_need_review", state)

    # Verify that malformed saved details return to the details form. The test client sends GET to
    # party_builder:party_builder_simulated_checkout; the required outcome is redirects to
    # party_builder:party_builder_customer_details and self.client.session checkout session key
    # omits 'details'.
    def test_malformed_saved_details_return_to_the_details_form(self):
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": self.package.pk,
            "guest_tier_id": self.tier.pk,
            "addon_ids": [],
            "details": {"event_date": "not-a-date", "event_time": "10:00"},
        }
        session.save()

        response = self.client.get(
            reverse("party_builder:party_builder_simulated_checkout")
        )

        self.assertRedirects(
            response,
            reverse("party_builder:party_builder_customer_details"),
            fetch_redirect_response=False,
        )
        self.assertNotIn(
            "details", self.client.session[CHECKOUT_SESSION_KEY]
        )

    # Verify that public cards include CSRF tokens for session actions. The test client sends GET to
    # party_ideas:list; the required outcome is renders 'name="csrfmiddlewaretoken"'.
    def test_public_cards_include_csrf_tokens_for_session_actions(self):
        response = self.client.get(reverse("party_ideas:list"))
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    # Verify that inactive detail records return 404. The test client sends GET to
    # party_ideas:addon_detail; the required outcome is HTTP 404.
    def test_inactive_detail_records_return_404(self):
        response = self.client.get(
            reverse("party_ideas:addon_detail", args=[self.hidden_addon.slug])
        )
        self.assertEqual(response.status_code, 404)

    # Verify that package and experience detail pages load. The test client sends GET to
    # party_ideas:package_detail; the required outcome is renders 'Use this as my starting package'
    # and renders 'Add to my party'.
    def test_package_and_experience_detail_pages_load(self):
        package_response = self.client.get(
            reverse("party_ideas:package_detail", args=[self.package.slug])
        )
        addon_response = self.client.get(
            reverse("party_ideas:addon_detail", args=[self.addon.slug])
        )
        self.assertContains(package_response, "Use this as my starting package")
        self.assertContains(addon_response, "Add to my party")

    # Verify that session actions require post. The test client sends GET to
    # party_ideas:start_package; the required outcome is self returns HTTP 405 and self returns HTTP
    # 405.
    def test_session_actions_require_post(self):
        self.assertEqual(
            self.client.get(reverse("party_ideas:start_package", args=[self.package.slug])).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(reverse("party_ideas:add_addon", args=[self.addon.slug])).status_code,
            405,
        )

    # Verify that starting package sets package without a tier. The test client sends POST to
    # party_ideas:start_package; the required outcome is redirects to
    # party_builder:party_builder_package_options, state package ID equals self.package.pk, and
    # state omits 'guest_tier_id'.
    def test_starting_package_sets_package_without_a_tier(self):
        response = self.client.post(
            reverse("party_ideas:start_package", args=[self.package.slug])
        )
        self.assertRedirects(response, reverse("party_builder:party_builder_package_options"))
        state = self.client.session[CHECKOUT_SESSION_KEY]
        self.assertEqual(state["package_id"], self.package.pk)
        self.assertNotIn("guest_tier_id", state)

    # Verify that add experience is idempotent and preserves package. The test client sends POST to
    # url; the required outcome is state package ID equals self.package.pk and state addon IDs
    # equals [self.addon.pk].
    def test_add_experience_is_idempotent_and_preserves_package(self):
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {"package_id": self.package.pk, "addon_ids": []}
        session.save()
        url = reverse("party_ideas:add_addon", args=[self.addon.slug])
        self.client.post(url)
        self.client.post(url)
        state = self.client.session[CHECKOUT_SESSION_KEY]
        self.assertEqual(state["package_id"], self.package.pk)
        self.assertEqual(state["addon_ids"], [self.addon.pk])

    # Verify that builder uses session package and shows multiple packages. The test client sends
    # GET to party_builder:party_builder_package_options; the required outcome is renders
    # 'self.package.name', renders 'f\'value="{self.package.pk}"\'', and response.context package
    # equals self.package.
    def test_builder_uses_session_package_and_shows_multiple_packages(self):
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {"package_id": self.package.pk, "addon_ids": []}
        session.save()
        response = self.client.get(reverse("party_builder:party_builder_package_options"))
        self.assertContains(response, self.package.name)
        self.assertContains(response, f'value="{self.package.pk}"')
        self.assertEqual(response.context["package"], self.package)

    # Verify that PackageOptionsForm exposes package and add-on choices but no legacy guest-tier
    # field.
    def test_package_form_has_no_guest_tier_field(self):
        form = PackageOptionsForm(package=self.package)
        self.assertNotIn("guest_tier", form.fields)
        self.assertIn("package", form.fields)
        self.assertIn("addons", form.fields)

    # Verify that package form requires an explicit public package. The required outcome is
    # form.is_valid() is false and form.errors includes 'package'.
    def test_package_form_requires_an_explicit_public_package(self):
        form = PackageOptionsForm({"addons": []}, package=self.package)
        self.assertFalse(form.is_valid())
        self.assertIn("package", form.errors)

    # Verify that invalid builder submission keeps the submitted package visible. The test client
    # sends POST to party_builder:party_builder_package_options; the required outcome is HTTP 200,
    # response.context['package'].pk equals self.package.pk, and response.context selected package
    # ID equals str(self.package.pk).
    def test_invalid_builder_submission_keeps_the_submitted_package_visible(self):
        response = self.client.post(
            reverse("party_builder:party_builder_package_options"),
            {
                "package": self.package.pk,
                "addons": [self.hidden_addon.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["package"].pk, self.package.pk)
        self.assertEqual(
            response.context["selected_package_id"],
            str(self.package.pk),
        )
        self.assertIn("addons", response.context["form"].errors)

    # Verify that private review comment is not exposed on public pages. The test client sends GET
    # to party_ideas:package_detail; the required outcome is renders '5.0' and does not expose 'This
    # private sentence'.
    def test_private_review_comment_is_not_exposed_on_public_pages(self):
        user = get_user_model().objects.create_user(
            username="party-ideas-reviewer", email="reviewer@example.com", password="StrongPass123!"
        )
        build = PartyBuild.objects.create(
            customer=user,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Private Reviewer",
            contact_email=user.email,
            contact_phone="+30 6900000000",
            event_date=timezone.localdate() - timedelta(days=2),
            guest_count=8,
            guest_tier_label=self.tier.label,
            package_price=self.tier.total_price,
            addon_price=Decimal("0.00"),
            total_price=self.tier.total_price,
            status=PartyBuild.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        PartyReview.objects.create(
            booking=build,
            reviewer=user,
            package_score=5,
            comment="This private sentence must never appear publicly.",
            visibility=PartyReview.Visibility.PRIVATE,
        )
        response = self.client.get(
            reverse("party_ideas:package_detail", args=[self.package.slug])
        )
        self.assertContains(response, "5.0")
        self.assertNotContains(response, "This private sentence")


    # Verify that search is case insensitive and can find a slug. The test client sends GET to
    # party_ideas:list; the required outcome is renders 'self.addon.name' and renders
    # 'self.addon.name'.
    def test_search_is_case_insensitive_and_can_find_a_slug(self):
        lowercase = self.client.get(reverse("party_ideas:list"), {"q": "magic workshop"})
        slug = self.client.get(
            reverse("party_ideas:list"), {"q": "magic-workshop-test"}
        )
        self.assertContains(lowercase, self.addon.name)
        self.assertContains(slug, self.addon.name)

    # Verify that category and subcategory filters keep the expected scope. The test client sends
    # GET to party_ideas:list; the required outcome is renders 'self.package.name', renders
    # 'self.addon.name', and does not expose 'self.package.name'.
    def test_category_and_subcategory_filters_keep_the_expected_scope(self):
        parent_response = self.client.get(
            reverse("party_ideas:list"), {"category": self.main_category.slug}
        )
        child_response = self.client.get(
            reverse("party_ideas:list"), {"category": self.child_category.slug}
        )
        self.assertContains(parent_response, self.package.name)
        self.assertContains(parent_response, self.addon.name)
        self.assertNotContains(child_response, self.package.name)
        self.assertContains(child_response, self.addon.name)

    # Verify that maximum price and invalid sort values are handled safely. The test client sends
    # GET to party_ideas:list; the required outcome is does not expose 'self.package.name', renders
    # 'self.addon.name', and HTTP 200.
    def test_maximum_price_and_invalid_sort_values_are_handled_safely(self):
        price_response = self.client.get(
            reverse("party_ideas:list"), {"max_price": "60"}
        )
        invalid_sort_response = self.client.get(
            reverse("party_ideas:list"), {"sort": "not-a-real-order"}
        )
        self.assertNotContains(price_response, self.package.name)
        self.assertContains(price_response, self.addon.name)
        self.assertEqual(invalid_sort_response.status_code, 200)
        self.assertIn("sort", invalid_sort_response.context["filter_form"].errors)

    # Verify that minimum rating filter uses completed verified feedback. The test client sends GET
    # to party_ideas:list; the required outcome is renders 'self.package.name' and does not expose
    # 'self.addon.name'.
    def test_minimum_rating_filter_uses_completed_verified_feedback(self):
        user = get_user_model().objects.create_user(
            username="rating-filter-reviewer",
            email="rating-filter@example.com",
            password="StrongPass123!",
        )
        build = PartyBuild.objects.create(
            customer=user,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Rating Filter Reviewer",
            contact_email=user.email,
            contact_phone="+30 6900000099",
            event_date=timezone.localdate() - timedelta(days=2),
            guest_count=8,
            guest_tier_label=self.tier.label,
            package_price=self.tier.total_price,
            addon_price=Decimal("0.00"),
            total_price=self.tier.total_price,
            status=PartyBuild.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        PartyReview.objects.create(
            booking=build, reviewer=user, package_score=5
        )

        response = self.client.get(
            reverse("party_ideas:list"),
            {"type": "package", "min_rating": "4.5"},
        )

        self.assertContains(response, self.package.name)
        self.assertNotContains(response, self.addon.name)

    # Verify that package detail uses fixed package price and capacity. The test client sends GET to
    # party_ideas:package_detail; the required outcome is
    # response.context['package'].catalogue_price equals self.package.base_price, renders '€210.00',
    # and renders 'Up to 10 children'.
    def test_package_detail_uses_fixed_package_price_and_capacity(self):
        GuestPriceTier.objects.create(
            package=self.package,
            label="Legacy 11–20 children",
            min_guests=11,
            max_guests=20,
            total_price=Decimal("190.00"),
            is_active=True,
        )
        response = self.client.get(
            reverse("party_ideas:package_detail", args=[self.package.slug])
        )
        self.assertEqual(response.context["package"].catalogue_price, self.package.base_price)
        self.assertContains(response, "€210.00")
        self.assertContains(response, "Up to 10 children")
        self.assertNotContains(response, "Legacy 11–20 children")
        self.assertNotContains(response, "From €")

    # Verify that inactive catalogue records cannot be added through post actions. The test client
    # sends POST to party_ideas:start_package; the required outcome is HTTP 404 and HTTP 404.
    def test_inactive_catalogue_records_cannot_be_added_through_post_actions(self):
        self.package.is_active = False
        self.package.save(update_fields=["is_active"])
        package_response = self.client.post(
            reverse("party_ideas:start_package", args=[self.package.slug])
        )
        addon_response = self.client.post(
            reverse("party_ideas:add_addon", args=[self.hidden_addon.slug])
        )
        self.assertEqual(package_response.status_code, 404)
        self.assertEqual(addon_response.status_code, 404)

    # Verify that form rejects inactive experiences. The required outcome is form.is_valid() is
    # false and form.errors includes 'addons'.
    def test_form_rejects_inactive_experiences(self):
        form = PackageOptionsForm(
            {
                "package": self.package.pk,
                "addons": [self.hidden_addon.pk],
            },
            package=self.package,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("addons", form.errors)

    # Verify that switching package preserves existing contact details. The test client sends POST
    # to party_ideas:start_package; the required outcome is state package ID equals self.package.pk,
    # state details equals saved_details, and state omits 'guest_tier_id'.
    def test_switching_package_preserves_existing_contact_details(self):
        other_package = (
            PartyPackage.objects.filter(is_active=True)
            .exclude(pk=self.package.pk)
            .first()
        )
        saved_details = {"contact_name": "Saved Parent", "event_date": "2030-01-01"}
        session = self.client.session
        session[CHECKOUT_SESSION_KEY] = {
            "package_id": other_package.pk,
            "guest_tier_id": self.tier.pk,
            "addon_ids": [],
            "details": saved_details,
        }
        session.save()

        self.client.post(
            reverse("party_ideas:start_package", args=[self.package.slug])
        )

        state = self.client.session[CHECKOUT_SESSION_KEY]
        self.assertEqual(state["package_id"], self.package.pk)
        self.assertEqual(state["details"], saved_details)
        self.assertNotIn("guest_tier_id", state)
        self.assertNotIn("details_need_review", state)


    # Verify that capacity filter returns packages large enough for the party. The test client sends
    # GET to party_ideas:list; the required outcome is does not expose 'Basic P Kids Events Party',
    # renders 'P Kids Events Plus Party', and renders 'P Kids Events Festival Party'.
    def test_capacity_filter_returns_packages_large_enough_for_the_party(self):
        response = self.client.get(
            reverse("party_ideas:list"),
            {"type": "package", "capacity": "15"},
        )
        self.assertNotContains(response, "Basic P Kids Events Party")
        self.assertContains(response, "P Kids Events Plus Party")
        self.assertContains(response, "P Kids Events Festival Party")

    # Verify that capacity_asc places the Basic package before the Festival package, while
    # capacity_desc reverses that order.
    def test_capacity_sorting_orders_packages_by_size(self):
        ascending = self.client.get(
            reverse("party_ideas:list"),
            {"type": "package", "sort": "capacity_asc"},
        )
        descending = self.client.get(
            reverse("party_ideas:list"),
            {"type": "package", "sort": "capacity_desc"},
        )
        ascending_names = [
            card["name"] for card in ascending.context["page_obj"].object_list
        ]
        descending_names = [
            card["name"] for card in descending.context["page_obj"].object_list
        ]
        self.assertLess(
            ascending_names.index("Basic P Kids Events Party"),
            ascending_names.index("P Kids Events Festival Party"),
        )
        self.assertLess(
            descending_names.index("P Kids Events Festival Party"),
            descending_names.index("Basic P Kids Events Party"),
        )

    # Verify that seeded catalogue contains eight packages and twenty experiences. The required
    # outcome is set(PartyPackage.objects.filter(slug__in=package_slugs,
    # is_active=True).values_list('slug', flat=True)) equals package_slugs,
    # set(AddonExperience.objects.filter(slug__in=addon_slugs, is_active=True).values_list('slug',
    # flat=True)) equals addon_slugs, and PartyPackage.objects.filter(slug__in=package_slugs,
    # is_default=True) count is 1.
    def test_seeded_catalogue_contains_eight_packages_and_twenty_experiences(self):
        package_slugs = {
            "basic-popadoo-party",
            "popadoo-plus-party",
            "popadoo-classic-party",
            "popadoo-big-party",
            "popadoo-xl-party",
            "popadoo-mega-party",
            "popadoo-super-party",
            "popadoo-festival-party",
        }
        addon_slugs = {
            "face-painting",
            "balloon-modelling",
            "treasure-hunt",
            "creative-craft-workshop",
            "mini-magic-show",
            "themed-balloon-decoration",
            "extra-entertainer",
            "party-favour-pack",
            "bubble-show",
            "kids-disco-dance-games",
            "slime-laboratory",
            "junior-science-experiments",
            "character-visit",
            "superhero-training",
            "puppet-show",
            "karaoke-party",
            "party-photo-booth",
            "glitter-tattoos",
            "cupcake-decorating",
            "pinata-game",
        }
        self.assertEqual(
            set(
                PartyPackage.objects.filter(
                    slug__in=package_slugs,
                    is_active=True,
                ).values_list("slug", flat=True)
            ),
            package_slugs,
        )
        self.assertEqual(
            set(
                AddonExperience.objects.filter(
                    slug__in=addon_slugs,
                    is_active=True,
                ).values_list("slug", flat=True)
            ),
            addon_slugs,
        )
        self.assertEqual(
            PartyPackage.objects.filter(slug__in=package_slugs, is_default=True).count(),
            1,
        )

    # Verify that catalogue seed is idempotent and preserves legacy booking snapshots. The required
    # outcome is PartyPackage.objects count is first_package_count, AddonExperience.objects count is
    # first_addon_count, and legacy.guest_tier_id equals self.tier.pk.
    def test_catalogue_seed_is_idempotent_and_preserves_legacy_booking_snapshots(self):
        user = get_user_model().objects.create_user(
            username="migration-history-user",
            email="migration-history@example.com",
            password="StrongPass123!",
        )
        legacy = PartyBuild.objects.create(
            customer=user,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Legacy Parent",
            contact_email=user.email,
            contact_phone="+30 6900000042",
            event_date=timezone.localdate() - timedelta(days=1),
            guest_count=7,
            guest_tier_label=self.tier.label,
            package_price=Decimal("205.00"),
            addon_price=Decimal("0.00"),
            total_price=Decimal("205.00"),
        )
        seed = import_module(
            "party_builder.migrations.0014_seed_capacity_packages_and_experiences"
        ).seed_capacity_packages_and_experiences

        seed(django_apps, None)
        first_package_count = PartyPackage.objects.count()
        first_addon_count = AddonExperience.objects.count()
        seed(django_apps, None)

        legacy.refresh_from_db()
        self.assertEqual(PartyPackage.objects.count(), first_package_count)
        self.assertEqual(AddonExperience.objects.count(), first_addon_count)
        self.assertEqual(legacy.guest_tier_id, self.tier.pk)
        self.assertEqual(legacy.guest_count, 7)
        self.assertEqual(legacy.guest_tier_label, self.tier.label)
        self.assertEqual(legacy.package_price, Decimal("205.00"))
        self.assertEqual(legacy.total_price, Decimal("205.00"))

    # Verify that pagination preserves filters. The test client sends GET to party_ideas:list; the
    # required outcome is response.context['paginator'].num_pages equals 2, renders
    # 'q=Extra+Search', and renders 'type=experience'.
    def test_pagination_preserves_filters(self):
        for index in range(13):
            AddonExperience.objects.create(
                name=f"Extra Search Test {index}",
                slug=f"extra-search-test-{index}",
                category=self.child_category,
                short_description="Searchable extra",
                price=Decimal("25.00"),
                duration_minutes=20,
                is_active=True,
                display_order=50 + index,
            )
        response = self.client.get(
            reverse("party_ideas:list"), {"q": "Extra Search", "type": "experience"}
        )
        self.assertEqual(response.context["paginator"].num_pages, 2)
        self.assertContains(response, "q=Extra+Search")
        self.assertContains(response, "type=experience")

    # Verify that list query count does not grow per card. The test client sends GET to
    # party_ideas:list; the required outcome is HTTP 200 and len(captured) is at most 16.
    def test_list_query_count_does_not_grow_per_card(self):
        for index in range(8):
            AddonExperience.objects.create(
                name=f"Query Test {index}",
                slug=f"query-test-{index}",
                category=self.child_category,
                short_description="Query count fixture",
                price=Decimal("30.00"),
                is_active=True,
            )
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("party_ideas:list"))
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 16)

    # Verify that package detail does not render legacy tiers. The test client sends GET to
    # party_ideas:package_detail; the required outcome is does not expose 'Archived tier' and does
    # not expose 'Guest-price tiers'.
    def test_package_detail_does_not_render_legacy_tiers(self):
        GuestPriceTier.objects.create(
            package=self.package,
            label="Archived tier",
            min_guests=11,
            max_guests=12,
            total_price=Decimal("999.00"),
            is_active=False,
        )
        response = self.client.get(
            reverse("party_ideas:package_detail", args=[self.package.slug])
        )
        self.assertNotContains(response, "Archived tier")
        self.assertNotContains(response, "Guest-price tiers")

    # Verify that incomplete review does not change public rating. The test client sends GET to
    # party_ideas:package_detail; the required outcome is renders 'No ratings yet'.
    def test_incomplete_review_does_not_change_public_rating(self):
        user = get_user_model().objects.create_user(
            username="incomplete-reviewer",
            email="incomplete@example.com",
            password="StrongPass123!",
        )
        build = PartyBuild.objects.create(
            customer=user,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Incomplete Reviewer",
            contact_email=user.email,
            contact_phone="+30 6900000002",
            event_date=timezone.localdate() + timedelta(days=2),
            guest_count=8,
            guest_tier_label=self.tier.label,
            package_price=self.tier.total_price,
            addon_price=Decimal("0.00"),
            total_price=self.tier.total_price,
            status=PartyBuild.Status.SUBMITTED,
        )
        # Direct creation represents legacy or imported data; public queries
        # still require a completed booking before counting the score.
        PartyReview.objects.bulk_create(
            [PartyReview(booking=build, reviewer=user, package_score=1)]
        )
        response = self.client.get(
            reverse("party_ideas:package_detail", args=[self.package.slug])
        )
        self.assertContains(response, "No ratings yet")

    # Verify that completed addon rating contributes to public average. The test client sends GET to
    # party_ideas:addon_detail; the required outcome is renders '5.0' and does not expose 'Private
    # add-on note'.
    def test_completed_addon_rating_contributes_to_public_average(self):
        user = get_user_model().objects.create_user(
            username="addon-reviewer", email="addon@example.com", password="StrongPass123!"
        )
        build = PartyBuild.objects.create(
            customer=user,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Addon Reviewer",
            contact_email=user.email,
            contact_phone="+30 6900000001",
            event_date=timezone.localdate() - timedelta(days=2),
            guest_count=8,
            guest_tier_label=self.tier.label,
            package_price=self.tier.total_price,
            addon_price=self.addon.price,
            total_price=self.tier.total_price + self.addon.price,
            status=PartyBuild.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        build_addon = PartyBuildAddon.objects.create(build=build, addon=self.addon, unit_price=self.addon.price)
        review = PartyReview.objects.create(booking=build, reviewer=user, package_score=4)
        AddonRating.objects.create(review=review, build_addon=build_addon, score=5, comment="Private add-on note")
        response = self.client.get(reverse("party_ideas:addon_detail", args=[self.addon.slug]))
        self.assertContains(response, "5.0")
        self.assertNotContains(response, "Private add-on note")

    # Verify that recommendation cards use aligned content and footer structure. The test client
    # sends GET to party_builder:party_builder_package_options; the required outcome is renders
    # 'class="recommendation-card-content"', renders 'class="recommendation-card-footer"', and
    # renders 'class="recommendation-price"'.
    def test_recommendation_cards_use_aligned_content_and_footer_structure(self):
        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )
        self.assertContains(response, 'class="recommendation-card-content"')
        self.assertContains(response, 'class="recommendation-card-footer"')
        self.assertContains(response, 'class="recommendation-price"')
        self.assertContains(response, "recommendation-action")

    # Verify that recommendation CSS uses one canonical card layout. The required outcome is css
    # count is 1, css count is 1, and css includes 'grid-auto-rows: 1fr'.
    def test_recommendation_css_uses_one_canonical_card_layout(self):
        from django.conf import settings

        css = (settings.BASE_DIR / "static/css/party-builder.css").read_text()
        self.assertEqual(css.count(".recommendation-card {"), 1)
        self.assertEqual(css.count(".recommendation-card-footer {"), 1)
        self.assertIn("grid-auto-rows: 1fr", css)
        self.assertIn("display: flex", css)
        self.assertIn("flex: 1 1 auto", css)
        self.assertIn("min-height: 4.5rem", css)

    # Verify that JavaScript-created recommendation cards use the same content, footer, price, and
    # action classes as the server-rendered layout.
    def test_javascript_recommendations_use_the_same_alignment_classes(self):
        from django.conf import settings

        script = (settings.BASE_DIR / "static/js/party-builder.js").read_text()
        self.assertIn('content.className = "recommendation-card-content"', script)
        self.assertIn('footer.className = "recommendation-card-footer"', script)
        self.assertIn('price.className = "recommendation-price"', script)
        self.assertIn('button.className = "button button-outline recommendation-action"', script)
    # Verify that builder copy and catalogue cards have translation hooks. The test client sends GET
    # to party_builder:party_builder_package_options; the required outcome is renders
    # 'data-i18n="builder.browseIntro"', renders 'data-i18n="builder.packageChoiceHelp"', and
    # renders 'data-i18n="builder.recommendationHelp"'.
    def test_builder_copy_and_catalogue_cards_have_translation_hooks(self):
        response = self.client.get(
            reverse("party_builder:party_builder_package_options")
        )
        self.assertContains(response, 'data-i18n="builder.browseIntro"')
        self.assertContains(response, 'data-i18n="builder.packageChoiceHelp"')
        self.assertContains(response, 'data-i18n="builder.recommendationHelp"')
        self.assertContains(
            response,
            f'data-catalogue-i18n="catalogue.package.{self.package.slug}.name"',
        )
        self.assertContains(
            response,
            f'data-catalogue-i18n="catalogue.addon.{self.addon.slug}.name"',
        )

    # Verify that the Greek translation catalogue contains the party total, Basic package name, and
    # face-painting experience labels read by the builder.
    def test_greek_builder_catalogue_translations_are_present(self):
        from django.conf import settings

        # The translation catalogue contains Greek text, so the test reads it using
        # the same UTF-8 encoding used by browsers and Linux deployment servers.
        catalog = (
            settings.BASE_DIR / "static/js/translations.js"
        ).read_text(encoding="utf-8")        
        self.assertIn('"builder.partyTotal": "Σύνολο πάρτι"', catalog)
        self.assertIn(
            '"catalogue.package.basic-popadoo-party.name": "Βασικό Πάρτι P Kids Events"',
            catalog,
        )
        self.assertIn(
            '"catalogue.addon.face-painting.name": "Ζωγραφική Προσώπου"',
            catalog,
        )

    # Verify that recommendation JSON contains translation metadata. The test client sends GET to
    # party_builder:party_builder_recommendations; the required outcome is HTTP 200, recommendations
    # is true, and recommendations[0] includes 'slug'.
    def test_recommendation_json_contains_translation_metadata(self):
        response = self.client.get(
            reverse("party_builder:party_builder_recommendations"),
            {"package": self.package.pk},
        )
        self.assertEqual(response.status_code, 200)
        recommendations = response.json()["recommendations"]
        self.assertTrue(recommendations)
        self.assertIn("slug", recommendations[0])
        self.assertIn("reason_key", recommendations[0])
        self.assertIn("reason_values", recommendations[0])
