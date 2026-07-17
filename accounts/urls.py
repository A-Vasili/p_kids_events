# This file maps readable website addresses to the part of Popadoo responsible for answering each
# request.
# The route order also protects specialised management and messaging paths from being swallowed by
# broader URL groups.
# It contains no page logic; the matched view performs the actual work.

from django.urls import path

from . import views

app_name = "accounts"

# These named routes connect stable website addresses to the views that handle each customer or
# staff request.
# Permission checks remain inside the views, so knowing an address never grants access by itself.
urlpatterns = [
    path("sign-up/", views.SignUpView.as_view(), name="accounts_sign_up"),
    path("sign-in/", views.SignInView.as_view(), name="accounts_sign_in"),
    path("sign-out/", views.SignOutView.as_view(), name="accounts_sign_out"),
    path("profile/", views.ProfileUpdateView.as_view(), name="accounts_profile"),
    path(
        "dashboard/",
        views.CustomerDashboardView.as_view(),
        name="accounts_customer_dashboard",
    ),
]
