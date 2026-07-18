# This file protects party packages, add-ons, checkout, reviews, recommendations, and customer
# booking records with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.permissions import OWNER_GROUP
from operations.models import AuditEvent
from operations.forms import BookingStatusForm
from operations.services.bookings import change_booking_status

from .analytics import addon_popularity, recommend_addons
from .models import (
    AddonExperience,
    AddonRating,
    GuestPriceTier,
    PartyBuild,
    PartyBuildAddon,
    PartyPackage,
    PartyReview,
)
from .review_services import REVIEW_AUTH_SESSION_KEY

User = get_user_model()


# Provide shared accounts, catalogue records, and helper methods for review feature regression
# tests. Centralized fixtures keep each test focused on one permission, visibility, or persistence
# rule.
class ReviewFeatureTestMixin:
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("reviewer", password="SafePass!234")
        cls.other = User.objects.create_user("other", password="SafePass!234")
        cls.owner = User.objects.create_user("review-owner", password="SafePass!234")
        Group.objects.get_or_create(name=OWNER_GROUP)[0].user_set.add(cls.owner)
        cls.package = PartyPackage.objects.filter(is_active=True).first()
        cls.tier = GuestPriceTier.objects.filter(package=cls.package, is_active=True).first()
        cls.addons = list(AddonExperience.objects.filter(is_active=True)[:3])

    # This method handles make booking for the surrounding review feature test mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def make_booking(self, *, customer=None, status=PartyBuild.Status.COMPLETED, addons=None, event_date=None):
        booking = PartyBuild.objects.create(
            customer=customer,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Review Parent",
            contact_email="review@example.com",
            contact_phone="+30 6900000000",
            event_date=event_date or timezone.localdate() - timedelta(days=1),
            event_time="16:00",
            event_address="Athens",
            postal_code="10558",
            guest_count=self.tier.min_guests,
            guest_tier_label=self.tier.label,
            package_price=self.tier.total_price,
            addon_price=Decimal("0.00"),
            total_price=self.tier.total_price,
            status=status,
            completed_at=timezone.now() if status == PartyBuild.Status.COMPLETED else None,
        )
        for addon in addons or []:
            PartyBuildAddon.objects.create(build=booking, addon=addon, unit_price=addon.price)
        return booking


