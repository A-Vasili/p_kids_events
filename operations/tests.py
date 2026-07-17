# This file protects worker tasks and the custom management area used by Owners and Administrators
# with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WorkerProfile
from party_builder.models import GuestPriceTier, PartyBuild, PartyPackage
from party_builder.review_services import verify_review_code

from .models import AuditEvent, PartyAssignment, WorkerAvailability
from .services.assignment import accept_assignment, offer_assignment
from .services.bookings import mark_booking_completed


User = get_user_model()


# This group of tests protects the operations permission tests behaviour as one related customer
# or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class OperationsPermissionTests(TestCase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user("customer", password="pass-12345")
        cls.worker_user = User.objects.create_user("worker", password="pass-12345")
        cls.other_worker_user = User.objects.create_user("worker2", password="pass-12345")
        cls.owner = User.objects.create_user("owner", password="pass-12345")
        Group.objects.get(name="Workers").user_set.add(cls.worker_user, cls.other_worker_user)
        Group.objects.get(name="Owners").user_set.add(cls.owner)
        cls.worker = WorkerProfile.objects.create(user=cls.worker_user, display_name="Worker One")
        cls.other_worker = WorkerProfile.objects.create(user=cls.other_worker_user, display_name="Worker Two")
        cls.package = PartyPackage.objects.get(slug="basic-popadoo-party")
        cls.tier = GuestPriceTier.objects.filter(package=cls.package).first()

    # This method handles make build for the surrounding operations permission tests.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def make_build(self, event_date=None):
        return PartyBuild.objects.create(
            package=self.package,
            guest_tier=self.tier,
            contact_name="Test Parent",
            contact_email="parent@example.com",
            contact_phone="+306900000000",
            event_date=event_date or (timezone.localdate() + timedelta(days=5)),
            event_time=timezone.datetime.strptime("16:00", "%H:%M").time(),
            event_address="Athens",
            postal_code="10558",
            guest_count=8,
            guest_tier_label=self.tier.label,
            package_price=Decimal("180.00"),
            addon_price=Decimal("0.00"),
            total_price=Decimal("180.00"),
        )

    # This business action carries out add availability.
    # It validates the live records and permissions before changing anything, then keeps related
    # updates together so partial results are not left behind.
    def add_availability(self, worker, build):
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(build.event_date, build.event_time), tz)
        WorkerAvailability.objects.create(
            worker=worker,
            start_at=start - timedelta(hours=1),
            end_at=start + timedelta(hours=5),
            availability_type=WorkerAvailability.AvailabilityType.AVAILABLE,
        )

    # This test protects the business rule described by “customer cannot access operations”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_customer_cannot_access_operations(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("operations:operations_dashboard"))
        self.assertEqual(response.status_code, 403)

    # This test protects the business rule described by “worker sees only own assignment”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_worker_sees_only_own_assignment(self):
        build = self.make_build()
        assignment = PartyAssignment.objects.create(party_build=build, worker=self.other_worker)
        self.client.force_login(self.worker_user)
        response = self.client.get(
            reverse("operations:operations_worker_assignment_detail", args=[assignment.pk])
        )
        self.assertEqual(response.status_code, 404)

    # This test protects the business rule described by “available worker receives and accepts
    # offer”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_available_worker_receives_and_accepts_offer(self):
        build = self.make_build()
        self.add_availability(self.worker, build)
        assignment = offer_assignment(build.pk)
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, PartyAssignment.Status.PENDING)
        accept_assignment(assignment_id=assignment.pk, worker=self.worker)
        build.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, PartyAssignment.Status.ACCEPTED)
        self.assertEqual(build.assignment_state, PartyBuild.AssignmentState.ASSIGNED)

    # This test protects the business rule described by “no available worker requires owner
    # review”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_no_available_worker_requires_owner_review(self):
        build = self.make_build()
        self.assertIsNone(offer_assignment(build.pk))
        build.refresh_from_db()
        self.assertEqual(build.assignment_state, PartyBuild.AssignmentState.MANUAL_REVIEW)


    # This test protects the business rule described by “worker accounts use dedicated creation
    # workflow”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_worker_accounts_use_dedicated_creation_workflow(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(
                reverse(
                    "management:management_user_action",
                    args=[self.customer.pk, "promote"],
                ),
                {"confirmation": "on"},
            ).status_code,
            404,
        )

        response = self.client.post(
            reverse("management:management_user_create_worker"),
            {
                "username": "dedicated-worker",
                "first_name": "Dedicated",
                "last_name": "Worker",
                "email": "dedicated-worker@example.test",
                "phone": "+306900001234",
                "password1": "A9!Quartz-Celebration-582",
                "password2": "A9!Quartz-Celebration-582",
            },
        )
        worker = User.objects.get(username="dedicated-worker")
        self.assertRedirects(
            response,
            reverse("management:management_user_detail", args=[worker.pk]),
        )
        self.assertTrue(worker.groups.filter(name="Workers").exists())
        self.assertTrue(worker.worker_profile.is_active_worker)

    # This test protects the business rule described by “pricing manager can access catalogue
    # only”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_pricing_manager_can_access_catalogue_only(self):
        Group.objects.get(name="Pricing Managers").user_set.add(self.worker_user)
        self.client.force_login(self.worker_user)
        self.assertEqual(
            self.client.get(reverse("management:management_catalogue")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("management:management_user_list")).status_code,
            403,
        )

    # This test protects the business rule described by “normal worker cannot open catalogue
    # management”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_normal_worker_cannot_open_catalogue_management(self):
        self.client.force_login(self.other_worker_user)
        self.assertEqual(
            self.client.get(reverse("management:management_catalogue")).status_code,
            403,
        )

    # This test protects the business rule described by “owner and superuser use management not
    # worker dashboard”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_and_superuser_use_management_not_worker_dashboard(self):
        for user in (
            self.owner,
            User.objects.create_superuser(
                "admin_test", "admin@example.com", "pass-12345"
            ),
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("operations:operations_dashboard"))
                self.assertRedirects(
                    response,
                    reverse("management:management_dashboard"),
                )
                self.assertEqual(
                    self.client.get(reverse("management:management_dashboard")).status_code,
                    200,
                )

    # This test protects the business rule described by “legacy owner get routes redirect to
    # management”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_legacy_owner_get_routes_redirect_to_management(self):
        self.client.force_login(self.owner)
        routes = {
            "operations:operations_owner_workers": "management:management_user_list",
            "operations:operations_owner_worker_create": "management:management_user_create_worker",
            "operations:operations_owner_schedule": "management:management_schedule",
            "operations:operations_owner_pricing": "management:management_catalogue",
            "operations:operations_owner_audit": "management:management_audit",
        }
        for legacy, canonical in routes.items():
            with self.subTest(legacy=legacy):
                response = self.client.get(reverse(legacy))
                self.assertRedirects(
                    response,
                    reverse(canonical),
                    status_code=301,
                )

    # This test protects the business rule described by “legacy integer assignment route redirects
    # to uuid management route”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_legacy_integer_assignment_route_redirects_to_uuid_management_route(self):
        booking = self.make_build()
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse(
                "operations:operations_owner_manual_assignment",
                args=[booking.pk],
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "management:management_booking_assign",
                args=[booking.public_id],
            ),
            status_code=301,
        )

    # This test protects the business rule described by “availability form uses custom datetime
    # controls”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_availability_form_uses_custom_datetime_controls(self):
        self.client.force_login(self.worker_user)
        response = self.client.get(
            reverse("operations:operations_worker_availability")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-custom-datetime')
        self.assertContains(response, 'type="hidden" name="start_at"')
        self.assertContains(response, 'type="hidden" name="end_at"')
        self.assertNotContains(response, 'type="datetime-local"')


# This group of tests protects the owner account management tests behaviour as one related
# customer or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class OwnerAccountManagementTests(TestCase):
    """Checks for the owner-only worker account workflow and account isolation."""

    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "owner-manager",
            password="Owner-test-pass-123!",
            email="owner-manager@example.test",
        )
        cls.other_owner = User.objects.create_user(
            "other-owner",
            password="Owner-test-pass-456!",
            email="other-owner@example.test",
        )
        owners = Group.objects.get(name="Owners")
        owners.user_set.add(cls.owner, cls.other_owner)

    # This test protects the business rule described by “owner can create worker account”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_can_create_worker_account(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("management:management_user_create_worker"),
            {
                "username": "new-worker",
                "first_name": "New",
                "last_name": "Worker",
                "email": "new-worker@example.test",
                "phone": "+30 690 000 0000",
                "password1": "Worker-account-test-2026!",
                "password2": "Worker-account-test-2026!",
            },
        )

        worker = User.objects.get(username="new-worker")
        self.assertRedirects(
            response,
            reverse("management:management_user_detail", args=[worker.pk]),
        )
        worker = User.objects.get(username="new-worker")
        self.assertTrue(worker.groups.filter(name="Workers").exists())
        self.assertTrue(worker.worker_profile.is_active_worker)
        self.assertFalse(worker.is_staff)
        self.assertFalse(worker.is_superuser)

    # This test protects the business rule described by “owner list hides all owner accounts”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_list_hides_all_owner_accounts(self):
        customer = User.objects.create_user(
            "visible-customer",
            password="Customer-test-pass-123!",
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("management:management_user_list")
        )

        self.assertContains(response, customer.username)
        self.assertContains(response, self.owner.username)
        self.assertNotContains(response, self.other_owner.username)

    # This test protects the business rule described by “owner cannot change another owner through
    # permission url”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_cannot_change_another_owner_through_permission_url(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "management:management_user_action",
                args=[self.other_owner.pk, "promote"],
            ),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 404)

    # This test protects the business rule described by “worker schedule contains only the signed
    # in worker assignments”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_worker_schedule_contains_only_the_signed_in_worker_assignments(self):
        worker_one_user = User.objects.create_user(
            "schedule-worker-one",
            password="Worker-test-pass-123!",
        )
        worker_two_user = User.objects.create_user(
            "schedule-worker-two",
            password="Worker-test-pass-456!",
        )
        Group.objects.get(name="Workers").user_set.add(
            worker_one_user,
            worker_two_user,
        )
        worker_one = WorkerProfile.objects.create(
            user=worker_one_user,
            display_name="Schedule Worker One",
        )
        worker_two = WorkerProfile.objects.create(
            user=worker_two_user,
            display_name="Schedule Worker Two",
        )
        package = PartyPackage.objects.get(slug="basic-popadoo-party")
        tier = GuestPriceTier.objects.filter(package=package).first()

        # This function handles booking as part of this module’s workflow.
        # It keeps the repeated decision in one place so callers receive the same result and
        # controlled failure behaviour.
        def booking(name):
            return PartyBuild.objects.create(
                package=package,
                guest_tier=tier,
                contact_name=name,
                contact_email=f"{name.lower().replace(' ', '-')}@example.test",
                contact_phone="+306900000000",
                event_date=timezone.localdate() + timedelta(days=7),
                event_time=timezone.datetime.strptime("16:00", "%H:%M").time(),
                event_address="Athens",
                postal_code="10558",
                guest_count=8,
                guest_tier_label=tier.label,
                package_price=Decimal("180.00"),
                addon_price=Decimal("0.00"),
                total_price=Decimal("180.00"),
            )

        PartyAssignment.objects.create(
            party_build=booking("Own Client"),
            worker=worker_one,
            status=PartyAssignment.Status.ACCEPTED,
        )
        PartyAssignment.objects.create(
            party_build=booking("Other Client"),
            worker=worker_two,
            status=PartyAssignment.Status.ACCEPTED,
        )

        self.client.force_login(worker_one_user)
        response = self.client.get(
            reverse("operations:operations_worker_schedule")
        )
        self.assertContains(response, "Own Client")
        self.assertNotContains(response, "Other Client")


