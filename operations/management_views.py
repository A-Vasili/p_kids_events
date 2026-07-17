# This file coordinates the custom management pages used by Popadoo Administrators, Owners, and
# specifically delegated workers.
# Each view limits records and actions to the visitor’s current privileges before presenting
# catalogue, booking, user, analytics, audit, or message information.
# Business changes are handed to protected services so direct URLs cannot bypass the same
# safeguards.

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import CharField, Count, Prefetch, Q
from django.db.models.functions import Cast
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from accounts.models import WorkerProfile
from accounts.permissions import (
    OWNER_GROUP,
    WORKER_GROUP,
    can_access_full_management,
    can_create_owner,
    can_respond_to_customer_chat,
    can_manage_pricing,
    is_administrator,
)
from party_builder.analytics import analytics_report, resolve_period
from communications.services import unread_chat_count
from party_builder.models import AddonExperience, Category, GuestPriceTier, PartyBuild, PartyPackage

from .forms import (
    ManualAssignmentForm,
    ActionConfirmationForm,
    AddonForm,
    BookingStatusForm,
    CategoryForm,
    ManagedWorkerForm,
    OwnerCreationForm,
    OwnerWorkerCreationForm,
    ManualReviewForm,
    PackageForm,
)
from .models import AuditEvent, PartyAssignment, WorkerAvailability
from .services.assignment import assign_manually
from .services.audit import model_snapshot, record_audit
from .services.bookings import (
    booking_completion_block_reason,
    can_mark_booking_completed,
    change_booking_status,
    mark_booking_completed,
    send_to_manual_review,
)
from .services.catalogue import (
    remove_addon,
    remove_category,
    remove_package,
    save_catalogue_form,
)
from .services.scheduling import find_schedule_conflicts, get_event_window, worker_is_available
from .services.users import (
    customer_delete_blockers,
    delete_unused_customer,
    demote_worker,
    ensure_manager_can_view,
    grant_chat_responder_access,
    grant_pricing_management,
    is_customer_account,
    is_owner_account,
    is_worker_account,
    revoke_chat_responder_access,
    revoke_pricing_management,
    set_account_banned,
)

User = get_user_model()


# This class groups the information and behaviour needed for management context mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class ManagementContextMixin:
    """Supply page title, active navigation, breadcrumbs, and filter links."""

    page_title = "Management"
    active_section = "dashboard"
    breadcrumbs: tuple[tuple[str, str | None], ...] = ()

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.copy()
        query.pop("page", None)
        resolved_breadcrumbs = []
        for label, target in self.breadcrumbs:
            if target and not target.startswith("/"):
                target = reverse(target)
            resolved_breadcrumbs.append((label, target))
        context.update(
            {
                "management_page_title": self.page_title,
                "management_active_section": self.active_section,
                "management_breadcrumbs": tuple(resolved_breadcrumbs),
                "pagination_query": query.urlencode(),
            }
        )
        return context


# This class groups the information and behaviour needed for full management access mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class FullManagementAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Permit Administrators and Owners; authenticated failures receive HTTP 403."""

    raise_exception = True

    # This method handles handle no permission for the surrounding full management access mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_func(self):
        return can_access_full_management(self.request.user)


# This class groups the information and behaviour needed for catalogue management mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class CatalogueManagementMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Permit owners and workers who were explicitly delegated pricing access."""

    raise_exception = True

    # This method handles handle no permission for the surrounding catalogue management mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_func(self):
        return can_manage_pricing(self.request.user)


# This view coordinates the management dashboard view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class ManagementDashboardView(FullManagementAccessMixin, ManagementContextMixin, TemplateView):
    template_name = "operations/management/dashboard.html"
    page_title = "Management dashboard"
    active_section = "dashboard"

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        # Delegated workers land in the section they are actually allowed to use
        # instead of seeing a forbidden dashboard after selecting Management.
        if (
            request.user.is_authenticated
            and not can_access_full_management(request.user)
            and can_respond_to_customer_chat(request.user)
            and not can_manage_pricing(request.user)
        ):
            return redirect("communications:management_inbox")
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        week_end = today + timedelta(days=7)
        attention = PartyBuild.objects.filter(
            Q(assignment_state__in=(PartyBuild.AssignmentState.UNASSIGNED, PartyBuild.AssignmentState.MANUAL_REVIEW))
            | Q(status=PartyBuild.Status.SUBMITTED)
        ).select_related("package").order_by("event_date")
        upcoming = PartyBuild.objects.filter(
            event_date__gte=today,
            event_date__lte=week_end,
        ).select_related("package").prefetch_related(
            Prefetch(
                "assignments",
                queryset=PartyAssignment.objects.filter(status=PartyAssignment.Status.ACCEPTED).select_related("worker__user"),
                to_attr="accepted_assignments_for_dashboard",
            )
        ).order_by("event_date", "event_time")
        context.update(
            {
                "stats": {
                    "active_packages": PartyPackage.objects.filter(is_active=True).count(),
                    "active_addons": AddonExperience.objects.filter(is_active=True).count(),
                    "active_categories": Category.objects.filter(is_active=True).count(),
                    "upcoming_week": PartyBuild.objects.filter(event_date__gte=today, event_date__lte=week_end).count(),
                    "unassigned": PartyBuild.objects.filter(assignment_state=PartyBuild.AssignmentState.UNASSIGNED).count(),
                    "manual_review": PartyBuild.objects.filter(assignment_state=PartyBuild.AssignmentState.MANUAL_REVIEW).count(),
                    "active_workers": WorkerProfile.objects.filter(is_active_worker=True, user__is_active=True).count(),
                    "pending_offers": PartyAssignment.objects.filter(status=PartyAssignment.Status.PENDING).count(),
                    "unread_customer_chats": unread_chat_count(self.request.user),
                },
                "attention_bookings": attention[:8],
                "upcoming_bookings": upcoming[:8],
                "recent_catalogue_events": AuditEvent.objects.filter(
                    Q(event_type__contains="package")
                    | Q(event_type__contains="addon")
                    | Q(event_type__contains="category")
                    | Q(event_type__contains="tier")
                    | Q(event_type="catalogue_image_changed")
                ).select_related("actor")[:8],
                "recent_audit_events": AuditEvent.objects.select_related("actor")[:8],
            }
        )
        return context


