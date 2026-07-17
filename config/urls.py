# This file maps readable website addresses to the part of Popadoo responsible for answering each
# request.
# The route order also protects specialised management and messaging paths from being swallowed by
# broader URL groups.
# It contains no page logic; the matched view performs the actual work.
from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve as serve_media

# These named routes connect stable website addresses to the views that handle each customer or
# staff request.
# Permission checks remain inside the views, so knowing an address never grants access by itself.
urlpatterns = [
    path("", include("core.urls")),
    # Exact chat routes are resolved before the broader account and management includes.
    path("", include("communications.urls")),
    path("accounts/", include("accounts.urls")),
    path("operations/", include("operations.urls")),
    path("management/", include(("operations.management_urls", "management"), namespace="management")),
    path("party-ideas/", include(("party_builder.party_ideas_urls", "party_ideas"), namespace="party_ideas")),
    path("party-builder/", include("party_builder.urls")),
]

# Uploaded catalogue images live outside the collected static files. This
# controlled route is enabled locally and on the single-instance Render service
# so those owner-managed files can be read from the persistent media disk.
if settings.SERVE_MEDIA_FILES:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve_media,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
