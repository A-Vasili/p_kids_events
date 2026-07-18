# This file protects the public-facing pages and shared request behaviour used across the website
# with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


# This group of tests protects the public page tests behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class PublicPageTests(TestCase):
    # Verify that current public pages load. The test client sends GET to reverse(route_name); the
    # required outcome is HTTP 200.
    def test_current_public_pages_load(self):
        route_names = [
            "core:core_home",
            "core:core_gallery",
            "core:core_about",
            "core:core_testimonials",
        ]

        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

    # Verify that each current page has one main landmark. The test client sends GET to
    # reverse(route_name); the required outcome is html count is 1.
    def test_each_current_page_has_one_main_landmark(self):
        route_names = [
            "core:core_home",
            "core:core_gallery",
            "core:core_about",
            "core:core_testimonials",
        ]

        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                html = response.content.decode("utf-8")
                self.assertEqual(html.count('<main id="main-content">'), 1)

    # Verify that legacy public routes keep useful destinations. The test client sends GET to
    # reverse(route_name); the required outcome is redirects to target.
    def test_legacy_public_routes_keep_useful_destinations(self):
        destinations = {
            "core:core_packages_redirect": reverse("party_ideas:list"),
            "core:core_contact_redirect": reverse(
                "party_builder:party_builder_package_options"
            ),
        }
        for route_name, target in destinations.items():
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertRedirects(
                    response,
                    target,
                    status_code=301,
                    fetch_redirect_response=False,
                )

    # This test protects the hosted project from showing the original company name on its main public page.
    # The logo artwork may stay the same, but visible branding must identify P Kids Events.
    def test_homepage_uses_hosted_company_name(self):
        response = self.client.get(reverse("core:core_home"))
        self.assertContains(response, "P Kids Events")
        self.assertNotContains(response, "Popadoo Kids Events")

    # This test confirms that public pages no longer direct visitors to the real company’s social
    # account or branded email address after the hosting rebrand.
    def test_public_pages_do_not_include_original_instagram_or_email(self):
        for route_name in ("core:core_home", "core:core_about"):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertNotContains(response, "instagram.com/popadoo_kidsevents")
                self.assertNotContains(response, "hello@popadookidsevents.gr")


# This group of tests protects the navigation and security tests behaviour as one related customer
# or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class NavigationAndSecurityTests(TestCase):
    """Check the shared navigation order and browser security boundary."""

    # Verify that header has one builder cta and a separate party ideas link. The test client sends
    # GET to core:core_home; the required outcome is header includes 'Make Your Own Party', header
    # includes party_ideas:list, and header count is 1.
    def test_header_has_one_builder_cta_and_a_separate_party_ideas_link(self):
        response = self.client.get(reverse("core:core_home"))
        html = response.content.decode("utf-8")
        header = html.split("<header", 1)[1].split("</header>", 1)[0]
        self.assertIn("Make Your Own Party", header)
        self.assertIn(reverse("party_ideas:list"), header)
        self.assertEqual(
            header.count(reverse("party_builder:party_builder_package_options")),
            1,
        )

    # Verify that the home page exposes both discovery and direct-builder journeys, with at least
    # two links to Party Ideas and at least two links to package selection.
    def test_homepage_offers_discovery_and_direct_builder_paths(self):
        response = self.client.get(reverse("core:core_home"))
        html = response.content.decode("utf-8")
        self.assertIn("Explore Party Ideas", html)
        self.assertIn("Start building freely", html)
        self.assertGreaterEqual(
            html.count(reverse("party_builder:party_builder_package_options")),
            2,
        )
        self.assertGreaterEqual(html.count(reverse("party_ideas:list")), 2)

    # Verify that the header renders a separate utility stripe containing the language picker and
    # account selector before the main navigation row.
    def test_header_has_separate_language_and_account_stripe(self):
        response = self.client.get(reverse("core:core_home"))
        html = response.content.decode("utf-8")
        header = html.split("<header", 1)[1].split("</header>", 1)[0]

        self.assertIn("header-utility-stripe", header)
        self.assertIn("custom-language-picker", header)
        self.assertIn("header-account-selector", header)
        self.assertLess(
            header.index("header-utility-stripe"),
            header.index("header-main-row"),
        )

    # Verify that security headers are added to public pages. The test client sends GET to
    # core:core_home; the required outcome is response content-security-policy includes "default-src
    # 'self'", response cross-origin-resource-policy equals 'same-origin', and response
    # permissions-policy includes 'payment=()'.
    def test_security_headers_are_added_to_public_pages(self):
        response = self.client.get(reverse("core:core_home"))
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertIn("payment=()", response["Permissions-Policy"])

    # Verify that static and media URLs are absolute site paths. The required outcome is
    # settings.STATIC_URL.startswith('/') is true and settings.MEDIA_URL.startswith('/') is true.
    def test_static_and_media_urls_are_absolute_site_paths(self):
        """Nested public pages must not resolve assets relative to their URL."""

        self.assertTrue(settings.STATIC_URL.startswith("/"))
        self.assertTrue(settings.MEDIA_URL.startswith("/"))

# This group of tests protects the consolidated static asset tests behaviour as one related
# customer or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ConsolidatedStaticAssetTests(TestCase):
    """Ensure templates reference only the surviving consolidated assets."""

    # Verify that public content pages use shared stylesheet. The test client sends GET to
    # reverse(route_name); the required outcome is renders '/static/css/content-pages.css', does not
    # expose '/static/css/about.css', and does not expose '/static/css/gallery.css'.
    def test_public_content_pages_use_shared_stylesheet(self):
        for route_name in (
            "core:core_about",
            "core:core_gallery",
            "core:core_testimonials",
        ):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, "/static/css/content-pages.css")
                self.assertNotContains(response, "/static/css/about.css")
                self.assertNotContains(response, "/static/css/gallery.css")
                self.assertNotContains(response, "/static/css/testimonials.css")

    # Verify that base uses consolidated navigation assets. The test client sends GET to
    # core:core_home; the required outcome is renders '/static/css/navigation.css', does not expose
    # '/static/css/account-navigation.css', and does not expose '/static/css/header-utility.css'.
    def test_base_uses_consolidated_navigation_assets(self):
        response = self.client.get(reverse("core:core_home"))
        self.assertContains(response, "/static/css/navigation.css")
        self.assertNotContains(response, "/static/css/account-navigation.css")
        self.assertNotContains(response, "/static/css/header-utility.css")
        self.assertNotContains(response, "/static/js/account-menu.js")
        self.assertContains(response, "/static/js/main.js")

    # Verify that custom-controls.css loads before navigation.css so header overrides remain
    # predictable, and that the language picker retains combobox and aria-controls markup.
    def test_generic_custom_controls_load_before_header_navigation_overrides(self):
        response = self.client.get(reverse("core:core_home"))
        html = response.content.decode("utf-8")
        self.assertLess(
            html.index("/static/css/custom-controls.css"),
            html.index("/static/css/navigation.css"),
        )
        self.assertIn('role="combobox"', html)
        self.assertIn('aria-controls="language-selector-options"', html)

