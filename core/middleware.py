# This file handles request-wide behaviour that must run consistently around many pages.
# Middleware can inspect or adjust a request before a view runs and can shape the response
# afterwards, avoiding repeated code in every page.

from __future__ import annotations

from django.conf import settings


# This class groups the information and behaviour needed for popadoo security headers middleware.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class PopadooSecurityHeadersMiddleware:
    """Add a strict content policy without changing page content."""

    # This method handles init for the surrounding popadoo security headers middleware.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, get_response):
        self.get_response = get_response

    # This method handles call for the surrounding popadoo security headers middleware.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __call__(self, request):
        response = self.get_response(request)

        # Every page, including the custom management panel, loads scripts and
        # styles from local static files, so one strict policy can protect the
        # entire application.
        response.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
        response.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response
