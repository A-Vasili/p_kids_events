# This file protects worker tasks and the custom management area used by Owners and Administrators
# with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import WorkerProfile
from party_builder.models import (
    AddonExperience,
    Category,
    GuestPriceTier,
    PartyBuild,
    PartyBuildAddon,
    PartyPackage,
)

from .models import AuditEvent, PartyAssignment
from .services.assignment import assign_manually
from .services.bookings import send_to_manual_review
from .services.catalogue import remove_tier

User = get_user_model()


# This group of tests protects the management panel tests behaviour as one related customer or
# staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ManagementPanelTests(TestCase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.administrator = User.objects.create_superuser(
            "management-admin", "admin@popadoo.test", "Admin-pass-123!"
        )
        cls.owner = User.objects.create_user("management-owner", password="Owner-pass-123!")
        Group.objects.get(name="Owners").user_set.add(cls.owner)
        cls.customer = User.objects.create_user("management-customer", password="Customer-pass-123!")
        cls.worker_user = User.objects.create_user("management-worker", password="Worker-pass-123!")
        Group.objects.get(name="Workers").user_set.add(cls.worker_user)
        cls.worker = WorkerProfile.objects.create(user=cls.worker_user, display_name="Management Worker")
        cls.pricing_user = User.objects.create_user("pricing-worker", password="Pricing-pass-123!")
        Group.objects.get(name="Workers").user_set.add(cls.pricing_user)
        Group.objects.get(name="Pricing Managers").user_set.add(cls.pricing_user)
        cls.pricing_profile = WorkerProfile.objects.create(user=cls.pricing_user, display_name="Pricing Worker")
        cls.package = PartyPackage.objects.get(slug="basic-popadoo-party")
        cls.tier = GuestPriceTier.objects.filter(package=cls.package).order_by("min_guests").first()

    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    def setUp(self):
        self.client.force_login(self.owner)

    # This method handles make booking for the surrounding management panel tests.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def make_booking(self, *, package=None, tier=None, name="Parent One"):
        package = package or self.package
        tier = tier or GuestPriceTier.objects.filter(package=package).first()
        return PartyBuild.objects.create(
            package=package,
            guest_tier=tier,
            contact_name=name,
            contact_email="parent@example.test",
            contact_phone="+306900000000",
            event_date=timezone.localdate() + timedelta(days=7),
            event_time=timezone.datetime.strptime("16:00", "%H:%M").time(),
            event_address="Athens",
            postal_code="10558",
            guest_count=8,
            guest_tier_label=tier.label if tier else "Custom",
            package_price=Decimal("180.00"),
            addon_price=Decimal("0.00"),
            total_price=Decimal("180.00"),
        )

    # This test protects the business rule described by “admin route is unavailable”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_admin_route_is_unavailable(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 404)

    # This test protects the business rule described by “management access is role protected”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_management_access_is_role_protected(self):
        self.client.logout()
        response = self.client.get(reverse("management:management_dashboard"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("management:management_dashboard")).status_code, 403)

        self.client.force_login(self.worker_user)
        self.assertEqual(self.client.get(reverse("management:management_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("management:management_package_list")).status_code, 403)

        self.client.force_login(self.pricing_user)
        self.assertEqual(self.client.get(reverse("management:management_catalogue")).status_code, 200)
        self.assertEqual(self.client.get(reverse("management:management_dashboard")).status_code, 403)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("management:management_dashboard")).status_code, 200)

        self.client.force_login(self.administrator)
        self.assertEqual(self.client.get(reverse("management:management_dashboard")).status_code, 200)

    # This test protects the business rule described by “active catalogue details link to public
    # party ideas”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_active_catalogue_details_link_to_public_party_ideas(self):
        package_response = self.client.get(
            reverse("management:management_package_detail", args=[self.package.pk])
        )
        category_response = self.client.get(
            reverse(
                "management:management_category_detail",
                args=[self.package.category_id],
            )
        )
        addon = AddonExperience.objects.filter(is_active=True).first()
        addon_response = self.client.get(
            reverse("management:management_addon_detail", args=[addon.pk])
        )

        self.assertContains(
            package_response,
            reverse("party_ideas:package_detail", args=[self.package.slug]),
        )
        self.assertContains(
            category_response,
            reverse(
                "party_ideas:category_detail", args=[self.package.category.slug]
            ),
        )
        self.assertContains(
            addon_response,
            reverse("party_ideas:addon_detail", args=[addon.slug]),
        )

    # This test protects the business rule described by “owner can create category and
    # subcategory”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_can_create_category_and_subcategory(self):
        response = self.client.post(
            reverse("management:management_category_create"),
            {
                "name": "Management Creative Activities",
                "slug": "management-creative-activities",
                "description": "Hands-on activities.",
                "display_order": 30,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("management:management_category_list"))
        parent = Category.objects.get(slug="management-creative-activities")

        response = self.client.post(
            reverse("management:management_category_create"),
            {
                "name": "Craft Workshops",
                "slug": "craft-workshops",
                "description": "Craft subcategory.",
                "parent": parent.pk,
                "display_order": 10,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("management:management_category_list"))
        self.assertEqual(Category.objects.get(slug="craft-workshops").parent, parent)
        self.assertTrue(AuditEvent.objects.filter(event_type="category_created").exists())

    # This test protects the business rule described by “category circular parent is rejected”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_category_circular_parent_is_rejected(self):
        parent = Category.objects.create(name="Parent", slug="parent")
        child = Category.objects.create(name="Child", slug="child", parent=parent)
        response = self.client.post(
            reverse("management:management_category_update", args=[parent.pk]),
            {
                "name": "Parent",
                "slug": "parent",
                "parent": child.pk,
                "display_order": 0,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be placed underneath", status_code=200)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent)

    # This test protects the business rule described by “unused category is deleted and used
    # category is archived”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_unused_category_is_deleted_and_used_category_is_archived(self):
        unused = Category.objects.create(name="Unused", slug="unused")
        response = self.client.post(
            reverse("management:management_category_remove", args=[unused.pk]),
            {"confirmation": "on"},
        )
        self.assertRedirects(response, reverse("management:management_category_list"))
        self.assertFalse(Category.objects.filter(pk=unused.pk).exists())

        used = self.package.category
        self.assertIsNotNone(used)
        response = self.client.post(
            reverse("management:management_category_remove", args=[used.pk]),
            {"confirmation": "on"},
        )
        self.assertRedirects(response, reverse("management:management_category_list"))
        used.refresh_from_db()
        self.assertFalse(used.is_active)

    # This test protects the business rule described by “package crud and default switch”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_package_crud_and_default_switch(self):
        response = self.client.post(
            reverse("management:management_package_create"),
            {
                "name": "Premium Party",
                "slug": "premium-party",
                "category": self.package.category_id,
                "short_description": "A premium package.",
                "base_price": "260.00",
                "duration_minutes": 150,
                "included_guest_count": 10,
                "included_experiences": "Host\nGames",
                "is_default": "on",
                "is_active": "on",
                "display_order": 20,
            },
        )
        self.assertRedirects(response, reverse("management:management_package_list"))
        premium = PartyPackage.objects.get(slug="premium-party")
        self.package.refresh_from_db()
        self.assertTrue(premium.is_default)
        self.assertFalse(self.package.is_default)

        response = self.client.post(
            reverse("management:management_package_update", args=[premium.pk]),
            {
                "name": "Premium Party Plus",
                "slug": "premium-party",
                "category": self.package.category_id,
                "short_description": "Updated package.",
                "base_price": "280.00",
                "duration_minutes": 165,
                "included_guest_count": 12,
                "included_experiences": "Host\nGames\nCraft",
                "is_default": "on",
                "is_active": "on",
                "display_order": 20,
            },
        )
        self.assertRedirects(response, reverse("management:management_package_list"))
        premium.refresh_from_db()
        self.assertEqual(premium.name, "Premium Party Plus")
        self.assertEqual(premium.base_price, Decimal("280.00"))

    # This test protects the business rule described by “referenced package is archived”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_referenced_package_is_archived(self):
        replacement = PartyPackage.objects.create(
            name="Replacement",
            slug="replacement",
            category=self.package.category,
            short_description="Replacement",
            base_price=Decimal("200.00"),
            duration_minutes=120,
            included_guest_count=10,
            included_experiences="Host",
            is_active=True,
            is_default=False,
        )
        GuestPriceTier.objects.create(
            package=replacement,
            label="1-10",
            min_guests=1,
            max_guests=10,
            total_price=Decimal("200.00"),
            is_active=True,
            is_default=True,
        )
        self.make_booking()
        response = self.client.post(
            reverse("management:management_package_remove", args=[self.package.pk]),
            {"confirmation": "on"},
        )
        self.assertRedirects(response, reverse("management:management_package_list"))
        self.package.refresh_from_db()
        replacement.refresh_from_db()
        self.assertFalse(self.package.is_active)
        self.assertTrue(replacement.is_default)

    # This test protects the business rule described by “package management uses capacity and
    # hides tier crud”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_package_management_uses_capacity_and_hides_tier_crud(self):
        catalogue = self.client.get(
            reverse("management:management_catalogue")
        )
        package_detail = self.client.get(
            reverse(
                "management:management_package_detail",
                args=[self.package.pk],
            )
        )

        self.assertContains(catalogue, "Capacity-based packages")
        self.assertNotContains(catalogue, "Guest-price tiers")
        self.assertContains(package_detail, "Fixed package price")
        self.assertContains(package_detail, "Package capacity")
        self.assertNotContains(package_detail, "Add tier")
        self.assertNotContains(package_detail, "Edit tier")

    # This test protects the business rule described by “legacy tier management urls are read only
    # redirects”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_legacy_tier_management_urls_are_read_only_redirects(self):
        original_count = GuestPriceTier.objects.count()
        list_response = self.client.get(
            reverse("management:management_tier_list")
        )
        create_response = self.client.post(
            reverse("management:management_tier_create"),
            {
                "package": self.package.pk,
                "label": "New tier should not be created",
                "min_guests": 41,
                "max_guests": 45,
                "total_price": "630.00",
                "is_active": "on",
            },
        )
        package_create_response = self.client.get(
            reverse(
                "management:management_package_tier_create",
                args=[self.package.pk],
            )
        )
        update_response = self.client.get(
            reverse("management:management_tier_update", args=[self.tier.pk])
        )

        self.assertRedirects(
            list_response,
            reverse("management:management_catalogue"),
        )
        self.assertRedirects(
            create_response,
            reverse("management:management_catalogue"),
        )
        package_detail = reverse(
            "management:management_package_detail",
            args=[self.package.pk],
        )
        self.assertRedirects(package_create_response, package_detail)
        self.assertRedirects(update_response, package_detail)
        self.assertEqual(GuestPriceTier.objects.count(), original_count)
        self.assertFalse(
            GuestPriceTier.objects.filter(
                label="New tier should not be created"
            ).exists()
        )

    # This test protects the business rule described by “referenced addon is archived”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_referenced_addon_is_archived(self):
        addon = AddonExperience.objects.first()
        build = self.make_booking()
        PartyBuildAddon.objects.create(build=build, addon=addon, unit_price=addon.price)
        response = self.client.post(
            reverse("management:management_addon_remove", args=[addon.pk]),
            {"confirmation": "on"},
        )
        self.assertRedirects(response, reverse("management:management_addon_list"))
        addon.refresh_from_db()
        self.assertFalse(addon.is_active)
        self.assertTrue(build.addon_items.filter(addon=addon).exists())

    # This test protects the business rule described by “fake image upload is rejected”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_fake_image_upload_is_rejected(self):
        fake = SimpleUploadedFile("fake.png", b"not a real image", content_type="image/png")
        response = self.client.post(
            reverse("management:management_category_create"),
            {
                "name": "Image Category",
                "slug": "image-category",
                "description": "Image test",
                "display_order": 1,
                "is_active": "on",
                "image": fake,
                "image_alt_text": "Decorative party table",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image")
        self.assertFalse(Category.objects.filter(slug="image-category").exists())

    # This test protects the business rule described by “owner can ban customer but not view other
    # owner or administrator”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_can_ban_customer_but_not_view_other_owner_or_administrator(self):
        other_owner = User.objects.create_user("other-management-owner", password="Owner-pass-456!")
        Group.objects.get(name="Owners").user_set.add(other_owner)

        self.assertEqual(
            self.client.get(reverse("management:management_user_detail", args=[other_owner.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("management:management_user_detail", args=[self.administrator.pk])).status_code,
            404,
        )

        response = self.client.post(
            reverse("management:management_user_action", args=[self.customer.pk, "ban"]),
            {"confirmation": "on"},
        )
        self.assertRedirects(response, reverse("management:management_user_detail", args=[self.customer.pk]))
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertTrue(AuditEvent.objects.filter(event_type="user_banned", object_id=str(self.customer.pk)).exists())

    # This test protects the business rule described by “booking filter detail and status update”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_booking_filter_detail_and_status_update(self):
        booking = self.make_booking(name="Searchable Parent")
        response = self.client.get(reverse("management:management_booking_list"), {"q": "Searchable"})
        self.assertContains(response, "Searchable Parent")
        self.assertEqual(
            self.client.get(reverse("management:management_booking_detail", args=[booking.public_id])).status_code,
            200,
        )
        response = self.client.post(
            reverse("management:management_booking_status", args=[booking.public_id]),
            {"status": PartyBuild.Status.CONTACTED, "note": "Client called."},
        )
        self.assertRedirects(response, reverse("management:management_booking_detail", args=[booking.public_id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONTACTED)
        self.assertTrue(AuditEvent.objects.filter(event_type="booking_status_changed", object_id=str(booking.pk)).exists())

    # This test protects the business rule described by “mutation endpoints reject get”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_mutation_endpoints_reject_get(self):
        booking = self.make_booking()
        self.assertEqual(
            self.client.get(reverse("management:management_booking_status", args=[booking.public_id])).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(reverse("management:management_booking_manual_review", args=[booking.public_id])).status_code,
            405,
        )

    # This test protects the business rule described by “dashboard totals can exceed recent list
    # limit”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_dashboard_totals_can_exceed_recent_list_limit(self):
        category = self.package.category
        for index in range(12):
            PartyPackage.objects.create(
                name=f"Count Package {index}",
                slug=f"count-package-{index}",
                category=category,
                short_description="Count test",
                base_price=Decimal("180.00"),
                duration_minutes=120,
                included_guest_count=10,
                included_experiences="Host",
                is_active=True,
            )
        response = self.client.get(reverse("management:management_dashboard"))
        self.assertGreaterEqual(response.context["stats"]["active_packages"], 13)
        self.assertLessEqual(len(response.context["attention_bookings"]), 8)

    # This test protects the business rule described by “audit page is owner only and paginated”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_audit_page_is_owner_only_and_paginated(self):
        for index in range(55):
            AuditEvent.objects.create(
                actor=self.owner,
                event_type="test_event",
                object_type="Test",
                object_id=str(index),
                summary=f"Event {index}",
            )
        response = self.client.get(reverse("management:management_audit"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["events"]), 50)
        self.client.force_login(self.worker_user)
        self.assertEqual(self.client.get(reverse("management:management_audit")).status_code, 403)


    # This test protects the business rule described by “valid image upload uses generated
    # catalogue path”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_valid_image_upload_uses_generated_catalogue_path(self):
        image_bytes = BytesIO()
        Image.new("RGB", (12, 12), color=(240, 80, 140)).save(image_bytes, format="PNG")
        image_bytes.seek(0)
        upload = SimpleUploadedFile(
            "parent-controlled-name.png",
            image_bytes.read(),
            content_type="image/png",
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("management:management_category_create"),
                {
                    "name": "Photo Category",
                    "slug": "photo-category",
                    "description": "A category with a validated image.",
                    "display_order": 4,
                    "is_active": "on",
                    "image": upload,
                    "image_alt_text": "Pink party decoration",
                },
            )
            self.assertRedirects(response, reverse("management:management_category_list"))
            category = Category.objects.get(slug="photo-category")
            self.assertTrue(category.image.name.startswith("catalogue/categories/"))
            self.assertNotIn("parent-controlled-name", category.image.name)
            self.assertTrue(category.image.storage.exists(category.image.name))

    # This test protects the business rule described by “unused catalogue records are permanently
    # deleted”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_unused_catalogue_records_are_permanently_deleted(self):
        package = PartyPackage.objects.create(
            name="Temporary Package",
            slug="temporary-package",
            category=self.package.category,
            short_description="Not used by any booking.",
            base_price=Decimal("150.00"),
            duration_minutes=90,
            included_guest_count=8,
            included_experiences="Host",
            is_active=True,
            is_default=False,
        )
        tier = GuestPriceTier.objects.create(
            package=package,
            label="1–8 children",
            min_guests=1,
            max_guests=8,
            total_price=Decimal("150.00"),
            is_active=True,
            is_default=True,
        )
        addon = AddonExperience.objects.create(
            name="Temporary Add-on",
            slug="temporary-addon",
            category=AddonExperience.objects.first().category,
            short_description="Not used by any booking.",
            price=Decimal("20.00"),
            duration_minutes=0,
            is_active=True,
        )

        self.client.post(
            reverse("management:management_addon_remove", args=[addon.pk]),
            {"confirmation": "on"},
        )
        self.assertFalse(AddonExperience.objects.filter(pk=addon.pk).exists())

        self.client.post(
            reverse("management:management_package_remove", args=[package.pk]),
            {"confirmation": "on"},
        )
        self.assertFalse(PartyPackage.objects.filter(pk=package.pk).exists())
        self.assertFalse(GuestPriceTier.objects.filter(pk=tier.pk).exists())

    # This test protects the business rule described by “legacy tier service archives without
    # losing booking”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_legacy_tier_service_archives_without_losing_booking(self):
        tier = GuestPriceTier.objects.create(
            package=self.package,
            label="Archive test 41–45",
            min_guests=41,
            max_guests=45,
            total_price=Decimal("630.00"),
            is_active=True,
            is_default=False,
        )
        booking = self.make_booking(tier=tier)

        result = remove_tier(tier, actor=self.owner)

        tier.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(result.action, "archived")
        self.assertFalse(tier.is_active)
        self.assertEqual(booking.guest_tier_id, tier.pk)

    # This test protects the business rule described by “last default package cannot be removed”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_last_default_package_cannot_be_removed(self):
        PartyPackage.objects.exclude(pk=self.package.pk).update(
            is_active=False,
            is_default=False,
        )
        PartyPackage.objects.filter(pk=self.package.pk).update(
            is_active=True,
            is_default=True,
        )
        response = self.client.post(
            reverse("management:management_package_remove", args=[self.package.pk]),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create or activate another package")
        self.assertTrue(PartyPackage.objects.filter(pk=self.package.pk).exists())
        self.package.refresh_from_db()
        self.assertTrue(self.package.is_default)

    # This test protects the business rule described by “invalid catalogue form preserves values
    # and field errors”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_invalid_catalogue_form_preserves_values_and_field_errors(self):
        response = self.client.post(
            reverse("management:management_package_create"),
            {
                "name": "Preserved Invalid Package",
                "slug": "preserved-invalid-package",
                "category": self.package.category_id,
                "short_description": "This value should remain visible.",
                "base_price": "-1.00",
                "duration_minutes": 120,
                "included_guest_count": 10,
                "included_experiences": "Host",
                "is_active": "on",
                "display_order": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preserved Invalid Package")
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, "greater than or equal to")
        self.assertFalse(PartyPackage.objects.filter(slug="preserved-invalid-package").exists())

    # This test protects the business rule described by “owner can create worker through
    # management namespace”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_owner_can_create_worker_through_management_namespace(self):
        response = self.client.post(
            reverse("management:management_user_create_worker"),
            {
                "username": "new-management-worker",
                "first_name": "New",
                "last_name": "Worker",
                "email": "new-management-worker@example.test",
                "phone": "+306900001111",
                "password1": "Strong-worker-pass-2026!",
                "password2": "Strong-worker-pass-2026!",
            },
        )
        worker_user = User.objects.get(username="new-management-worker")
        self.assertRedirects(
            response,
            reverse("management:management_user_detail", args=[worker_user.pk]),
        )
        self.assertTrue(worker_user.groups.filter(name="Workers").exists())
        self.assertTrue(worker_user.worker_profile.is_active_worker)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="worker_promoted",
                object_id=str(worker_user.pk),
            ).exists()
        )

    # This test protects the business rule described by “crafted user action must match current
    # role state”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_crafted_user_action_must_match_current_role_state(self):
        response = self.client.post(
            reverse(
                "management:management_user_action",
                args=[self.customer.pk, "demote"],
            ),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.customer.groups.filter(name="Workers").exists())

    # This test protects the business rule described by “state changing management actions require
    # csrf”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_state_changing_management_actions_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(
            reverse(
                "management:management_user_action",
                args=[self.customer.pk, "ban"],
            ),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 403)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    # This test protects the business rule described by “price and default changes have filterable
    # audit events”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_price_and_default_changes_have_filterable_audit_events(self):
        response = self.client.post(
            reverse("management:management_package_update", args=[self.package.pk]),
            {
                "name": self.package.name,
                "slug": self.package.slug,
                "category": self.package.category_id,
                "short_description": self.package.short_description,
                "base_price": "195.00",
                "duration_minutes": self.package.duration_minutes,
                "included_guest_count": self.package.included_guest_count,
                "included_experiences": self.package.included_experiences,
                "is_default": "on",
                "is_active": "on",
                "display_order": self.package.display_order,
            },
        )
        self.assertRedirects(response, reverse("management:management_package_list"))
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="catalogue_price_changed",
                object_id=str(self.package.pk),
            ).exists()
        )


    # This test protects the business rule described by “manual reassignment replaces confirmed
    # schedule entry”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_manual_reassignment_replaces_confirmed_schedule_entry(self):
        second_user = User.objects.create_user(
            "second-management-worker",
            password="Second-worker-pass-123!",
        )
        Group.objects.get(name="Workers").user_set.add(second_user)
        second_worker = WorkerProfile.objects.create(
            user=second_user,
            display_name="Second Management Worker",
        )
        booking = self.make_booking()
        previous = PartyAssignment.objects.create(
            party_build=booking,
            worker=self.worker,
            status=PartyAssignment.Status.ACCEPTED,
            assignment_source=PartyAssignment.Source.OWNER_MANUAL,
            assigned_by=self.owner,
        )
        booking.assignment_state = PartyBuild.AssignmentState.ASSIGNED
        booking.save(update_fields=["assignment_state"])

        response = self.client.post(
            reverse("management:management_booking_assign", args=[booking.public_id]),
            {
                "worker": second_worker.pk,
                "already_agreed": "on",
                "override_reason": "The worker confirmed availability by phone.",
            },
        )
        self.assertRedirects(
            response,
            reverse("management:management_booking_detail", args=[booking.public_id]),
        )
        previous.refresh_from_db()
        booking.refresh_from_db()
        current = booking.assignments.get(status=PartyAssignment.Status.ACCEPTED)
        self.assertEqual(previous.status, PartyAssignment.Status.SUPERSEDED)
        self.assertEqual(current.worker, second_worker)
        self.assertEqual(booking.assignment_state, PartyBuild.AssignmentState.ASSIGNED)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="manual_assignment",
                object_id=str(current.pk),
            ).exists()
        )

    # This test protects the business rule described by “manual assignment service rejects non
    # owner”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_manual_assignment_service_rejects_non_owner(self):
        booking = self.make_booking()

        with self.assertRaises(PermissionDenied):
            assign_manually(
                party_build=booking,
                worker=self.worker,
                owner=self.customer,
                override_reason="Attempted outside the owner workflow.",
            )

        self.assertFalse(booking.assignments.exists())

    # This test protects the business rule described by “manual review removes confirmed schedule
    # entry”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_manual_review_removes_confirmed_schedule_entry(self):
        booking = self.make_booking()
        assignment = PartyAssignment.objects.create(
            party_build=booking,
            worker=self.worker,
            status=PartyAssignment.Status.ACCEPTED,
            assignment_source=PartyAssignment.Source.OWNER_MANUAL,
            assigned_by=self.owner,
        )
        booking.assignment_state = PartyBuild.AssignmentState.ASSIGNED
        booking.save(update_fields=["assignment_state"])

        response = self.client.post(
            reverse(
                "management:management_booking_manual_review",
                args=[booking.public_id],
            ),
            {"reason": "Client requested a different entertainer."},
        )
        self.assertRedirects(
            response,
            reverse("management:management_booking_detail", args=[booking.public_id]),
        )
        assignment.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(assignment.status, PartyAssignment.Status.SUPERSEDED)
        self.assertEqual(
            booking.assignment_state,
            PartyBuild.AssignmentState.MANUAL_REVIEW,
        )

    # This test protects the business rule described by “manual review service rejects non owner”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_manual_review_service_rejects_non_owner(self):
        booking = self.make_booking()

        with self.assertRaises(PermissionDenied):
            send_to_manual_review(
                booking=booking,
                actor=self.customer,
                reason="Attempted outside the owner workflow.",
            )

        booking.refresh_from_db()
        self.assertEqual(
            booking.assignment_state,
            PartyBuild.AssignmentState.UNASSIGNED,
        )

    # This test protects the business rule described by “terminal booking cannot return to manual
    # review”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_terminal_booking_cannot_return_to_manual_review(self):
        booking = self.make_booking()
        booking.status = PartyBuild.Status.CANCELLED
        booking.save(update_fields=["status"])

        response = self.client.post(
            reverse(
                "management:management_booking_manual_review",
                args=[booking.public_id],
            ),
            {"reason": "This should be rejected safely."},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Completed or cancelled bookings cannot be sent to manual review.",
        )
        booking.refresh_from_db()
        self.assertEqual(
            booking.assignment_state,
            PartyBuild.AssignmentState.UNASSIGNED,
        )

    # This test protects the business rule described by “administrator can create owner without
    # system privileges”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_administrator_can_create_owner_without_system_privileges(self):
        self.client.force_login(self.administrator)
        response = self.client.post(
            reverse("management:management_user_create_owner"),
            {
                "username": "new-business-owner",
                "first_name": "New",
                "last_name": "Owner",
                "email": "new-owner@popadoo.test",
                "password1": "Strong-owner-pass-2026!",
                "password2": "Strong-owner-pass-2026!",
            },
        )
        owner = User.objects.get(username="new-business-owner")
        self.assertRedirects(
            response,
            reverse("management:management_user_detail", args=[owner.pk]),
        )
        self.assertFalse(owner.is_superuser)
        self.assertFalse(owner.is_staff)
        self.assertTrue(owner.groups.filter(name="Owners").exists())
        self.assertFalse(owner.groups.filter(name="Workers").exists())
        self.assertFalse(owner.groups.filter(name="Pricing Managers").exists())
        self.assertFalse(hasattr(owner, "worker_profile"))
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="owner_created", object_id=str(owner.pk)
            ).exists()
        )

    # This test protects the business rule described by “only administrator can open owner
    # creation”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_only_administrator_can_open_owner_creation(self):
        url = reverse("management:management_user_create_owner")

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

        for user in (self.owner, self.worker_user, self.customer):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.administrator)
        self.assertEqual(self.client.get(url).status_code, 200)

    # This test protects the business rule described by “customer information is read only in
    # management”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_customer_information_is_read_only_in_management(self):
        detail_url = reverse(
            "management:management_user_detail", args=[self.customer.pk]
        )
        update_url = reverse(
            "management:management_user_update", args=[self.customer.pk]
        )
        response = self.client.get(detail_url)
        self.assertContains(response, "Customer information is read-only")
        self.assertNotContains(response, "Edit profile")
        self.assertNotContains(response, "Edit worker settings")
        self.assertEqual(self.client.get(update_url).status_code, 403)
        self.assertEqual(
            self.client.post(
                update_url,
                {
                    "display_name": "Not allowed",
                    "phone": "+306900009999",
                    "max_daily_parties": 3,
                    "notes_for_owner": "Not allowed",
                },
            ).status_code,
            403,
        )

    # This test protects the business rule described by “worker settings do not change customer
    # profile defaults”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_worker_settings_do_not_change_customer_profile_defaults(self):
        profile = self.worker_user.customer_profile
        profile.phone = "+306911111111"
        profile.default_address = "Customer-controlled address"
        profile.default_postal_code = "10558"
        profile.save()

        response = self.client.post(
            reverse(
                "management:management_user_update", args=[self.worker_user.pk]
            ),
            {
                "display_name": "Updated Worker",
                "phone": "+306922222222",
                "max_daily_parties": 4,
                "notes_for_owner": "Available for large venues.",
            },
        )
        self.assertRedirects(
            response,
            reverse(
                "management:management_user_detail", args=[self.worker_user.pk]
            ),
        )
        self.worker.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.worker.display_name, "Updated Worker")
        self.assertEqual(self.worker.phone, "+306922222222")
        self.assertEqual(profile.phone, "+306911111111")
        self.assertEqual(profile.default_address, "Customer-controlled address")
        self.assertEqual(profile.default_postal_code, "10558")

    # This test protects the business rule described by “customer can be banned and unbanned with
    # audit history”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_customer_can_be_banned_and_unbanned_with_audit_history(self):
        ban_url = reverse(
            "management:management_user_action", args=[self.customer.pk, "ban"]
        )
        unban_url = reverse(
            "management:management_user_action", args=[self.customer.pk, "unban"]
        )
        self.assertRedirects(
            self.client.post(ban_url, {"confirmation": "on"}),
            reverse("management:management_user_detail", args=[self.customer.pk]),
        )
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertFalse(
            self.client.login(
                username=self.customer.username, password="Customer-pass-123!"
            )
        )

        self.client.force_login(self.owner)
        self.assertRedirects(
            self.client.post(unban_url, {"confirmation": "on"}),
            reverse("management:management_user_detail", args=[self.customer.pk]),
        )
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="user_banned", object_id=str(self.customer.pk)
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="user_unbanned", object_id=str(self.customer.pk)
            ).exists()
        )

    # This test protects the business rule described by “unused customer can be deleted”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_unused_customer_can_be_deleted(self):
        unused = User.objects.create_user(
            "unused-customer",
            email="unused@example.test",
            password="Unused-customer-pass-2026!",
        )
        response = self.client.post(
            reverse(
                "management:management_user_action", args=[unused.pk, "delete"]
            ),
            {"confirmation": "on"},
        )
        self.assertRedirects(response, reverse("management:management_user_list"))
        self.assertFalse(User.objects.filter(pk=unused.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="unused_customer_deleted", object_id=str(unused.pk)
            ).exists()
        )

    # This test protects the business rule described by “customer with booking history cannot be
    # deleted”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_customer_with_booking_history_cannot_be_deleted(self):
        booking = self.make_booking()
        booking.customer = self.customer
        booking.save(update_fields=["customer"])
        response = self.client.post(
            reverse(
                "management:management_user_action",
                args=[self.customer.pk, "delete"],
            ),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ban the account instead")
        self.assertTrue(User.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(PartyBuild.objects.filter(pk=booking.pk).exists())

    # This test protects the business rule described by “administrator can manage owner status
    # when another owner remains”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_administrator_can_manage_owner_status_when_another_owner_remains(self):
        other_owner = User.objects.create_user(
            "remaining-owner", password="Remaining-owner-pass-2026!"
        )
        Group.objects.get(name="Owners").user_set.add(other_owner)
        self.client.force_login(self.administrator)

        detail = self.client.get(
            reverse("management:management_user_detail", args=[self.owner.pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Ban account")

        response = self.client.post(
            reverse(
                "management:management_user_action", args=[self.owner.pk, "ban"]
            ),
            {"confirmation": "on"},
        )
        self.assertRedirects(
            response,
            reverse("management:management_user_detail", args=[self.owner.pk]),
        )
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)

    # This test protects the business rule described by “final active owner cannot be banned”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_final_active_owner_cannot_be_banned(self):
        self.client.force_login(self.administrator)
        response = self.client.post(
            reverse(
                "management:management_user_action", args=[self.owner.pk, "ban"]
            ),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "At least one other active Owner must remain")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    # This test protects the business rule described by “management pages share one content
    # frame”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_management_pages_share_one_content_frame(self):
        response = self.client.get(reverse("management:management_user_list"))
        self.assertContains(
            response,
            'class="management-content-frame management-topbar-inner"',
        )
        self.assertContains(
            response,
            'class="management-main management-content-frame"',
        )

    # This test protects the business rule described by “user list shows role appropriate
    # actions”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_user_list_shows_role_appropriate_actions(self):
        response = self.client.get(reverse("management:management_user_list"))
        html = response.content.decode("utf-8")
        customer_row = html.split(self.customer.username, 1)[1].split("</tr>", 1)[0]
        worker_row = html.split(self.worker_user.username, 1)[1].split("</tr>", 1)[0]
        self.assertNotIn("Edit worker settings", customer_row)
        self.assertIn("Edit worker settings", worker_row)

    # This test protects the business rule described by “management css defines readable theme
    # button states”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_management_css_defines_readable_theme_button_states(self):
        css = (settings.BASE_DIR / "static/css/management.css").read_text()
        for token in (
            "--management-button-primary-text",
            "--management-button-secondary-text",
            "--management-button-danger-text",
            "--management-button-disabled-text",
            "--management-content-max",
            "--management-content-padding",
        ):
            self.assertIn(token, css)
        self.assertIn('.management-button[aria-disabled="true"]', css)
        self.assertIn(".management-topbar-inner", css)



# This group of tests protects the dedicated management completion action. It verifies that full
# managers can find and use the action while customers, future events, and final bookings remain
# outside the workflow.
class ManagementPartyCompletionTests(TestCase):
    # This setup creates the minimum set of roles and catalogue records required to exercise the
    # management booking page without changing any unrelated management feature.
    @classmethod
    def setUpTestData(cls):
        cls.administrator = User.objects.create_superuser(
            "done-management-admin",
            "done-admin@example.test",
            "Admin-pass-123!",
        )
        cls.owner = User.objects.create_user(
            "done-management-owner",
            password="Owner-pass-123!",
        )
        cls.customer = User.objects.create_user(
            "done-management-customer",
            password="Customer-pass-123!",
        )
        Group.objects.get(name="Owners").user_set.add(cls.owner)
        cls.package = PartyPackage.objects.get(slug="basic-popadoo-party")
        cls.tier = GuestPriceTier.objects.filter(package=cls.package).first()

    # This helper creates a booking with a chosen operational state so the page and endpoint can be
    # checked against past, future, cancelled, and already-completed parties.
    def make_booking(
        self,
        *,
        status=PartyBuild.Status.CONFIRMED,
        event_date=None,
        completed_at=None,
    ):
        return PartyBuild.objects.create(
            customer=self.customer,
            package=self.package,
            guest_tier=self.tier,
            contact_name="Management Completion Parent",
            contact_email="management-completion@example.test",
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
            completed_at=completed_at,
        )

    # This test confirms the action also appears for the submitted status used by existing checkout
    # records, so a manager can close a past party without first repairing an older workflow label.
    def test_booking_detail_shows_completion_action_when_eligible(self):
        booking = self.make_booking(status=PartyBuild.Status.SUBMITTED)
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse(
                "management:management_booking_detail",
                args=[booking.public_id],
            )
        )
        self.assertContains(response, "Complete this party")
        self.assertContains(response, "Mark party as done")
        self.assertContains(response, "allows the customer to rate the party")

    # This test keeps the active action off pages where the event is in the future, cancelled, or
    # already final, while still showing an understandable state explanation.
    def test_booking_detail_hides_completion_action_when_ineligible(self):
        bookings = (
            self.make_booking(event_date=timezone.localdate() + timedelta(days=1)),
            self.make_booking(status=PartyBuild.Status.CANCELLED),
            self.make_booking(
                status=PartyBuild.Status.COMPLETED,
                completed_at=timezone.now(),
            ),
        )
        self.client.force_login(self.owner)
        for booking in bookings:
            with self.subTest(status=booking.status, event_date=booking.event_date):
                response = self.client.get(
                    reverse(
                        "management:management_booking_detail",
                        args=[booking.public_id],
                    )
                )
                self.assertNotContains(response, ">Mark party as done<")

    # This test verifies both full-management roles can complete the submitted status found in the
    # current project data and receive the same trusted final status and server timestamp.
    def test_owner_and_administrator_can_use_completion_endpoint(self):
        for actor in (self.owner, self.administrator):
            with self.subTest(actor=actor.username):
                booking = self.make_booking(status=PartyBuild.Status.SUBMITTED)
                self.client.force_login(actor)
                response = self.client.post(
                    reverse(
                        "management:management_booking_complete",
                        args=[booking.public_id],
                    )
                )
                self.assertRedirects(
                    response,
                    reverse(
                        "management:management_booking_detail",
                        args=[booking.public_id],
                    ),
                )
                booking.refresh_from_db()
                self.assertEqual(booking.status, PartyBuild.Status.COMPLETED)
                self.assertIsNotNone(booking.completed_at)

    # This test protects the dedicated endpoint from customer accounts even when they own the
    # booking, because completion confirms service delivery rather than customer intent.
    def test_customer_cannot_call_management_completion_endpoint(self):
        booking = self.make_booking()
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse(
                "management:management_booking_complete",
                args=[booking.public_id],
            )
        )
        self.assertEqual(response.status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)

    # This test ensures opening the completion address cannot change a booking; the manager must
    # submit the protected POST form shown on the detail page.
    def test_management_completion_endpoint_rejects_get(self):
        booking = self.make_booking()
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse(
                "management:management_booking_complete",
                args=[booking.public_id],
            )
        )
        self.assertEqual(response.status_code, 405)
        booking.refresh_from_db()
        self.assertEqual(booking.status, PartyBuild.Status.CONFIRMED)