# This view coordinates the catalogue index view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CatalogueIndexView(CatalogueManagementMixin, ManagementContextMixin, TemplateView):
    template_name = "operations/management/catalogue/index.html"
    page_title = "Catalogue"
    active_section = "catalogue"
    breadcrumbs = (("Catalogue", None),)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "package_count": PartyPackage.objects.count(),
                "tier_count": GuestPriceTier.objects.count(),
                "addon_count": AddonExperience.objects.count(),
                "category_count": Category.objects.count(),
            }
        )
        return context


# This view coordinates the category list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CategoryListView(CatalogueManagementMixin, ManagementContextMixin, ListView):
    template_name = "operations/management/categories/list.html"
    context_object_name = "categories"
    paginate_by = 20
    page_title = "Categories"
    active_section = "categories"
    breadcrumbs = (("Categories", None),)

    ORDERING = {
        "order": ("display_order", "name"),
        "name": ("name",),
        "-name": ("-name",),
        "newest": ("-created_at",),
    }

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        queryset = Category.objects.select_related("parent").annotate(
            package_count=Count("packages", distinct=True),
            addon_count=Count("addons", distinct=True),
        )
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        kind = self.request.GET.get("kind", "")
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(slug__icontains=query) | Q(description__icontains=query))
        if status in {"active", "inactive"}:
            queryset = queryset.filter(is_active=(status == "active"))
        if kind == "main":
            queryset = queryset.filter(parent__isnull=True)
        elif kind == "sub":
            queryset = queryset.filter(parent__isnull=False)
        return queryset.order_by(*self.ORDERING.get(self.request.GET.get("ordering", "order"), self.ORDERING["order"]))


# This view coordinates the category detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CategoryDetailView(CatalogueManagementMixin, ManagementContextMixin, DetailView):
    model = Category
    template_name = "operations/management/categories/detail.html"
    context_object_name = "category"
    page_title = "Category details"
    active_section = "categories"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return Category.objects.select_related("parent").prefetch_related("children", "packages", "addons")

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["management_breadcrumbs"] = (("Categories", reverse("management:management_category_list")), (self.object.name, None))
        return context


# This view coordinates the catalogue form view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CatalogueFormView(CatalogueManagementMixin, ManagementContextMixin, FormView):
    """Reusable create/edit workflow for catalogue records."""

    model = None
    success_name = ""
    object_label = "record"
    template_name = "operations/management/catalogue/form.html"
    object = None

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        if pk:
            self.object = get_object_or_404(self.model, pk=pk)
        return super().dispatch(request, *args, **kwargs)

    # This helper retrieves form kwargs for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object
        kwargs["files"] = self.request.FILES or None
        return kwargs

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object": self.object,
                "object_label": self.object_label,
                "is_create": self.object is None,
                "cancel_url": reverse(self.success_name),
            }
        )
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        try:
            saved = save_catalogue_form(form, actor=self.request.user)
        except ValidationError as error:
            # A service-level rule can involve several records, so it is shown
            # as a clear form-wide error while preserving every submitted value.
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, f"{saved} was saved successfully.")
        return redirect(self.success_name)


# This view coordinates the category create view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CategoryCreateView(CatalogueFormView):
    model = Category
    form_class = CategoryForm
    success_name = "management:management_category_list"
    object_label = "category"
    page_title = "Create category"
    active_section = "categories"
    breadcrumbs = (("Categories", "management:management_category_list"), ("Create", None))


# This view coordinates the category update view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CategoryUpdateView(CategoryCreateView):
    page_title = "Edit category"