# This group of tests protects the new party-completion workflow shared by full managers and the
# worker who delivered the accepted assignment. The scenarios prove that completion unlocks the
# existing customer review journey without granting workers any broader booking-control powers.
class PartyCompletionWorkflowTests(TestCase):
    # This setup creates separate customer, manager, and worker accounts so each permission boundary
    # can be tested against realistic booking and assignment records.
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            "completion-customer",
            password="Customer-pass-123!",
        )
        cls.owner = User.objects.create_user(
            "completion-owner",
            password="Owner-pass-123!",
        )
        cls.administrator = User.objects.create_superuser(
            "completion-admin",
            "completion-admin@example.test",
            "Admin-pass-123!",
        )
        cls.worker_user = User.objects.create_user(
            "completion-worker",
            password="Worker-pass-123!",
        )
        cls.other_worker_user = User.objects.create_user(
            "completion-other-worker",
            password="Worker-pass-456!",
        )
        Group.objects.get(name="Owners").user_set.add(cls.owner)
        Group.objects.get(name="Workers").user_set.add(
            cls.worker_user,
            cls.other_worker_user,
        )
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user,
            display_name="Completion Worker",
        )
        cls.other_worker = WorkerProfile.objects.create(
            user=cls.other_worker_user,
            display_name="Other Completion Worker",
        )
        cls.package = PartyPackage.objects.get(slug="basic-popadoo-party")
        cls.tier = GuestPriceTier.objects.filter(package=cls.package).first()

    # This helper creates a booking at a chosen stage while keeping the customer, price snapshot,
    # and review code realistic enough for both operations and customer-dashboard checks.
    def make_booking(
        self,
        *,
        status=PartyBuild.Status.CONFIRMED,
        event_date=None,
        customer=None,
    ):
        return PartyBuild.objects.create(
            customer=customer if customer is not None else self.customer,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Completion Parent",
            contact_email="completion-parent@example.test",
            contact_phone="+306900000000",
            event_date=event_date or timezone.localdate(),
            event_time=timezone.datetime.strptime("16:00", "%H:%M").time(),
            event_address="Athens",
            postal_code="10558",
            guest_count=8,
            guest_tier_label=self.tier.label,
            package_price=Decimal("180.00"),
            addon_price=Decimal("0.00"),
            total_price=Decimal("180.00"),
            status=status,
            assignment_state=PartyBuild.AssignmentState.ASSIGNED,
        )

    # This helper records the worker relationship that authorises completion. Different assignment
    # states let the tests prove that merely appearing in assignment history is not enough.
    def make_assignment(self, booking, *, worker=None, status=PartyAssignment.Status.ACCEPTED):
        return PartyAssignment.objects.create(
            party_build=booking,
            worker=worker or self.worker,
            status=status,
            assignment_source=PartyAssignment.Source.OWNER_MANUAL,
            assigned_by=self.owner,
        )

    # This test confirms both full-management roles can complete an eligible party and that the
    # existing audit history records management as the source of the decision.
    def test_owner_and_administrator_can_complete_eligible_party(self):
        for actor in (self.owner, self.administrator):
            with self.subTest(actor=actor.username):
                booking = self.make_booking()
                completed = mark_booking_completed(booking=booking, actor=actor)
                completed.refresh_from_db()
                self.assertEqual(completed.status, PartyBuild.Status.COMPLETED)
                self.assertIsNotNone(completed.completed_at)
                event = AuditEvent.objects.get(
                    event_type="booking_status_changed",
                    object_id=str(completed.pk),
                )
                self.assertEqual(event.actor, actor)
                self.assertEqual(event.after_data["completion_source"], "management")

    # This test follows the complete worker-to-customer journey: the accepted worker confirms
    # delivery, then the customer sees the existing rating action and can verify the same review code.
    def test_accepted_worker_completion_unlocks_customer_review(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        self.client.force_login(self.worker_user)
        response = self.client.post(
            reverse(
                "operations:operations_worker_assignment_complete",
                args=[assignment.pk],
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "operations:operations_worker_assignment_detail",
                args=[assignment.pk],
            ),
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.COMPLETED)
        self.assertIsNotNone(booking.completed_at)

        self.client.force_login(self.customer)
        dashboard = self.client.get(reverse("accounts:accounts_customer_dashboard"))
        self.assertContains(dashboard, "Rate this party")
        self.assertContains(dashboard, booking.review_code)
        self.assertEqual(
            verify_review_code(
                user=self.customer,
                submitted_code=booking.review_code,
            ),
            booking,
        )

    # This test proves that a worker assignment must be accepted at the moment of completion;
    # pending, declined, superseded, and cancelled history entries remain non-authorising records.
    def test_nonaccepted_assignment_states_cannot_complete_party(self):
        for status in (
            PartyAssignment.Status.PENDING,
            PartyAssignment.Status.DECLINED,
            PartyAssignment.Status.SUPERSEDED,
            PartyAssignment.Status.CANCELLED,
        ):
            with self.subTest(status=status):
                booking = self.make_booking()
                assignment = self.make_assignment(booking, status=status)
                with self.assertRaises(ValidationError):
                    mark_booking_completed(
                        booking=booking,
                        actor=self.worker_user,
                        assignment=assignment,
                    )
                booking.refresh_from_db()
                self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)

    # This test protects assignment ownership at the URL boundary. Another worker receives no
    # record at all, even when they know the assignment number.
    def test_other_worker_cannot_complete_assignment_by_url(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        self.client.force_login(self.other_worker_user)
        response = self.client.post(
            reverse(
                "operations:operations_worker_assignment_complete",
                args=[assignment.pk],
            )
        )
        self.assertEqual(response.status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)

    # This test confirms an inactive worker loses operational authority immediately, even when an
    # accepted assignment remains in history.
    def test_inactive_assigned_worker_cannot_complete_party(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        self.worker.is_active_worker = False
        self.worker.save(update_fields=["is_active_worker", "updated_at"])
        self.client.force_login(self.worker_user)
        response = self.client.post(
            reverse(
                "operations:operations_worker_assignment_complete",
                args=[assignment.pk],
            )
        )
        self.assertEqual(response.status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)

    # This test keeps the completion endpoint unavailable to customers and signed-out visitors,
    # while preserving the project’s existing deny-or-login behavior for anonymous worker pages.
    def test_customer_and_anonymous_user_cannot_complete_party(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        url = reverse(
            "operations:operations_worker_assignment_complete",
            args=[assignment.pk],
        )

        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.assertIn(self.client.post(url).status_code, (302, 403))
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)

    # This test ensures the state-changing endpoint cannot be triggered by opening a link or
    # preloading a page; only a CSRF-protected POST form may request completion.
    def test_worker_completion_endpoint_rejects_get(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        self.client.force_login(self.worker_user)
        response = self.client.get(
            reverse(
                "operations:operations_worker_assignment_complete",
                args=[assignment.pk],
            )
        )
        self.assertEqual(response.status_code, 405)
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)

    # This test proves the server ignores any status or timestamp invented by the browser and
    # always applies the single trusted completion result.
    def test_worker_cannot_submit_arbitrary_status_or_completion_time(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        self.client.force_login(self.worker_user)
        response = self.client.post(
            reverse(
                "operations:operations_worker_assignment_complete",
                args=[assignment.pk],
            ),
            {
                "status": PartyBuild.Status.CANCELLED,
                "completed_at": "2000-01-01T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.COMPLETED)
        self.assertGreater(booking.completed_at, timezone.now() - timedelta(minutes=1))

    # This test preserves the real checkout workflow, where an accepted worker assignment may exist
    # while the booking still says submitted or contacted. Once the party date has arrived, either
    # earlier label may be completed; future and cancelled parties remain protected.
    def test_past_submitted_and_contacted_bookings_can_be_completed(self):
        for status in (PartyBuild.Status.SUBMITTED, PartyBuild.Status.CONTACTED):
            with self.subTest(status=status):
                booking = self.make_booking(status=status)
                assignment = self.make_assignment(booking)
                completed = mark_booking_completed(
                    booking=booking,
                    actor=self.worker_user,
                    assignment=assignment,
                )
                completed.refresh_from_db()
                self.assertEqual(completed.status, PartyBuild.Status.COMPLETED)
                self.assertIsNotNone(completed.completed_at)

    # This test keeps future and cancelled parties outside the completion workflow even when an
    # accepted assignment exists, so customer review access cannot open before delivery or after a
    # cancellation.
    def test_future_and_cancelled_bookings_cannot_be_completed(self):
        cases = (
            (
                PartyBuild.Status.SUBMITTED,
                timezone.localdate() + timedelta(days=1),
            ),
            (PartyBuild.Status.CANCELLED, timezone.localdate()),
        )
        for status, event_date in cases:
            with self.subTest(status=status, event_date=event_date):
                booking = self.make_booking(status=status, event_date=event_date)
                assignment = self.make_assignment(booking)
                with self.assertRaises(ValidationError):
                    mark_booking_completed(
                        booking=booking,
                        actor=self.worker_user,
                        assignment=assignment,
                    )
                booking.refresh_from_db()
                self.assertEqual(booking.status, status)
                self.assertIsNone(booking.completed_at)

    # This test ensures a repeated request cannot replace the original completion time or create a
    # second successful history entry after the booking has already become final.
    def test_repeated_completion_preserves_timestamp_and_single_audit_event(self):
        booking = self.make_booking()
        completed = mark_booking_completed(booking=booking, actor=self.owner)
        original_completed_at = completed.completed_at
        with self.assertRaises(ValidationError):
            mark_booking_completed(booking=booking, actor=self.owner)
        booking.refresh_from_db()
        self.assertEqual(booking.completed_at, original_completed_at)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="booking_status_changed",
                object_id=str(booking.pk),
            ).count(),
            1,
        )

    # This test confirms the audit event records accountability without copying customer contact,
    # venue, review-code, or free-text information into management history.
    def test_completion_audit_contains_only_safe_operational_metadata(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        mark_booking_completed(
            booking=booking,
            actor=self.worker_user,
            assignment=assignment,
        )
        event = AuditEvent.objects.get(
            event_type="booking_status_changed",
            object_id=str(booking.pk),
        )
        self.assertEqual(event.after_data["completion_source"], "assigned_worker")
        self.assertEqual(event.after_data["assignment_id"], assignment.pk)
        combined = f"{event.summary} {event.before_data} {event.after_data}"
        for private_value in (
            booking.notes,
            booking.review_code,
            booking.event_address,
            booking.contact_phone,
            booking.contact_email,
        ):
            if private_value:
                self.assertNotIn(private_value, combined)

    # This test confirms the worker page shows the completion button only for an accepted assignment
    # whose party date has arrived, including the submitted state used by real checkout records,
    # rather than relying on the template to decide access.
    def test_worker_detail_shows_completion_action_only_when_eligible(self):
        eligible_booking = self.make_booking(status=PartyBuild.Status.SUBMITTED)
        eligible_assignment = self.make_assignment(eligible_booking)
        future_booking = self.make_booking(
            event_date=timezone.localdate() + timedelta(days=1)
        )
        future_assignment = self.make_assignment(future_booking)
        pending_booking = self.make_booking()
        pending_assignment = self.make_assignment(
            pending_booking,
            status=PartyAssignment.Status.PENDING,
        )
        self.client.force_login(self.worker_user)

        eligible_response = self.client.get(
            reverse(
                "operations:operations_worker_assignment_detail",
                args=[eligible_assignment.pk],
            )
        )
        self.assertContains(eligible_response, "Mark party as done")

        for assignment in (future_assignment, pending_assignment):
            with self.subTest(assignment=assignment.pk):
                response = self.client.get(
                    reverse(
                        "operations:operations_worker_assignment_detail",
                        args=[assignment.pk],
                    )
                )
                self.assertNotContains(response, ">Mark party as done<")

    # This test confirms the worker page replaces the active action with the final timestamp and an
    # explanation that the customer’s existing review access has been enabled.
    def test_worker_detail_shows_completed_state(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking)
        mark_booking_completed(
            booking=booking,
            actor=self.worker_user,
            assignment=assignment,
        )
        self.client.force_login(self.worker_user)
        response = self.client.get(
            reverse(
                "operations:operations_worker_assignment_detail",
                args=[assignment.pk],
            )
        )
        self.assertContains(response, "Party completed")
        self.assertContains(response, "Customer review access is now available")
        self.assertNotContains(response, ">Mark party as done<")

    # This test calls the service with an assignment owned by somebody else to prove the business
    # layer remains secure even outside the already restricted worker view.
    def test_service_rejects_worker_assignment_owned_by_somebody_else(self):
        booking = self.make_booking()
        assignment = self.make_assignment(booking, worker=self.other_worker)
        with self.assertRaises(PermissionDenied):
            mark_booking_completed(
                booking=booking,
                actor=self.worker_user,
                assignment=assignment,
            )
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)
