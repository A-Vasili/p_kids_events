# This file coordinates page requests for this area of Popadoo.
# Each view checks who is making the request, gathers only the records they are allowed to see,
# and chooses the template or response to return.
# Multi-step business changes are delegated to services so page handling remains separate from
# data rules.

from __future__ import annotations

from datetime import date, time
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView

from .analytics import addon_popularity, recommend_addons, review_score_updates
from .forms import (
    PackageOptionsForm,
    PartyDetailsForm,
    PartyReviewForm,
    ReviewCodeForm,
    SimulatedPaymentForm,
)
from .models import AddonExperience, PartyBuild, PartyPackage
from .party_ideas import public_package_queryset, visible_addon_categories
from .review_services import (
    authorize_review_session,
    get_reviewable_booking,
    review_session_is_authorized,
    save_party_review,
    verify_review_code,
)
from .services import (
    AUTHORIZED_BUILD_SESSION_KEY,
    active_session_addons,
    calculate_party_quote,
    checkout_state,
    clear_checkout_state,
    create_completed_party_build,
    resolve_active_package,
    save_checkout_state,
    select_package,
)


# This class groups the information and behaviour needed for checkout state mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class CheckoutStateMixin:
    """Shared session and catalogue helpers for the checkout steps."""

    package: PartyPackage

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.package = self.get_package()
        # Old browser sessions may reference catalogue items that were archived.
        # Cleaning the add-on list here prevents hidden items reaching pricing.
        self.get_selected_addons()
        return super().dispatch(request, *args, **kwargs)

    # This helper retrieves package for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_package(self) -> PartyPackage:
        package = resolve_active_package(self.request.session)
        if package is None:
            raise Http404("No active party package is currently available.")
        return package

    # This helper retrieves checkout state for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_checkout_state(self) -> dict[str, Any]:
        return checkout_state(self.request.session)

    # This method handles save checkout state for the surrounding checkout state mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def save_checkout_state(self, state: dict[str, Any]) -> None:
        save_checkout_state(self.request.session, state)

    # This method handles clear checkout state for the surrounding checkout state mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def clear_checkout_state(self) -> None:
        clear_checkout_state(self.request.session)

    # This helper retrieves selected addons for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_selected_addons(self) -> list[AddonExperience]:
        return active_session_addons(self.request.session)

    # This helper retrieves quote context for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_quote_context(self) -> dict[str, Any]:
        addons = self.get_selected_addons()
        return {
            "package": self.package,
            "selected_addons": addons,
            "quote": calculate_party_quote(self.package, addons),
        }


# This view coordinates the party options view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyOptionsView(CheckoutStateMixin, FormView):
    """Step one: choose a capacity-based package and optional experiences."""

    template_name = "party_builder/options.html"
    form_class = PackageOptionsForm

    # This helper retrieves form kwargs for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["package"] = self.package
        state = self.get_checkout_state()
        if self.request.method == "GET":
            kwargs["initial"] = {
                "package": state.get("package_id") or self.package.pk,
                "addons": state.get("addon_ids", []),
            }
        return kwargs

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        selected_package_id = str(form["package"].value() or self.package.pk)
        selected_addon_ids = {str(value) for value in (form["addons"].value() or [])}
        addons = list(form.fields["addons"].queryset)
        selected_addons = [addon for addon in addons if str(addon.pk) in selected_addon_ids]
        package_options = list(public_package_queryset().order_by("display_order", "name"))
        displayed_package = next(
            (option for option in package_options if str(option.pk) == selected_package_id),
            self.package,
        )
        popularity = addon_popularity(days=365)
        # The filter row includes only categories that can reveal at least one active experience.
        # Broader categories remain available when their experiences live in subcategories.
        addon_categories = list(visible_addon_categories())
        context.update(
            {
                "package": displayed_package,
                "package_options": package_options,
                "selected_package_id": selected_package_id,
                "addon_categories": addon_categories,
                "addon_options": [
                    {
                        "addon": addon,
                        "selected": str(addon.pk) in selected_addon_ids,
                        "analytics": popularity["by_id"].get(addon.pk, {}),
                    }
                    for addon in addons
                ],
                "recommendations": recommend_addons(
                    selected_ids=[addon.pk for addon in selected_addons],
                    package=displayed_package,
                    popularity_by_id=popularity["by_id"],
                ),
                "initial_quote": calculate_party_quote(displayed_package, selected_addons),
                "current_step": 1,
            }
        )
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        package = form.cleaned_data["package"]
        addons = list(form.cleaned_data["addons"])
        state = select_package(self.request.session, package)
        state["addon_ids"] = [addon.pk for addon in addons]
        self.save_checkout_state(state)
        return redirect("party_builder:party_builder_customer_details")


