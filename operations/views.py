# This file coordinates page requests for this area of Popadoo.
# Each view checks who is making the request, gathers only the records they are allowed to see,
# and chooses the template or response to return.
# Multi-step business changes are delegated to services so page handling remains separate from
# data rules.

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from accounts.models import WorkerProfile
from accounts.permissions import can_access_full_management, can_access_operations, is_worker
from party_builder.models import PartyBuild

from .forms import (
    DeclineAssignmentForm,
    WorkerAvailabilityForm,
    WorkerProfileForm,
)
from .models import PartyAssignment, WorkerAvailability
from .services.assignment import accept_assignment, decline_assignment
from .services.bookings import (
    booking_completion_block_reason,
    can_mark_booking_completed,
    mark_booking_completed,
)


# This class groups the information and behaviour needed for operations access mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class OperationsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_func(self):
        return can_access_operations(self.request.user)


# This class groups the information and behaviour needed for worker required mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class WorkerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_func(self):
        user = self.request.user
        return is_worker(user)

    # This helper retrieves worker profile for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_worker_profile(self):
        return get_object_or_404(
            WorkerProfile,
            user=self.request.user,
            is_active_worker=True,
        )


# This view coordinates the operations dashboard view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class OperationsDashboardView(OperationsAccessMixin, TemplateView):
    template_name = "operations/dashboard.html"

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and can_access_full_management(request.user):
            return redirect("management:management_dashboard")
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker = get_object_or_404(
            WorkerProfile,
            user=self.request.user,
            is_active_worker=True,
        )
        context.update(
            {
                "is_owner_panel": False,
                "pending_assignments": worker.assignments.filter(
                    status=PartyAssignment.Status.PENDING
                ).select_related("party_build__package")[:10],
                "upcoming_assignments": worker.assignments.filter(
                    status=PartyAssignment.Status.ACCEPTED,
                    party_build__event_date__gte=timezone.localdate(),
                ).select_related("party_build__package")[:10],
            }
        )
        return context


# This view coordinates the worker assignment list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerAssignmentListView(WorkerRequiredMixin, ListView):
    template_name = "operations/assignment_list.html"
    context_object_name = "assignments"
    paginate_by = 20

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return PartyAssignment.objects.filter(
            worker=self.get_worker_profile()
        ).select_related(
            "party_build__package", "worker__user"
        ).prefetch_related("party_build__addon_items__addon")


# This view coordinates the worker assignment detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerAssignmentDetailView(WorkerRequiredMixin, DetailView):
    model = PartyAssignment
    template_name = "operations/assignment_detail.html"
    context_object_name = "assignment"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return PartyAssignment.objects.filter(
            worker=self.get_worker_profile()
        ).select_related(
            "party_build__package", "party_build__guest_tier", "worker__user"
        ).prefetch_related("party_build__addon_items__addon")

    # This step prepares the decline form and a server-checked completion decision for this exact
    # assignment. The template can explain the available action, while the completion service still
    # repeats every safeguard when the worker submits it.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["decline_form"] = DeclineAssignmentForm()
        context["can_mark_party_done"] = can_mark_booking_completed(
            booking=self.object.party_build,
            actor=self.request.user,
            assignment=self.object,
        )
        context["completion_block_reason"] = booking_completion_block_reason(
            self.object.party_build
        )
        return context


# This view coordinates the worker assignment accept view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerAssignmentAcceptView(WorkerRequiredMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, pk):
        try:
            assignment = accept_assignment(
                assignment_id=pk,
                worker=self.get_worker_profile(),
                actor=request.user,
            )
        except (ValidationError, PartyAssignment.DoesNotExist) as error:
            messages.error(request, "; ".join(getattr(error, "messages", [str(error)])))
            return redirect("operations:operations_worker_assignment_detail", pk=pk)
        messages.success(request, "The party is now confirmed in your schedule.")
        return redirect("operations:operations_worker_assignment_detail", pk=assignment.pk)