# This view coordinates the catalogue remove view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CatalogueRemoveView(CatalogueManagementMixin, ManagementContextMixin, FormView):
    form_class = ActionConfirmationForm
    template_name = "operations/management/confirm_action.html"
    model = None
    remove_service = None
    success_name = ""
    object_label = "record"
    object = None

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(self.model, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "target": self.object,
                "target_name": str(self.object),
                "eyebrow": "Protected catalogue action",
                "will_archive": self.will_archive(),
                "usage_summary": self.usage_summary(),
                "action_label": ("Archive" if self.will_archive() else "Delete") + f" {self.object_label}",
                "title": ("Archive" if self.will_archive() else "Delete") + f" {self.object_label} “{self.object}”?",
                "consequence": (
                    "This record is referenced by existing catalogue or booking data. It will be deactivated instead of being destroyed, so historical bookings remain accurate."
                    if self.will_archive()
                    else "This record is unused and can be permanently deleted. This action cannot be undone."
                ),
                "cancel_url": reverse(self.success_name),
            }
        )
        return context

    # This method handles will archive for the surrounding catalogue remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def will_archive(self) -> bool:
        return False

    # This method handles usage summary for the surrounding catalogue remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def usage_summary(self) -> str:
        return ""

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        try:
            result = self.remove_service(self.object, actor=self.request.user)
        except ValidationError as error:
            # Deleting the last default package/tier would break checkout. Keep
            # the confirmation page open and explain the safe next step.
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, result.message)
        return redirect(self.success_name)


# This view coordinates the category remove view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CategoryRemoveView(CatalogueRemoveView):
    model = Category
    remove_service = staticmethod(remove_category)
    success_name = "management:management_category_list"
    object_label = "category"
    page_title = "Delete or deactivate category"
    active_section = "categories"

    # This method handles will archive for the surrounding category remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def will_archive(self):
        return self.object.packages.exists() or self.object.addons.exists() or self.object.children.exists()

    # This method handles usage summary for the surrounding category remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def usage_summary(self):
        parts = []
        if self.object.packages.exists():
            parts.append(f"{self.object.packages.count()} package(s)")
        if self.object.addons.exists():
            parts.append(f"{self.object.addons.count()} add-on(s)")
        if self.object.children.exists():
            parts.append(f"{self.object.children.count()} subcategory record(s)")
        return ", ".join(parts)


# This view coordinates the package list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PackageListView(CatalogueManagementMixin, ManagementContextMixin, ListView):
    template_name = "operations/management/packages/list.html"
    context_object_name = "packages"
    paginate_by = 20
    page_title = "Packages"
    active_section = "catalogue"
    breadcrumbs = (("Catalogue", "management:management_catalogue"), ("Packages", None))

    ORDERING = {
        "order": ("display_order", "name"),
        "name": ("name",),
        "-name": ("-name",),
        "price": ("base_price", "name"),
        "-price": ("-base_price", "name"),
    }

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        queryset = PartyPackage.objects.select_related("category")
        query = self.request.GET.get("q", "").strip()
        category = self.request.GET.get("category", "")
        status = self.request.GET.get("status", "")
        default = self.request.GET.get("default", "")
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(slug__icontains=query) | Q(short_description__icontains=query))
        if category.isdigit():
            queryset = queryset.filter(category_id=category)
        if status in {"active", "inactive"}:
            queryset = queryset.filter(is_active=(status == "active"))
        if default in {"yes", "no"}:
            queryset = queryset.filter(is_default=(default == "yes"))
        return queryset.order_by(*self.ORDERING.get(self.request.GET.get("ordering", "order"), self.ORDERING["order"]))

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category_options"] = Category.objects.order_by("display_order", "name")
        return context


# This view coordinates the package detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PackageDetailView(CatalogueManagementMixin, ManagementContextMixin, DetailView):
    model = PartyPackage
    template_name = "operations/management/packages/detail.html"
    context_object_name = "package"
    page_title = "Package details"
    active_section = "catalogue"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return PartyPackage.objects.select_related("category").prefetch_related("guest_price_tiers")

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["management_breadcrumbs"] = (("Catalogue", reverse("management:management_catalogue")), ("Packages", reverse("management:management_package_list")), (self.object.name, None))
        return context


# This view coordinates the package create view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PackageCreateView(CatalogueFormView):
    model = PartyPackage
    form_class = PackageForm
    success_name = "management:management_package_list"
    object_label = "package"
    page_title = "Create package"
    active_section = "catalogue"


# This view coordinates the package update view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PackageUpdateView(PackageCreateView):
    page_title = "Edit package"


# This view coordinates the package remove view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PackageRemoveView(CatalogueRemoveView):
    model = PartyPackage
    remove_service = staticmethod(remove_package)
    success_name = "management:management_package_list"
    object_label = "package"
    page_title = "Delete or archive package"
    active_section = "catalogue"

    # This method handles will archive for the surrounding package remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def will_archive(self):
        return self.object.builds.exists() or self.object.guest_price_tiers.filter(builds__isnull=False).exists()

    # This method handles usage summary for the surrounding package remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def usage_summary(self):
        count = self.object.builds.count()
        return f"{count} historical booking(s)" if count else "Historical tier references"