# This view coordinates the party details view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyDetailsView(CheckoutStateMixin, FormView):
    """Step two: collect personal, venue, and event information."""

    template_name = "party_builder/details.html"
    form_class = PartyDetailsForm

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        if not checkout_state(request.session).get("package_id"):
            return redirect("party_builder:party_builder_package_options")
        return super().dispatch(request, *args, **kwargs)

    # This helper retrieves form kwargs for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["show_save_profile"] = self.request.user.is_authenticated
        kwargs["user"] = self.request.user
        state = self.get_checkout_state()
        if self.request.method == "GET" and state.get("details"):
            kwargs["initial"] = state["details"]
        elif self.request.method == "GET" and self.request.user.is_authenticated:
            from accounts.models import CustomerProfile

            profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
            kwargs["initial"] = {
                "contact_name": self.request.user.get_full_name(),
                "contact_email": self.request.user.email,
                "contact_phone": profile.phone,
                "event_address": profile.default_address,
                "postal_code": profile.default_postal_code,
            }
        return kwargs

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_quote_context())
        context["current_step"] = 2
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        cleaned = form.cleaned_data
        state = self.get_checkout_state()
        state["details"] = {
            "contact_name": cleaned["contact_name"],
            "contact_email": cleaned["contact_email"],
            "contact_phone": cleaned["contact_phone"],
            "event_date": cleaned["event_date"].isoformat(),
            "event_time": cleaned["event_time"].isoformat() if cleaned.get("event_time") else "",
            "event_address": cleaned["event_address"],
            "postal_code": cleaned["postal_code"],
            "notes": cleaned.get("notes", ""),
        }
        state.pop("details_need_review", None)
        self.save_checkout_state(state)
        if self.request.user.is_authenticated and cleaned.get("save_profile"):
            from accounts.models import CustomerProfile

            profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
            profile.phone = cleaned["contact_phone"]
            profile.default_address = cleaned["event_address"]
            profile.default_postal_code = cleaned["postal_code"]
            profile.save(update_fields=["phone", "default_address", "default_postal_code", "updated_at"])
            self.request.user.first_name = cleaned["contact_name"].split(" ", 1)[0]
            if " " in cleaned["contact_name"]:
                self.request.user.last_name = cleaned["contact_name"].split(" ", 1)[1]
            self.request.user.email = cleaned["contact_email"]
            self.request.user.save(update_fields=["first_name", "last_name", "email"])
        return redirect("party_builder:party_builder_simulated_checkout")


# This view coordinates the party checkout view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyCheckoutView(CheckoutStateMixin, FormView):
    """Step three: review the cart and validate a simulated card payment."""

    template_name = "party_builder/checkout.html"
    form_class = SimulatedPaymentForm

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        if not checkout_state(request.session).get("package_id"):
            return redirect("party_builder:party_builder_package_options")
        state = checkout_state(request.session)
        if not state.get("details"):
            return redirect("party_builder:party_builder_customer_details")
        try:
            self._deserialize_details(state["details"])
        except (KeyError, TypeError, ValueError):
            state.pop("details", None)
            save_checkout_state(request.session, state)
            return redirect("party_builder:party_builder_customer_details")
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_quote_context())
        context["details"] = self.get_checkout_state()["details"]
        context["current_step"] = 3
        return context

    # This method handles deserialize details for the surrounding party checkout view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @staticmethod
    def _deserialize_details(raw_details: dict[str, Any]) -> dict[str, Any]:
        return {
            **raw_details,
            "event_date": date.fromisoformat(raw_details["event_date"]),
            "event_time": (
                time.fromisoformat(raw_details["event_time"])
                if raw_details.get("event_time")
                else None
            ),
        }

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        state = self.get_checkout_state()
        addons = self.get_selected_addons()
        party_build = create_completed_party_build(
            package=self.package,
            addons=addons,
            details=self._deserialize_details(state["details"]),
            payment=form.safe_payment_result(),
            customer=self.request.user,
        )

        permitted_builds = self.request.session.get(AUTHORIZED_BUILD_SESSION_KEY, [])
        permitted_builds.append(str(party_build.public_id))
        self.request.session[AUTHORIZED_BUILD_SESSION_KEY] = permitted_builds[-10:]
        self.clear_checkout_state()
        return HttpResponseRedirect(party_build.get_absolute_url())


