# This file maps readable website addresses to the part of Popadoo responsible for answering each
# request.
# The route order also protects specialised management and messaging paths from being swallowed by
# broader URL groups.
# It contains no page logic; the matched view performs the actual work.

from django.urls import path

from . import party_ideas

app_name = "party_ideas"

# These named routes connect stable website addresses to the views that handle each customer or
# staff request.
# Permission checks remain inside the views, so knowing an address never grants access by itself.
# Django needs this to remain a real list of routes; pointing it at the imported view module would
# stop the whole website during startup before any Party Ideas page could be opened.
urlpatterns = [
    path("", party_ideas.PartyIdeasListView.as_view(), name="list"),
    path(
        "packages/<slug:slug>/",
        party_ideas.PartyPackageDetailView.as_view(),
        name="package_detail",
    ),
    path(
        "experiences/<slug:slug>/",
        party_ideas.PartyAddonDetailView.as_view(),
        name="addon_detail",
    ),
    path(
        "categories/<slug:slug>/",
        party_ideas.PartyIdeasCategoryView.as_view(),
        name="category_detail",
    ),
    path(
        "packages/<slug:slug>/start/",
        party_ideas.StartPackageView.as_view(),
        name="start_package",
    ),
    path(
        "experiences/<slug:slug>/add/",
        party_ideas.AddAddonView.as_view(),
        name="add_addon",
    ),
]