# This view coordinates the legacy tier compatibility view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class LegacyTierCompatibilityView(CatalogueManagementMixin, View):
    """Keep old tier URLs safe while directing managers to fixed-price packages.

    Guest tiers still exist for historical bookings, but new catalogue changes
    belong on the package itself. Both GET and POST are therefore non-mutating.
    """

    http_method_names = ["get", "post"]

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.package = None
        package_id = kwargs.get("package_id")
        tier_id = kwargs.get("pk")
        if package_id:
            self.package = get_object_or_404(PartyPackage, pk=package_id)
        elif tier_id:
            tier = get_object_or_404(
                GuestPriceTier.objects.select_related("package"),
                pk=tier_id,
            )
            self.package = tier.package
        return super().dispatch(request, *args, **kwargs)

    # This method handles redirect for the surrounding legacy tier compatibility view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def _redirect(self):
        messages.info(
            self.request,
            "Guest-price tiers are read-only legacy records. Edit the package capacity and fixed price instead.",
        )
        if self.package is not None:
            return redirect(
                "management:management_package_detail",
                pk=self.package.pk,
            )
        return redirect("management:management_catalogue")

    # This request method displays the current page and its permitted records.
    def get(self, request, *args, **kwargs):
        return self._redirect()

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, *args, **kwargs):
        return self._redirect()


# This view coordinates the addon list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AddonListView(CatalogueManagementMixin, ManagementContextMixin, ListView):
    template_name = "operations/management/addons/list.html"
    context_object_name = "addons"
    paginate_by = 20
    page_title = "Add-ons"
    active_section = "catalogue"
    ORDERING = {
        "order": ("display_order", "name"),
        "name": ("name",),
        "-name": ("-name",),
        "price": ("price", "name"),
        "-price": ("-price", "name"),
    }

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        queryset = AddonExperience.objects.select_related("category")
        query = self.request.GET.get("q", "").strip()
        category = self.request.GET.get("category", "")
        status = self.request.GET.get("status", "")
        featured = self.request.GET.get("featured", "")
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(slug__icontains=query) | Q(short_description__icontains=query))
        if category.isdigit():
            queryset = queryset.filter(category_id=category)
        if status in {"active", "inactive"}:
            queryset = queryset.filter(is_active=(status == "active"))
        if featured in {"yes", "no"}:
            queryset = queryset.filter(is_featured=(featured == "yes"))
        return queryset.order_by(*self.ORDERING.get(self.request.GET.get("ordering", "order"), self.ORDERING["order"]))

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category_options"] = Category.objects.order_by("display_order", "name")
        return context


# This view coordinates the addon detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AddonDetailView(CatalogueManagementMixin, ManagementContextMixin, DetailView):
    model = AddonExperience
    template_name = "operations/management/addons/detail.html"
    context_object_name = "addon"
    page_title = "Add-on details"
    active_section = "catalogue"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return AddonExperience.objects.select_related("category")


# This view coordinates the addon create view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AddonCreateView(CatalogueFormView):
    model = AddonExperience
    form_class = AddonForm
    success_name = "management:management_addon_list"
    object_label = "add-on"
    page_title = "Create add-on"
    active_section = "catalogue"


# This view coordinates the addon update view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AddonUpdateView(AddonCreateView):
    page_title = "Edit add-on"


# This view coordinates the addon remove view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AddonRemoveView(CatalogueRemoveView):
    model = AddonExperience
    remove_service = staticmethod(remove_addon)
    success_name = "management:management_addon_list"
    object_label = "add-on"
    page_title = "Delete or archive add-on"
    active_section = "catalogue"

    # This method handles will archive for the surrounding addon remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def will_archive(self):
        return self.object.build_items.exists()

    # This method handles usage summary for the surrounding addon remove view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def usage_summary(self):
        count = self.object.build_items.count()
        return f"{count} historical booking add-on selection(s)" if count else ""


# This view coordinates the user list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class UserListView(FullManagementAccessMixin, ManagementContextMixin, ListView):
    template_name = "operations/management/users/list.html"
    context_object_name = "managed_users"
    paginate_by = 25
    page_title = "Users and roles"
    active_section = "users"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        # Administrator accounts are system identities and never enter custom
        # account-mutation workflows. Administrators may inspect Owners, while
        # an Owner sees only their own Owner record.
        base = User.objects.filter(is_superuser=False)
        if is_administrator(self.request.user):
            queryset = base
        else:
            queryset = base.exclude(groups__name=OWNER_GROUP) | base.filter(
                pk=self.request.user.pk
            )
        queryset = queryset.prefetch_related("groups").select_related(
            "customer_profile", "worker_profile"
        )
        query = self.request.GET.get("q", "").strip()
        role = self.request.GET.get("role", "")
        status = self.request.GET.get("status", "")
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
        if role == "owner":
            queryset = queryset.filter(groups__name=OWNER_GROUP)
        elif role == "worker":
            queryset = queryset.filter(groups__name=WORKER_GROUP)
        elif role == "customer":
            queryset = queryset.exclude(groups__name__in=(OWNER_GROUP, WORKER_GROUP))
        if status in {"active", "inactive"}:
            queryset = queryset.filter(is_active=(status == "active"))
        return queryset.distinct().order_by("last_name", "first_name", "username")