# This view coordinates the party builder restart view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyBuilderRestartView(CheckoutStateMixin, View):
    """Clear the in-progress cart and return to the first checkout step."""

    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, *args, **kwargs):
        self.clear_checkout_state()
        return redirect("party_builder:party_builder_package_options")


# This view coordinates the party build success view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyBuildSuccessView(DetailView):
    """Show the completed simulated order only to its creating browser session."""

    model = PartyBuild
    template_name = "party_builder/build_success.html"
    context_object_name = "party_build"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("package", "guest_tier")
            .prefetch_related("addon_items__addon")
        )

    # This helper retrieves object for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_object(self, queryset=None):
        party_build = super().get_object(queryset)
        permitted_builds = self.request.session.get(
            AUTHORIZED_BUILD_SESSION_KEY,
            [],
        )
        owns_booking = (
            self.request.user.is_authenticated
            and party_build.customer_id == self.request.user.pk
        )
        if (
            str(party_build.public_id) not in permitted_builds
            and not owns_booking
            and not self.request.user.is_superuser
        ):
            raise Http404("This order summary is not available to this account or session.")
        return party_build


# This view coordinates the party review code view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyReviewCodeView(LoginRequiredMixin, FormView):
    """Verify a private code before opening a completed booking review."""

    template_name = "party_builder/review_code.html"
    form_class = ReviewCodeForm

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        try:
            booking = verify_review_code(
                user=self.request.user,
                submitted_code=form.cleaned_data["review_code"],
            )
        except ValidationError as error:
            form.add_error("review_code", error.messages[0])
            return self.form_invalid(form)
        authorize_review_session(self.request, booking)
        return redirect(
            "party_builder:party_builder_review",
            public_id=booking.public_id,
        )


# This view coordinates the party review view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyReviewView(LoginRequiredMixin, TemplateView):
    """Display feedback fields for the package and selected add-ons only."""

    template_name = "party_builder/review.html"

    # This helper retrieves booking for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_booking(self):
        booking = get_reviewable_booking(
            user=self.request.user,
            public_id=self.kwargs["public_id"],
        )
        if not review_session_is_authorized(self.request, booking):
            raise PermissionDenied("Verify the party code before opening the review form.")
        return booking

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking = kwargs.get("booking") or self.get_booking()
        addon_items = list(booking.addon_items.all())
        review_stats = review_score_updates(
            package_id=booking.package_id,
            addon_ids=[item.addon_id for item in addon_items],
        )
        for item in addon_items:
            item.rating_summary = review_stats["addons"].get(str(item.addon_id), {})
        context.update(
            {
                "booking": booking,
                "review_form": kwargs.get("review_form")
                or PartyReviewForm(booking=booking),
                "review_stats": review_stats,
            }
        )
        return context


# This function handles review template context as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _review_template_context(booking, form):
    """Build the same rating summaries for valid and invalid form renders."""

    addon_items = list(booking.addon_items.all())
    review_stats = review_score_updates(
        package_id=booking.package_id,
        addon_ids=[item.addon_id for item in addon_items],
    )
    for item in addon_items:
        item.rating_summary = review_stats["addons"].get(str(item.addon_id), {})
    return {
        "booking": booking,
        "review_form": form,
        "review_stats": review_stats,
    }