# This POST-only view lets the signed-in assigned worker confirm delivery of their own party. The
# assignment is selected through that worker’s restricted queryset, and the service checks it again
# so changing the URL cannot complete somebody else’s booking.
class WorkerAssignmentCompleteView(WorkerRequiredMixin, View):
    http_method_names = ["post"]

    # This request records completion through the shared booking service, then returns the worker to
    # the assignment page with a plain-language explanation of the result.
    def post(self, request, pk):
        assignment = get_object_or_404(
            PartyAssignment.objects.select_related("party_build", "worker__user"),
            pk=pk,
            worker=self.get_worker_profile(),
        )
        try:
            completed = mark_booking_completed(
                booking=assignment.party_build,
                actor=request.user,
                assignment=assignment,
            )
        except (PermissionDenied, ValidationError) as error:
            messages.error(request, "; ".join(getattr(error, "messages", [str(error)])))
            return redirect(
                "operations:operations_worker_assignment_detail",
                pk=assignment.pk,
            )
        messages.success(
            request,
            "The party was marked as done. The customer can now leave a review.",
        )
        return redirect(
            "operations:operations_worker_assignment_detail",
            pk=assignment.pk,
        )


# This view coordinates the worker assignment decline view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerAssignmentDeclineView(WorkerRequiredMixin, FormView):
    form_class = DeclineAssignmentForm
    template_name = "operations/assignment_detail.html"

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.assignment = get_object_or_404(
            PartyAssignment,
            pk=kwargs["pk"],
            worker=self.get_worker_profile(),
        )
        return super().dispatch(request, *args, **kwargs)

    # This method handles form invalid for the surrounding worker assignment decline view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def form_invalid(self, form):
        return self.render_to_response(
            {"assignment": self.assignment, "decline_form": form}
        )

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        try:
            decline_assignment(
                assignment_id=self.assignment.pk,
                worker=self.get_worker_profile(),
                reason=form.cleaned_data["reason"],
                actor=self.request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "The assignment was declined and will be reassigned.")
        return redirect("operations:operations_worker_assignments")


# This view coordinates the worker profile view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerProfileView(WorkerRequiredMixin, FormView):
    template_name = "operations/worker_profile.html"
    form_class = WorkerProfileForm
    success_url = reverse_lazy("operations:operations_worker_profile")

    # This helper retrieves form kwargs for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_worker_profile()
        return kwargs

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Your worker profile was updated.")
        return super().form_valid(form)


# This view coordinates the worker availability view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerAvailabilityView(WorkerRequiredMixin, FormView):
    template_name = "operations/availability.html"
    form_class = WorkerAvailabilityForm
    success_url = reverse_lazy("operations:operations_worker_availability")

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        availability = form.save(commit=False)
        availability.worker = self.get_worker_profile()
        availability.full_clean()
        availability.save()
        messages.success(self.request, "Your availability was saved.")
        return super().form_valid(form)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["availability_periods"] = self.get_worker_profile().availability_periods.filter(
            end_at__gte=timezone.now()
        )
        return context


# This view coordinates the worker availability delete view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerAvailabilityDeleteView(WorkerRequiredMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, pk):
        period = get_object_or_404(
            WorkerAvailability,
            pk=pk,
            worker=self.get_worker_profile(),
            start_at__gte=timezone.now(),
        )
        period.delete()
        messages.success(request, "The availability period was removed.")
        return redirect("operations:operations_worker_availability")


# This view coordinates the worker schedule view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class WorkerScheduleView(WorkerRequiredMixin, TemplateView):
    template_name = "operations/worker_schedule.html"

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker = self.get_worker_profile()
        context["worker"] = worker
        context["assignments"] = worker.assignments.filter(
            status=PartyAssignment.Status.ACCEPTED,
            party_build__event_date__gte=timezone.localdate(),
        ).select_related("party_build__package")
        return context


# This view coordinates the legacy owner booking assignment redirect view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class LegacyOwnerBookingAssignmentRedirectView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Translate the old integer booking URL to the canonical UUID route."""

    raise_exception = True

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_func(self):
        return can_access_full_management(self.request.user)

    # This request method displays the current page and its permitted records.
    def get(self, request, booking_id):
        booking = get_object_or_404(PartyBuild, pk=booking_id)
        return redirect(
            "management:management_booking_assign",
            public_id=booking.public_id,
            permanent=True,
        )