# This class groups the information and behaviour needed for protected user object mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class ProtectedUserObjectMixin:
    user_object = None

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.user_object = get_object_or_404(
            User.objects.select_related(
                "customer_profile", "worker_profile"
            ).prefetch_related("groups"),
            pk=kwargs["pk"],
        )
        try:
            ensure_manager_can_view(request.user, self.user_object)
        except PermissionDenied as error:
            # Protected accounts use 404 so their identifiers are not exposed to
            # users who are not allowed to inspect them.
            raise Http404 from error
        self.validate_user_object(request)
        return super().dispatch(request, *args, **kwargs)

    # This safeguard verifies user object before the surrounding workflow continues.
    # When the rule is not met, it stops the action with a controlled error rather than allowing
    # an inconsistent record.
    def validate_user_object(self, request):
        """Allow individual views to add role-specific object restrictions."""



# This view coordinates the user detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class UserDetailView(FullManagementAccessMixin, ProtectedUserObjectMixin, ManagementContextMixin, TemplateView):
    template_name = "operations/management/users/detail.html"
    page_title = "User details"
    active_section = "users"

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.user_object
        worker_profile = getattr(user, "worker_profile", None)
        customer = is_customer_account(user)
        delete_blockers = customer_delete_blockers(user) if customer else []
        worker = is_worker_account(user)
        owner = is_owner_account(user)
        administrator_actor = is_administrator(self.request.user)
        context.update(
            {
                "managed_user": user,
                "managed_user_is_customer": customer,
                "managed_user_is_worker": worker,
                "managed_user_is_owner": owner,
                "can_edit_worker": worker and not owner,
                "can_change_account_status": (
                    user.pk != self.request.user.pk
                    and not user.is_superuser
                    and (not owner or administrator_actor)
                ),
                "can_delete_customer": customer and not delete_blockers,
                "customer_delete_blockers": delete_blockers,
                "customer_bookings": user.party_bookings.select_related("package")[:10],
                "worker_assignments": worker_profile.assignments.select_related("party_build")[:10] if worker_profile else [],
                "worker_availability": worker_profile.availability_periods.all()[:10] if worker_profile else [],
                "recent_events": AuditEvent.objects.filter(
                    object_type="User", object_id=str(user.pk)
                ).select_related("actor")[:10],
            }
        )
        return context


# This view coordinates the user update view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class UserUpdateView(FullManagementAccessMixin, ProtectedUserObjectMixin, ManagementContextMixin, FormView):
    template_name = "operations/management/users/form.html"
    form_class = ManagedWorkerForm
    page_title = "Edit worker settings"
    active_section = "users"

    # This safeguard verifies user object before the surrounding workflow continues.
    # When the rule is not met, it stops the action with a controlled error rather than allowing
    # an inconsistent record.
    def validate_user_object(self, request):
        if not is_worker_account(self.user_object) or is_owner_account(self.user_object):
            raise PermissionDenied(
                "Customer and Owner profile information is read-only in management."
            )

    # This helper retrieves form kwargs for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.user_object.worker_profile
        return kwargs

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "managed_user": self.user_object,
                "form_eyebrow": "Worker operations",
                "form_title": f"Edit {self.user_object.get_full_name() or self.user_object.username}",
                "form_description": (
                    "Only staff scheduling and contact settings can be changed here. "
                    "Customer-supplied profile details remain under the account holder's control."
                ),
                "submit_label": "Save worker settings",
                "cancel_url": reverse(
                    "management:management_user_detail", args=[self.user_object.pk]
                ),
            }
        )
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        before = model_snapshot(
            self.user_object.worker_profile,
            ("display_name", "phone", "max_daily_parties", "notes_for_owner"),
        )
        worker = form.save()
        record_audit(
            actor=self.request.user,
            event_type="worker_settings_updated",
            target=self.user_object,
            summary=f"{self.request.user} updated worker settings for {self.user_object}.",
            before=before,
            after=model_snapshot(
                worker,
                ("display_name", "phone", "max_daily_parties", "notes_for_owner"),
            ),
        )
        messages.success(self.request, "The worker settings were updated.")
        return redirect("management:management_user_detail", pk=self.user_object.pk)


# This view coordinates the user create worker view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class UserCreateWorkerView(FullManagementAccessMixin, ManagementContextMixin, FormView):
    template_name = "operations/management/users/form.html"
    form_class = OwnerWorkerCreationForm
    page_title = "Create worker account"
    active_section = "users"

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_eyebrow": "Staff account",
                "form_title": "Create worker",
                "form_description": "The worker receives staff portal access but no Owner or Administrator privileges.",
                "submit_label": "Create worker",
                "cancel_url": reverse("management:management_user_list"),
            }
        )
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        user = form.save(actor=self.request.user)
        messages.success(self.request, f"Worker account {user.username} was created.")
        return redirect("management:management_user_detail", pk=user.pk)


