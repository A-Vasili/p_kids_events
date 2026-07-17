"""Public account pages and the customer booking dashboard.

These views handle HTTP flow only.  Forms own validation and the party builder
models provide the booking records shown to each signed-in customer.
"""
# This file coordinates page requests for this area of Popadoo.
# Each view checks who is making the request, gathers only the records they are allowed to see,
# and chooses the template or response to return.
# Multi-step business changes are delegated to services so page handling remains separate from
# data rules.

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from party_builder.models import PartyBuild

from .forms import PopadooAuthenticationForm, ProfileForm, SignUpForm
from .models import CustomerProfile


# This view coordinates the sign up view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class SignUpView(FormView):
    template_name = "accounts/sign_up.html"
    form_class = SignUpForm
    success_url = reverse_lazy("accounts:accounts_customer_dashboard")

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("accounts:accounts_customer_dashboard")
        return super().dispatch(request, *args, **kwargs)

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        # The success message welcomes the new customer using the hosted company name without changing registration behaviour.
        messages.success(self.request, "Your account is ready. Welcome to P Kids Events.")
        return super().form_valid(form)


# This view coordinates the sign in view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class SignInView(LoginView):
    template_name = "accounts/sign_in.html"
    authentication_form = PopadooAuthenticationForm
    redirect_authenticated_user = True


# This view coordinates the sign out view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class SignOutView(LogoutView):
    next_page = reverse_lazy("core:core_home")
    http_method_names = ["post", "options"]


# This view coordinates the profile update view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class ProfileUpdateView(LoginRequiredMixin, FormView):
    template_name = "accounts/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:accounts_profile")

    # This helper retrieves form kwargs for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
        kwargs["instance"] = profile
        kwargs["user"] = self.request.user
        return kwargs

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Your saved details were updated.")
        return super().form_valid(form)


# This view coordinates the customer dashboard view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CustomerDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/dashboard.html"

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bookings"] = (
            PartyBuild.objects.filter(customer=self.request.user)
            .select_related("package", "guest_tier", "review")
            .prefetch_related("addon_items__addon")[:20]
        )
        return context