# This function handles json form errors as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _json_form_errors(form):
    return {
        field: [error["message"] for error in errors.get_json_data()]
        for field, errors in form.errors.items()
    }


# This view coordinates the party review submit view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyReviewSubmitView(LoginRequiredMixin, View):
    """Save review feedback through AJAX or a normal accessible POST fallback."""

    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, *args, **kwargs):
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        try:
            booking = get_reviewable_booking(
                user=request.user,
                public_id=kwargs["public_id"],
            )
        except PermissionDenied:
            if is_ajax:
                return JsonResponse(
                    {"ok": False, "message": "This review is not available to your account."},
                    status=403,
                )
            raise
        if not review_session_is_authorized(request, booking):
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"ok": False, "message": "Verify the party code before submitting feedback."},
                    status=403,
                )
            raise PermissionDenied("Verify the party code before submitting feedback.")

        form = PartyReviewForm(request.POST, booking=booking)
        if not form.is_valid():
            if is_ajax:
                return JsonResponse(
                    {
                        "ok": False,
                        "message": "Please correct the highlighted review fields.",
                        "errors": _json_form_errors(form),
                    },
                    status=400,
                )
            return render(
                request,
                "party_builder/review.html",
                _review_template_context(booking, form),
            )

        try:
            review, created, stats, outcome = save_party_review(
                booking=booking,
                reviewer=request.user,
                package_score=form.cleaned_data["package_score"],
                comment=form.cleaned_data.get("comment", ""),
                addon_scores=form.addon_scores(),
                visibility=form.cleaned_data["visibility"],
                testimonial_name_display=form.cleaned_data[
                    "testimonial_name_display"
                ],
            )
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for field_name, field_messages in error.message_dict.items():
                    target = field_name if field_name in form.fields else None
                    for field_message in field_messages:
                        form.add_error(target, field_message)
            else:
                for field_message in error.messages:
                    form.add_error(None, field_message)
            message = "Please correct the highlighted review fields."
            if is_ajax:
                return JsonResponse(
                    {
                        "ok": False,
                        "message": message,
                        "errors": _json_form_errors(form),
                    },
                    status=400,
                )
            return render(
                request,
                "party_builder/review.html",
                _review_template_context(booking, form),
            )

        message = outcome["message"]
        if is_ajax:
            return JsonResponse(
                {
                    "ok": True,
                    "message": message,
                    "visibility": outcome["visibility"],
                    "is_public_testimonial": outcome["is_public_testimonial"],
                    "stats": stats,
                }
            )
        messages.success(request, message)
        return redirect(
            "party_builder:party_builder_review",
            public_id=booking.public_id,
        )


# This view coordinates the party recommendation view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyRecommendationView(View):
    """Return minimal public recommendation data for the live party builder."""

    http_method_names = ["get"]

    # This request method displays the current page and its permitted records.
    def get(self, request, *args, **kwargs):
        package_value = request.GET.get("package", "")
        requested_package = (
            PartyPackage.objects.filter(pk=int(package_value), is_active=True).first()
            if package_value.isdigit()
            else None
        )
        package = (
            requested_package
            or PartyPackage.objects.filter(is_active=True, is_default=True).first()
            or PartyPackage.objects.filter(is_active=True).first()
        )
        if package is None:
            return JsonResponse({"recommendations": []})
        raw_addon_values = []
        for value in request.GET.getlist("addons"):
            raw_addon_values.extend(part.strip() for part in value.split(","))
        selected_ids = [int(value) for value in raw_addon_values if value.isdigit()]
        recommendations = recommend_addons(
            selected_ids=selected_ids,
            package=package,
        )
        return JsonResponse(
            {
                "recommendations": [
                    {
                        "id": row["addon"].pk,
                        "slug": row["addon"].slug,
                        "name": row["addon"].name,
                        "short_description": row["addon"].short_description,
                        "price": str(row["addon"].price),
                        "reason": row["reason"],
                        "reason_key": row.get("reason_key"),
                        "reason_values": row.get("reason_values", {}),
                        "pair_count": row["pair_count"],
                    }
                    for row in recommendations
                ]
            }
        )