# This view coordinates the user create owner view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class UserCreateOwnerView(LoginRequiredMixin, UserPassesTestMixin, ManagementContextMixin, FormView):
    """Create a protected Owner without granting system-administrator rights."""

    template_name = "operations/management/users/form.html"
    form_class = OwnerCreationForm
    page_title = "Create Owner account"
    active_section = "users"
    raise_exception = True

    # This method handles handle no permission for the surrounding user create owner view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
    def test_func(self):
        return can_create_owner(self.request.user)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "form_eyebrow": "Protected business account",
                "form_title": "Create Owner",
                "form_description": (
                    "Owners can run the business management panel but do not receive "
                    "Django staff or Administrator privileges."
                ),
                "submit_label": "Create Owner",
                "cancel_url": reverse("management:management_user_list"),
            }
        )
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        user = form.save(actor=self.request.user)
        messages.success(self.request, f"Owner account {user.username} was created.")
        return redirect("management:management_user_detail", pk=user.pk)


# This view coordinates the user action view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class UserActionView(FullManagementAccessMixin, ProtectedUserObjectMixin, ManagementContextMixin, FormView):
    template_name = "operations/management/confirm_action.html"
    form_class = ActionConfirmationForm
    page_title = "Confirm user action"
    active_section = "users"
    ACTION_LABELS = {
        "ban": "Ban account",
        "unban": "Unban account",
        "delete": "Delete unused account",
        "demote": "Remove worker access",
        "grant_pricing": "Grant pricing access",
        "revoke_pricing": "Revoke pricing access",
        "grant_chat": "Grant chat responder access",
        "revoke_chat": "Revoke chat responder access",
    }

    # This safeguard verifies user object before the surrounding workflow continues.
    # When the rule is not met, it stops the action with a controlled error rather than allowing
    # an inconsistent record.
    def validate_user_object(self, request):
        target = self.user_object
        if is_owner_account(target):
            if not is_administrator(request.user):
                raise PermissionDenied("Only an Administrator can change an Owner account.")
            if self.action not in {"ban", "unban"}:
                raise Http404
            return
        if is_customer_account(target) and self.action not in {"ban", "unban", "delete"}:
            raise Http404
        if is_worker_account(target) and self.action not in {
            "ban", "unban", "demote", "grant_pricing", "revoke_pricing",
            "grant_chat", "revoke_chat"
        }:
            raise Http404

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.action = kwargs["action"]
        if self.action not in self.ACTION_LABELS:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "target": self.user_object,
                "target_name": self.user_object.get_full_name() or self.user_object.username,
                "eyebrow": "Account security",
                "action_label": self.ACTION_LABELS[self.action],
                "title": f"{self.ACTION_LABELS[self.action]} for {self.user_object.get_full_name() or self.user_object.username}?",
                "consequence": self._consequence(),
                "confirmation_button_class": (
                    "danger" if self.action in {"ban", "delete"} else "safe"
                ),
                "cancel_url": reverse(
                    "management:management_user_detail", args=[self.user_object.pk]
                ),
            }
        )
        return context

    # This method handles consequence for the surrounding user action view.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def _consequence(self):
        return {
            "ban": "The account will be unable to sign in. Existing business history is preserved.",
            "unban": "The account will be able to sign in again.",
            "delete": (
                "The account is permanently removed only when it has no bookings, reviews, "
                "worker records, assignments, or audit actions."
            ),
            "demote": "Worker, pricing, and chat responder access will be removed; historical assignments remain.",
            "grant_pricing": "The worker will be able to manage catalogue and pricing records.",
            "revoke_pricing": "The worker keeps staff access but loses catalogue management access.",
            "grant_chat": "The worker will be able to read and reply to customer chats only.",
            "revoke_chat": "The worker keeps staff access but loses customer-chat access.",
        }[self.action]

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        target = self.user_object
        try:
            if self.action == "ban":
                set_account_banned(target=target, banned=True, actor=self.request.user)
            elif self.action == "unban":
                set_account_banned(target=target, banned=False, actor=self.request.user)
            elif self.action == "delete":
                delete_unused_customer(target=target, actor=self.request.user)
                messages.success(self.request, "The unused customer account was deleted.")
                return redirect("management:management_user_list")
            elif self.action == "demote":
                demote_worker(target, self.request.user)
            elif self.action == "grant_pricing":
                grant_pricing_management(target, self.request.user)
            elif self.action == "revoke_pricing":
                revoke_pricing_management(target, self.request.user)
            elif self.action == "grant_chat":
                grant_chat_responder_access(target, self.request.user)
            else:
                revoke_chat_responder_access(target, self.request.user)
        except (PermissionDenied, ValidationError) as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"{self.ACTION_LABELS[self.action]} completed for {target}.",
        )
        return redirect("management:management_user_detail", pk=target.pk)


