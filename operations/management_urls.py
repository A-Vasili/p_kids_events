# This file lists the addresses available inside Popadoo’s custom management area.
# Routes are grouped by business area so the sidebar, views, and permission checks can refer to
# stable names.
# The presence of a route does not grant access; each management view still checks the signed-in
# account.

from django.urls import path

from . import management_views as views

app_name = "management"

# These named routes connect stable website addresses to the views that handle each customer or
# staff request.
# Permission checks remain inside the views, so knowing an address never grants access by itself.
urlpatterns = [
    path("", views.ManagementDashboardView.as_view(), name="management_dashboard"),
    path("catalogue/", views.CatalogueIndexView.as_view(), name="management_catalogue"),

    path("categories/", views.CategoryListView.as_view(), name="management_category_list"),
    path("categories/create/", views.CategoryCreateView.as_view(), name="management_category_create"),
    path("categories/<int:pk>/", views.CategoryDetailView.as_view(), name="management_category_detail"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="management_category_update"),
    path("categories/<int:pk>/remove/", views.CategoryRemoveView.as_view(), name="management_category_remove"),

    path("catalogue/packages/", views.PackageListView.as_view(), name="management_package_list"),
    path("catalogue/packages/create/", views.PackageCreateView.as_view(), name="management_package_create"),
    path("catalogue/packages/<int:pk>/", views.PackageDetailView.as_view(), name="management_package_detail"),
    path("catalogue/packages/<int:pk>/edit/", views.PackageUpdateView.as_view(), name="management_package_update"),
    path("catalogue/packages/<int:pk>/remove/", views.PackageRemoveView.as_view(), name="management_package_remove"),

    path("catalogue/tiers/", views.LegacyTierCompatibilityView.as_view(), name="management_tier_list"),
    path("catalogue/tiers/create/", views.LegacyTierCompatibilityView.as_view(), name="management_tier_create"),
    path("catalogue/packages/<int:package_id>/tiers/create/", views.LegacyTierCompatibilityView.as_view(), name="management_package_tier_create"),
    path("catalogue/tiers/<int:pk>/edit/", views.LegacyTierCompatibilityView.as_view(), name="management_tier_update"),
    path("catalogue/tiers/<int:pk>/remove/", views.LegacyTierCompatibilityView.as_view(), name="management_tier_remove"),

    path("catalogue/addons/", views.AddonListView.as_view(), name="management_addon_list"),
    path("catalogue/addons/create/", views.AddonCreateView.as_view(), name="management_addon_create"),
    path("catalogue/addons/<int:pk>/", views.AddonDetailView.as_view(), name="management_addon_detail"),
    path("catalogue/addons/<int:pk>/edit/", views.AddonUpdateView.as_view(), name="management_addon_update"),
    path("catalogue/addons/<int:pk>/remove/", views.AddonRemoveView.as_view(), name="management_addon_remove"),

    path("users/", views.UserListView.as_view(), name="management_user_list"),
    path("users/create-worker/", views.UserCreateWorkerView.as_view(), name="management_user_create_worker"),
    path("users/create-owner/", views.UserCreateOwnerView.as_view(), name="management_user_create_owner"),
    path("users/<int:pk>/", views.UserDetailView.as_view(), name="management_user_detail"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="management_user_update"),
    path("users/<int:pk>/<str:action>/", views.UserActionView.as_view(), name="management_user_action"),

    path("bookings/", views.BookingListView.as_view(), name="management_booking_list"),
    path("bookings/<uuid:public_id>/", views.BookingDetailView.as_view(), name="management_booking_detail"),
    path("bookings/<uuid:public_id>/status/", views.BookingStatusUpdateView.as_view(), name="management_booking_status"),
    # This dedicated POST route makes party completion easy to find while keeping the existing
    # general status workflow available for every other management transition.
    path("bookings/<uuid:public_id>/complete/", views.BookingCompleteView.as_view(), name="management_booking_complete"),
    path("bookings/<uuid:public_id>/manual-review/", views.BookingManualReviewView.as_view(), name="management_booking_manual_review"),
    path("bookings/<uuid:public_id>/assign/", views.BookingAssignView.as_view(), name="management_booking_assign"),

    path("schedules/", views.ScheduleView.as_view(), name="management_schedule"),
    path("audit/", views.AuditListView.as_view(), name="management_audit"),
    path("analytics/", views.AnalyticsView.as_view(), name="management_analytics"),
]