# This group of tests protects the review model and status tests behaviour as one related customer
# or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ReviewModelAndStatusTests(ReviewFeatureTestMixin, TestCase):
    # Verify that new bookings receive distinct human-readable review codes in the POP-XXXX-XXXX
    # alphabet and format.
    def test_new_bookings_receive_human_readable_unique_codes(self):
        first = self.make_booking(customer=self.user)
        second = self.make_booking(customer=self.user)
        self.assertRegex(first.review_code, r"^POP-[A-HJ-KM-NP-Z2-9]{4}-[A-HJ-KM-NP-Z2-9]{4}$")
        self.assertNotEqual(first.review_code, second.review_code)

    # Verify that lowercase, space-separated review codes are normalized back to the canonical
    # POP-XXXX-XXXX format when saved.
    def test_review_code_is_normalized_before_storage(self):
        booking = self.make_booking(customer=self.user)
        compact = booking.review_code.replace("-", " ").lower()
        booking.review_code = compact
        booking.save(update_fields=["review_code"])
        booking.refresh_from_db()
        self.assertRegex(booking.review_code, r"^POP-[A-Z2-9]{4}-[A-Z2-9]{4}$")

    # Verify that review score constraints and uniqueness. The required outcome is raises
    # ValidationError, raises IntegrityError, and raises ValidationError.
    def test_review_score_constraints_and_uniqueness(self):
        booking = self.make_booking(customer=self.user, addons=[self.addons[0]])
        review = PartyReview(booking=booking, reviewer=self.user, package_score=0)
        with self.assertRaises(ValidationError):
            review.full_clean()
        valid = PartyReview.objects.create(booking=booking, reviewer=self.user, package_score=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PartyReview.objects.create(booking=booking, reviewer=self.user, package_score=4)
        item = booking.addon_items.get()
        rating = AddonRating(review=valid, build_addon=item, score=6)
        with self.assertRaises(ValidationError):
            rating.full_clean()
        AddonRating.objects.create(review=valid, build_addon=item, score=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AddonRating.objects.create(review=valid, build_addon=item, score=4)

    # Verify that confirmed booking can be completed on or after event date. The required outcome is
    # changed status is PartyBuild.Status.COMPLETED, changed.completed_at is present, and AuditEvent
    # matching event type='booking_status_changed' exists.
    def test_confirmed_booking_can_be_completed_on_or_after_event_date(self):
        booking = self.make_booking(customer=self.user, status=PartyBuild.Status.CONFIRMED)
        changed = change_booking_status(
            booking=booking,
            status=PartyBuild.Status.COMPLETED,
            actor=self.owner,
        )
        self.assertEqual(changed.status, PartyBuild.Status.COMPLETED)
        self.assertIsNotNone(changed.completed_at)
        self.assertTrue(AuditEvent.objects.filter(event_type="booking_status_changed").exists())

    # Verify that a future confirmed booking’s status form does not offer Completed before the event
    # date arrives.
    def test_future_booking_status_form_does_not_offer_completed(self):
        booking = self.make_booking(
            customer=self.user,
            status=PartyBuild.Status.CONFIRMED,
            event_date=timezone.localdate() + timedelta(days=1),
        )
        choices = {value for value, _label in BookingStatusForm(booking=booking).fields["status"].choices}
        self.assertNotIn(PartyBuild.Status.COMPLETED, choices)

    # Verify that non-owner cannot change booking status. The required outcome is raises
    # PermissionDenied.
    def test_non_owner_cannot_change_booking_status(self):
        booking = self.make_booking(customer=self.user, status=PartyBuild.Status.CONFIRMED)
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            change_booking_status(booking=booking, status=PartyBuild.Status.COMPLETED, actor=self.user)

    # Verify that future cancelled and completed bookings cannot be completed or reversed. The
    # required outcome is raises ValidationError, raises ValidationError, and raises
    # ValidationError.
    def test_future_cancelled_and_completed_bookings_cannot_be_completed_or_reversed(self):
        future = self.make_booking(
            customer=self.user,
            status=PartyBuild.Status.CONFIRMED,
            event_date=timezone.localdate() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            change_booking_status(booking=future, status=PartyBuild.Status.COMPLETED, actor=self.owner)
        cancelled = self.make_booking(customer=self.user, status=PartyBuild.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            change_booking_status(booking=cancelled, status=PartyBuild.Status.COMPLETED, actor=self.owner)
        completed = self.make_booking(customer=self.user)
        with self.assertRaises(ValidationError):
            change_booking_status(booking=completed, status=PartyBuild.Status.CANCELLED, actor=self.owner)


# This group of tests protects the review workflow tests behaviour as one related customer or
# staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ReviewWorkflowTests(ReviewFeatureTestMixin, TestCase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    def setUp(self):
        self.booking = self.make_booking(customer=self.user, addons=self.addons[:2])
        self.review_url = reverse("party_builder:party_builder_review", args=[self.booking.public_id])
        self.submit_url = reverse("party_builder:party_builder_review_submit", args=[self.booking.public_id])

    # This method handles verify for the surrounding review workflow tests.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def verify(self, user=None, code=None):
        self.client.force_login(user or self.user)
        return self.client.post(
            reverse("party_builder:party_builder_review_code"),
            {"review_code": code or self.booking.review_code},
        )

    # This method handles valid payload for the surrounding review workflow tests.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def valid_payload(self, package_score="5"):
        data = {"package_score": package_score, "comment": "A lovely party."}
        for item in self.booking.addon_items.all():
            data[f"addon_score_{item.pk}"] = "4"
        return data

    # Verify that anonymous and direct access are blocked. The user sends GET to self.review_url;
    # the required outcome is HTTP 302 and self returns HTTP 403.
    def test_anonymous_and_direct_access_are_blocked(self):
        response = self.client.get(self.review_url)
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.review_url).status_code, 403)

    # Verify that code verification requires owner and completed booking. The required outcome is
    # HTTP 200, renders 'That party code is not valid for an eligible booking.', and does not expose
    # 'self.user.username'.
    def test_code_verification_requires_owner_and_completed_booking(self):
        response = self.verify(user=self.other)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That party code is not valid for an eligible booking.")
        self.assertNotContains(response, self.user.username)
        pending = self.make_booking(customer=self.user, status=PartyBuild.Status.CONFIRMED)
        response = self.verify(code=pending.review_code)
        self.assertContains(response, "That party code is not valid for an eligible booking.")
        guest = self.make_booking(customer=None)
        response = self.verify(code=guest.review_code)
        self.assertContains(response, "That party code is not valid for an eligible booking.")

    # Verify that code normalization accepts spacing and case. The required outcome is redirects to
    # self.review_url.
    def test_code_normalization_accepts_spacing_and_case(self):
        submitted = self.booking.review_code.lower().replace("-", " ")
        response = self.verify(code=submitted)
        self.assertRedirects(response, self.review_url)

    # Verify that expired session marker and unauthorized AJAX are denied. The user sends GET to
    # self.review_url; the required outcome is self returns HTTP 403, HTTP 403, and response.json()
    # ok is false.
    def test_expired_session_marker_and_unauthorized_ajax_are_denied(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[REVIEW_AUTH_SESSION_KEY] = {str(self.booking.public_id): 1}
        session.save()
        self.assertEqual(self.client.get(self.review_url).status_code, 403)
        response = self.client.post(
            self.submit_url,
            self.valid_payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    # Verify that review code visibility is limited to booking owner. The other sends GET to
    # self.booking.get_absolute_url(); the required outcome is renders 'self.booking.review_code',
    # self returns HTTP 404, and HTTP 200.
    def test_review_code_visibility_is_limited_to_booking_owner(self):
        self.client.force_login(self.user)
        response = self.client.get(self.booking.get_absolute_url())
        self.assertContains(response, self.booking.review_code)

        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.booking.get_absolute_url()).status_code, 404)

        guest_booking = self.make_booking(customer=None)
        self.client.logout()
        session = self.client.session
        session["party_builder_builds"] = [str(guest_booking.public_id)]
        session.save()
        response = self.client.get(guest_booking.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, guest_booking.review_code)

    # Verify that verified form contains exact booked addons. The test client sends GET to
    # self.review_url; the required outcome is redirects to self.review_url, HTTP 200, and renders
    # 'addon.name'.
    def test_verified_form_contains_exact_booked_addons(self):
        self.assertRedirects(self.verify(), self.review_url)
        response = self.client.get(self.review_url)
        self.assertEqual(response.status_code, 200)
        for addon in self.addons[:2]:
            self.assertContains(response, addon.name)
        self.assertNotContains(response, self.addons[2].name)

    # Verify that valid AJAX submission creates then updates one review. The test client sends POST
    # to self.submit_url; the required outcome is HTTP 200, response.json() ok is true, and
    # PartyReview.objects count is 1.
    def test_valid_ajax_submission_creates_then_updates_one_review(self):
        self.verify()
        response = self.client.post(
            self.submit_url,
            self.valid_payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(PartyReview.objects.count(), 1)
        self.assertEqual(AddonRating.objects.count(), 2)
        data = self.valid_payload(package_score="3")
        response = self.client.post(
            self.submit_url,
            data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PartyReview.objects.count(), 1)
        self.assertEqual(PartyReview.objects.get().package_score, 3)

    # Verify that malformed or manipulated AJAX review submissions return HTTP 400 and create no
    # PartyReview.
    def test_invalid_and_manipulated_ajax_submissions_are_rejected(self):
        self.verify()
        invalid = self.valid_payload(package_score="0")
        response = self.client.post(
            self.submit_url,
            invalid,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("package_score", response.json()["errors"])
        tampered = self.valid_payload()
        tampered["addon_score_999999"] = "5"
        response = self.client.post(
            self.submit_url,
            tampered,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PartyReview.objects.exists())

    # Verify that no addon booking and normal post fallback work. The user sends POST to
    # party_builder:party_builder_review_code; the required outcome is HTTP 302 and PartyReview
    # matching booking=booking exists.
    def test_no_addon_booking_and_normal_post_fallback_work(self):
        booking = self.make_booking(customer=self.user, addons=[])
        self.client.force_login(self.user)
        self.client.post(reverse("party_builder:party_builder_review_code"), {"review_code": booking.review_code})
        response = self.client.post(
            reverse("party_builder:party_builder_review_submit", args=[booking.public_id]),
            {"package_score": "5", "comment": "Package only."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PartyReview.objects.filter(booking=booking).exists())

    # Verify that comments are escaped. The test client sends POST to self.submit_url; the required
    # outcome is renders '&lt;script&gt;' and does not expose '<script>alert'.
    def test_comments_are_escaped(self):
        self.verify()
        data = self.valid_payload()
        data["comment"] = "<script>alert('x')</script>"
        self.client.post(self.submit_url, data)
        response = self.client.get(self.review_url)
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertNotContains(response, "<script>alert")

    # Verify that CSRF protection remains active. The user sends POST to self.submit_url; the
    # required outcome is HTTP 403.
    def test_csrf_protection_remains_active(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.submit_url, self.valid_payload())
        self.assertEqual(response.status_code, 403)


# This group of tests protects the popularity and recommendation tests behaviour as one related
# customer or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class PopularityAndRecommendationTests(ReviewFeatureTestMixin, TestCase):
    # Build a completed or alternate-status booking history for recommendation tests, adding review
    # and addon ratings only for completed parties. The helper returns the booking for later
    # assertions.
    def create_history(self, addon_list, *, status=PartyBuild.Status.COMPLETED, customer=None, score=5):
        customer = customer or self.user
        booking = self.make_booking(customer=customer, status=status, addons=addon_list)
        if status == PartyBuild.Status.COMPLETED:
            review = PartyReview.objects.create(booking=booking, reviewer=customer, package_score=score)
            for item in booking.addon_items.all():
                AddonRating.objects.create(review=review, build_addon=item, score=score)
        return booking

    # Verify that popularity uses completed distinct active bookings and threshold. The required
    # outcome is result most popular ID equals first.pk, result['by_id'][first.pk] completed booking
    # count equals 3, and addon_popularity(days=365) by ID omits first.pk.
    def test_popularity_uses_completed_distinct_active_bookings_and_threshold(self):
        first, second = self.addons[:2]
        for _ in range(3):
            self.create_history([first])
        self.create_history([second], status=PartyBuild.Status.CONFIRMED)
        result = addon_popularity(days=365)
        self.assertEqual(result["most_popular_id"], first.pk)
        self.assertEqual(result["by_id"][first.pk]["completed_booking_count"], 3)
        first.is_active = False
        first.save(update_fields=["is_active"])
        self.assertNotIn(first.pk, addon_popularity(days=365)["by_id"])

    # Verify that no popular badge below three completed bookings. The required outcome is
    # addon_popularity(days=365) most popular ID remains None.
    def test_no_popular_badge_below_three_completed_bookings(self):
        self.create_history([self.addons[0]])
        self.create_history([self.addons[0]])
        self.assertIsNone(addon_popularity(days=365)["most_popular_id"])

    # Verify that popularity tie uses verified average rating. The required outcome is
    # addon_popularity(days=365) most popular ID equals second.pk.
    def test_popularity_tie_uses_verified_average_rating(self):
        first, second = self.addons[:2]
        for _ in range(3):
            self.create_history([first], score=4)
            self.create_history([second], score=5)
        self.assertEqual(addon_popularity(days=365)["most_popular_id"], second.pk)

    # Verify that pair recommendations exclude selected inactive and uncompleted. The required
    # outcome is recommendations[0] addon equals second, recommendations[0] pair count equals 2, and
    # recommendations[0] confidence equals Decimal('1').
    def test_pair_recommendations_exclude_selected_inactive_and_uncompleted(self):
        first, second, third = self.addons
        self.create_history([first, second])
        self.create_history([first, second])
        self.create_history([first, third], status=PartyBuild.Status.CONFIRMED)
        recommendations = recommend_addons(selected_ids=[first.pk], package=self.package)
        self.assertEqual(recommendations[0]["addon"], second)
        self.assertEqual(recommendations[0]["pair_count"], 2)
        self.assertEqual(recommendations[0]["confidence"], Decimal("1"))
        self.assertNotIn(first.pk, [row["addon"].pk for row in recommendations])
        second.is_active = False
        second.save(update_fields=["is_active"])
        self.assertNotIn(second.pk, [row["addon"].pk for row in recommend_addons(selected_ids=[first.pk], package=self.package)])

    # Verify that builder displays data driven popular badge and ratings. The test client sends GET
    # to party_builder:party_builder_package_options; the required outcome is renders 'Most popular'
    # and renders '5.0 (3)'.
    def test_builder_displays_data_driven_popular_badge_and_ratings(self):
        for _ in range(3):
            self.create_history([self.addons[0]], score=5)
        response = self.client.get(reverse("party_builder:party_builder_package_options"))
        self.assertContains(response, "Most popular")
        self.assertContains(response, "5.0 (3)")

    # Verify that featured fallback is general and results are limited. The required outcome is
    # len(rows) is at most 3, row kind equals 'general', and row['reason'].lower() includes
    # 'suggestion'.
    def test_featured_fallback_is_general_and_results_are_limited(self):
        rows = recommend_addons(
            selected_ids=[self.addons[0].pk],
            package=self.package,
        )
        self.assertLessEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["kind"], "general")
            self.assertIn("suggestion", row["reason"].lower())

    # Verify that package recommendations and public JSON are minimal. The test client sends GET to
    # party_builder:party_builder_recommendations; the required outcome is rows[0] addon equals
    # self.addons[0], HTTP 200, and set(item) equals {'id', 'slug', 'name', 'short_description',
    # 'price', 'reason', 'reason_key', 'reason_values', 'pair_count'}.
    def test_package_recommendations_and_public_json_are_minimal(self):
        self.create_history([self.addons[0]])
        rows = recommend_addons(selected_ids=[], package=self.package)
        self.assertEqual(rows[0]["addon"], self.addons[0])
        response = self.client.get(
            reverse("party_builder:party_builder_recommendations"),
            {"package": "bad", "addons": ["bad", "999999,888888"]},
        )
        self.assertEqual(response.status_code, 200)
        for item in response.json()["recommendations"]:
            self.assertEqual(
                set(item),
                {"id", "slug", "name", "short_description", "price", "reason", "reason_key", "reason_values", "pair_count"},
            )