# This view coordinates the booking list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class BookingListView(FullManagementAccessMixin, ManagementContextMixin, ListView):
    template_name = "operations/management/bookings/list.html"
    context_object_name = "bookings"
    paginate_by = 25
    page_title = "Bookings"
    active_section = "bookings"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        accepted = PartyAssignment.objects.filter(status=PartyAssignment.Status.ACCEPTED).select_related("worker__user")
        queryset = PartyBuild.objects.select_related("package", "guest_tier", "customer").prefetch_related(
            Prefetch("assignments", queryset=accepted, to_attr="accepted_assignments")
        ).annotate(public_id_text=Cast("public_id", output_field=CharField()))
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        assignment = self.request.GET.get("assignment", "")
        package = self.request.GET.get("package", "")
        worker = self.request.GET.get("worker", "")
        date_from = self.request.GET.get("date_from", "")
        date_to = self.request.GET.get("date_to", "")
        if query:
            queryset = queryset.filter(
                Q(contact_name__icontains=query)
                | Q(contact_email__icontains=query)
                | Q(public_id_text__icontains=query)
                | Q(event_address__icontains=query)
            )
        if status in PartyBuild.Status.values:
            queryset = queryset.filter(status=status)
        if assignment in PartyBuild.AssignmentState.values:
            queryset = queryset.filter(assignment_state=assignment)
        if package.isdigit():
            queryset = queryset.filter(package_id=package)
        if worker.isdigit():
            queryset = queryset.filter(assignments__worker_id=worker, assignments__status=PartyAssignment.Status.ACCEPTED)
        parsed_from = parse_date(date_from) if date_from else None
        parsed_to = parse_date(date_to) if date_to else None
        if parsed_from:
            queryset = queryset.filter(event_date__gte=parsed_from)
        if parsed_to:
            queryset = queryset.filter(event_date__lte=parsed_to)
        return queryset.distinct().order_by("event_date", "event_time", "-created_at")

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "package_options": PartyPackage.objects.order_by("name"),
                "worker_options": WorkerProfile.objects.filter(is_active_worker=True).select_related("user"),
                "booking_status_choices": PartyBuild.Status.choices,
                "assignment_state_choices": PartyBuild.AssignmentState.choices,
            }
        )
        return context


# This view coordinates the booking detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class BookingDetailView(FullManagementAccessMixin, ManagementContextMixin, DetailView):
    model = PartyBuild
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    template_name = "operations/management/bookings/detail.html"
    context_object_name = "booking"
    page_title = "Booking details"
    active_section = "bookings"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return PartyBuild.objects.select_related("package", "guest_tier", "customer").prefetch_related(
            "addon_items__addon",
            "assignments__worker__user",
            "review__addon_ratings__build_addon__addon",
        )

    # This step prepares the existing status and manual-review tools together with a clear,
    # server-checked completion action. The dedicated button is easier to understand, while the
    # shared service remains the final authority when it is submitted.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "status_form": BookingStatusForm(booking=self.object),
                "manual_review_form": ManualReviewForm(),
                "can_mark_party_done": can_mark_booking_completed(
                    booking=self.object,
                    actor=self.request.user,
                ),
                "completion_block_reason": booking_completion_block_reason(self.object),
                "audit_events": AuditEvent.objects.filter(object_type="PartyBuild", object_id=str(self.object.pk)).select_related("actor")[:15],
            }
        )
        return context


# This POST-only management action gives Administrators and Owners an obvious way to confirm that
# an eligible party took place. It uses the same trusted service as the worker portal so completion
# time, review access, and audit history stay consistent.
class BookingCompleteView(FullManagementAccessMixin, View):
    http_method_names = ["post"]

    # This request resolves the booking by its public identifier, applies the completion safeguards,
    # and returns to the detail page with a clear explanation instead of accepting a posted status.
    def post(self, request, public_id):
        booking = get_object_or_404(PartyBuild, public_id=public_id)
        try:
            mark_booking_completed(
                booking=booking,
                actor=request.user,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(
                request,
                "The party was marked as done. The customer can now leave a review.",
            )
        return redirect(
            "management:management_booking_detail",
            public_id=booking.public_id,
        )


# This view coordinates the booking status update view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class BookingStatusUpdateView(FullManagementAccessMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, public_id):
        booking = get_object_or_404(PartyBuild, public_id=public_id)
        form = BookingStatusForm(request.POST, booking=booking)
        if form.is_valid():
            try:
                change_booking_status(
                    booking=booking,
                    status=form.cleaned_data["status"],
                    note=form.cleaned_data.get("note", ""),
                    actor=request.user,
                )
                messages.success(request, "The booking status was updated.")
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
        else:
            messages.error(request, "The requested status change was not valid.")
        return redirect("management:management_booking_detail", public_id=booking.public_id)


# This view coordinates the booking manual review view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class BookingManualReviewView(FullManagementAccessMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, public_id):
        booking = get_object_or_404(PartyBuild, public_id=public_id)
        form = ManualReviewForm(request.POST)
        if form.is_valid():
            try:
                send_to_manual_review(
                    booking=booking,
                    actor=request.user,
                    reason=form.cleaned_data["reason"],
                )
                messages.success(request, "The booking now requires manual review.")
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
        else:
            messages.error(request, "Explain why the booking needs manual review.")
        return redirect("management:management_booking_detail", public_id=booking.public_id)


# This view coordinates the booking assign view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class BookingAssignView(FullManagementAccessMixin, ManagementContextMixin, FormView):
    template_name = "operations/management/bookings/assign.html"
    form_class = ManualAssignmentForm
    page_title = "Assign worker"
    active_section = "bookings"

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.booking = get_object_or_404(
            PartyBuild.objects.select_related("package").prefetch_related("addon_items__addon"),
            public_id=kwargs["public_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event_window = get_event_window(self.booking)
        worker_rows = []
        for worker in WorkerProfile.objects.filter(is_active_worker=True, user__is_active=True).select_related("user"):
            worker_rows.append(
                {
                    "worker": worker,
                    "available": worker_is_available(worker, *event_window) if event_window else False,
                    "conflicts": find_schedule_conflicts(worker, *event_window, exclude_build_id=self.booking.pk) if event_window else [],
                }
            )
        context.update({"booking": self.booking, "worker_rows": worker_rows})
        return context

    # This step applies the validated form through the trusted business workflow and then sends
    # the person to the appropriate success page.
    def form_valid(self, form):
        try:
            assign_manually(
                party_build=self.booking,
                worker=form.cleaned_data["worker"],
                owner=self.request.user,
                override_reason=form.cleaned_data.get("override_reason", ""),
                already_agreed=form.cleaned_data.get("already_agreed", False),
            )
        except ValidationError as error:
            form.add_error("override_reason", error)
            return self.form_invalid(form)
        messages.success(self.request, "The worker assignment was saved.")
        return redirect("management:management_booking_detail", public_id=self.booking.public_id)


# This view coordinates the schedule view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class ScheduleView(FullManagementAccessMixin, ManagementContextMixin, TemplateView):
    template_name = "operations/management/schedules.html"
    page_title = "Worker schedules"
    active_section = "schedules"

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requested_from = self.request.GET.get("date_from", "")
        requested_to = self.request.GET.get("date_to", "")
        parsed_from = parse_date(requested_from) or timezone.localdate()
        parsed_to = parse_date(requested_to) or (timezone.localdate() + timedelta(days=30))
        if parsed_to < parsed_from:
            parsed_to = parsed_from
        date_from = str(parsed_from)
        date_to = str(parsed_to)
        worker_id = self.request.GET.get("worker", "")
        assignments = PartyAssignment.objects.filter(
            status__in=(PartyAssignment.Status.PENDING, PartyAssignment.Status.ACCEPTED),
            party_build__event_date__gte=date_from,
            party_build__event_date__lte=date_to,
        ).select_related("worker__user", "party_build__package")
        availability = WorkerAvailability.objects.filter(
            end_at__date__gte=date_from,
            start_at__date__lte=date_to,
        ).select_related("worker__user")
        if worker_id.isdigit():
            assignments = assignments.filter(worker_id=worker_id)
            availability = availability.filter(worker_id=worker_id)
        context.update(
            {
                "assignments": assignments.order_by("party_build__event_date", "party_build__event_time"),
                "availability_periods": availability.order_by("start_at"),
                "workers": WorkerProfile.objects.filter(is_active_worker=True).select_related("user"),
                "date_from": date_from,
                "date_to": date_to,
            }
        )
        return context


# This view coordinates the audit list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AuditListView(FullManagementAccessMixin, ManagementContextMixin, ListView):
    template_name = "operations/management/audit/list.html"
    context_object_name = "events"
    paginate_by = 50
    page_title = "Audit history"
    active_section = "audit"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        queryset = AuditEvent.objects.select_related("actor")
        query = self.request.GET.get("q", "").strip()
        event_type = self.request.GET.get("event_type", "").strip()
        actor = self.request.GET.get("actor", "")
        date_from = self.request.GET.get("date_from", "")
        date_to = self.request.GET.get("date_to", "")
        if query:
            queryset = queryset.filter(Q(summary__icontains=query) | Q(object_type__icontains=query) | Q(object_id__icontains=query))
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if actor.isdigit():
            queryset = queryset.filter(actor_id=actor)
        parsed_from = parse_date(date_from) if date_from else None
        parsed_to = parse_date(date_to) if date_to else None
        if parsed_from:
            queryset = queryset.filter(created_at__date__gte=parsed_from)
        if parsed_to:
            queryset = queryset.filter(created_at__date__lte=parsed_to)
        return queryset.order_by("-created_at")

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_type_options"] = AuditEvent.objects.order_by("event_type").values_list("event_type", flat=True).distinct()
        context["actor_options"] = User.objects.filter(popadoo_audit_events__isnull=False).distinct().order_by("username")
        return context


# This view coordinates the analytics view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AnalyticsView(FullManagementAccessMixin, ManagementContextMixin, TemplateView):
    """Show completed-party usage, verified ratings, and common combinations."""

    template_name = "operations/management/analytics.html"
    page_title = "Analytics"
    active_section = "analytics"
    breadcrumbs = (("Analytics", None),)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period_key, days = resolve_period(self.request.GET.get("period"))
        context.update(
            {
                "period_key": period_key,
                "period_options": (
                    ("30", "Last 30 days"),
                    ("90", "Last 90 days"),
                    ("365", "Last 365 days"),
                    ("all", "All time"),
                ),
                **analytics_report(days=days),
            }
        )
        return context
