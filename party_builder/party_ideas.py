# This file prepares the searchable Party Ideas catalogue used before a customer enters the
# builder.
# It validates filters and sorting, combines package and experience results, and prepares
# recommendation information without trusting raw query-string values.
# The resulting records are still governed by the active and public catalogue rules.

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Avg, Count, F, Prefetch, Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from .analytics import recommend_addons
from .forms import PartyIdeasFilterForm
from .models import AddonExperience, Category, PartyBuild, PartyPackage
from .services import add_addon_to_session, resolve_active_package, select_package


VISIBLE_CATEGORY_FILTER = Q(parent__isnull=True) | Q(parent__is_active=True)
PUBLIC_PACKAGE_CATEGORY_CONTENT = Q(packages__is_active=True) | Q(
    children__is_active=True, children__packages__is_active=True
)
PUBLIC_ADDON_CATEGORY_CONTENT = Q(addons__is_active=True) | Q(
    children__is_active=True, children__addons__is_active=True
)


# This helper returns only public categories that lead to at least one active package or
# experience. Empty catalogue headings are hidden so customers are not offered routes or filters
# that can never show a result.
def visible_categories():
    """Return non-empty categories customers may browse, with safe parent details."""

    return (
        Category.objects.filter(is_active=True)
        .filter(VISIBLE_CATEGORY_FILTER)
        .filter(PUBLIC_PACKAGE_CATEGORY_CONTENT | PUBLIC_ADDON_CATEGORY_CONTENT)
        .select_related("parent")
        .distinct()
        .order_by("display_order", "name")
    )


# This helper supplies the builder with categories that contain active optional experiences. It
# excludes package-only and empty categories while retaining broader parent categories whose
# experiences are organised in subcategories.
def visible_addon_categories():
    """Return non-empty experience categories for the builder's filter buttons."""

    return (
        Category.objects.filter(is_active=True)
        .filter(VISIBLE_CATEGORY_FILTER)
        .filter(PUBLIC_ADDON_CATEGORY_CONTENT)
        .select_related("parent")
        .distinct()
        .order_by("display_order", "name")
    )


# This function handles public package queryset as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def public_package_queryset():
    """Return active packages with one query-friendly public rating summary."""

    completed_reviews = Q(
        builds__status=PartyBuild.Status.COMPLETED,
        builds__review__isnull=False,
        builds__customer_id=F("builds__review__reviewer_id"),
    )
    return (
        PartyPackage.objects.filter(is_active=True, category__is_active=True)
        .filter(Q(category__parent__isnull=True) | Q(category__parent__is_active=True))
        .select_related("category", "category__parent")
        .annotate(
            catalogue_price=F("base_price"),
            rating_count=Count(
                "builds__review", filter=completed_reviews, distinct=True
            ),
            average_rating=Avg(
                "builds__review__package_score", filter=completed_reviews
            ),
        )
    )


# This function handles public addon queryset as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def public_addon_queryset():
    """Return active experiences with verified completed-party rating totals."""

    completed_ratings = Q(
        build_items__build__status=PartyBuild.Status.COMPLETED,
        build_items__build_id=F("build_items__ratings__review__booking_id"),
        build_items__ratings__review__booking__status=PartyBuild.Status.COMPLETED,
        build_items__ratings__review__reviewer_id=F(
            "build_items__ratings__review__booking__customer_id"
        ),
    )
    return (
        AddonExperience.objects.filter(is_active=True, category__is_active=True)
        .filter(Q(category__parent__isnull=True) | Q(category__parent__is_active=True))
        .select_related("category", "category__parent")
        .annotate(
            catalogue_price=F("price"),
            rating_count=Count(
                "build_items__ratings", filter=completed_ratings, distinct=True
            ),
            average_rating=Avg(
                "build_items__ratings__score", filter=completed_ratings
            ),
        )
    )


# This function handles duration filter as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _duration_filter(value: str) -> Q:
    if value == "short":
        return Q(duration_minutes__lte=30)
    if value == "medium":
        return Q(duration_minutes__gt=30, duration_minutes__lte=60)
    if value == "long":
        return Q(duration_minutes__gt=60)
    return Q()


# This helper gathers the selected category and every active subcategory beneath it. Walking the
# hierarchy means a broad category continues to include its organised experiences even if Owners
# add another level later.
def _category_ids(category: Category | None) -> list[int]:
    if category is None:
        return []
    category_ids = [category.pk]
    pending_parent_ids = [category.pk]
    while pending_parent_ids:
        child_ids = list(
            Category.objects.filter(
                is_active=True, parent_id__in=pending_parent_ids
            ).values_list("pk", flat=True)
        )
        category_ids.extend(child_ids)
        pending_parent_ids = child_ids
    return category_ids


# This helper identifies which catalogue tabs are meaningful inside one category. Package-only
# categories no longer offer an Experiences tab, and experience-only categories do not offer a
# package tab that would always be empty.
def _available_idea_types(category: Category | None) -> tuple[str, ...]:
    if category is None:
        return ("all", "package", "experience")
    category_ids = _category_ids(category)
    has_packages = public_package_queryset().filter(category_id__in=category_ids).exists()
    has_experiences = public_addon_queryset().filter(category_id__in=category_ids).exists()
    if has_packages and has_experiences:
        return ("all", "package", "experience")
    if has_packages:
        return ("package",)
    if has_experiences:
        return ("experience",)
    return ()


# This function handles normalise card as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _normalise_card(item, kind: str) -> dict:
    """Give package and experience templates one small, shared card shape."""

    return {
        "kind": kind,
        "object": item,
        "name": item.name,
        "description": item.short_description,
        "price": item.catalogue_price,
        "duration_minutes": item.duration_minutes,
        "category": item.category,
        "average_rating": item.average_rating,
        "rating_count": item.rating_count,
        "display_order": item.display_order,
        "is_featured": kind == "experience" and item.is_featured,
        "capacity": item.included_guest_count if kind == "package" else None,
    }


# This function handles name sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _name_sort_key(card: dict) -> tuple:
    return card["name"].casefold(), card["kind"]


# This function handles price ascending sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _price_ascending_sort_key(card: dict) -> tuple:
    return card["price"], card["name"].casefold()


# This function handles price descending sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _price_descending_sort_key(card: dict) -> tuple:
    return -card["price"], card["name"].casefold()


# This function handles capacity ascending sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _capacity_ascending_sort_key(card: dict) -> tuple:
    capacity = card["capacity"] if card["capacity"] is not None else 10_000
    return capacity, card["name"].casefold()


# This function handles capacity descending sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _capacity_descending_sort_key(card: dict) -> tuple:
    capacity = card["capacity"] if card["capacity"] is not None else -1
    return -capacity, card["name"].casefold()


# This function handles rating sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _rating_sort_key(card: dict) -> tuple:
    return (
        -float(card["average_rating"] or 0),
        -card["rating_count"],
        card["name"].casefold(),
    )


# This function handles review count sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _review_count_sort_key(card: dict) -> tuple:
    return (
        -card["rating_count"],
        -float(card["average_rating"] or 0),
        card["name"].casefold(),
    )


# This function handles recommended sort key as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _recommended_sort_key(card: dict) -> tuple:
    return (
        0 if card["kind"] == "package" else 1,
        card["display_order"],
        card["name"].casefold(),
    )


# This function handles sort cards as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _sort_cards(cards: list[dict], ordering: str) -> None:
    sort_keys = {
        "name": _name_sort_key,
        "price_asc": _price_ascending_sort_key,
        "price_desc": _price_descending_sort_key,
        "capacity_asc": _capacity_ascending_sort_key,
        "capacity_desc": _capacity_descending_sort_key,
        "rating": _rating_sort_key,
        "reviews": _review_count_sort_key,
    }
    cards.sort(key=sort_keys.get(ordering, _recommended_sort_key))


# This function handles query string as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _query_string(querydict, **changes) -> str:
    values = querydict.copy()
    values.pop("page", None)
    for key, value in changes.items():
        if value in (None, ""):
            values.pop(key, None)
        else:
            values[key] = value
    return urlencode(values, doseq=True)


# This view coordinates the party ideas list view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyIdeasListView(TemplateView):
    """Search, filter and paginate public packages and experiences together."""

    template_name = "party_builder/party_ideas/list.html"
    forced_category: Category | None = None

    # This helper retrieves forced category for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_forced_category(self):
        return self.forced_category

    # This method validates filters after aligning them with the current category. A category page
    # automatically keeps the only meaningful idea type, so stale or manually edited URLs cannot
    # recreate an impossible package/experience combination.
    def _validated_filters(self):
        data = self.request.GET.copy()
        category = self.get_forced_category()
        allowed_types = _available_idea_types(category)
        if category:
            data["category"] = category.slug
            requested_type = data.get("type") or "all"
            if requested_type not in allowed_types and allowed_types:
                data["type"] = "all" if "all" in allowed_types else allowed_types[0]
        form = PartyIdeasFilterForm(
            data or None,
            idea_type=data.get("type") or "all",
            allowed_types=allowed_types,
        )
        if form.is_valid():
            return form, form.cleaned_data
        # Invalid URL values stay visible with field errors but cannot reach ORM
        # ordering or numeric comparisons.
        return form, {
            "q": "",
            "type": "all",
            "min_price": None,
            "max_price": None,
            "category": category,
            "capacity": "",
            "duration": "",
            "min_rating": "",
            "featured": False,
            "sort": "recommended",
        }

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form, filters = self._validated_filters()
        packages = public_package_queryset()
        addons = public_addon_queryset()

        search = filters.get("q") or ""
        if search:
            packages = packages.filter(
                Q(name__icontains=search)
                | Q(short_description__icontains=search)
                | Q(included_experiences__icontains=search)
                | Q(slug__icontains=search)
                | Q(category__name__icontains=search)
                | Q(category__parent__name__icontains=search)
            )
            addons = addons.filter(
                Q(name__icontains=search)
                | Q(short_description__icontains=search)
                | Q(slug__icontains=search)
                | Q(category__name__icontains=search)
                | Q(category__parent__name__icontains=search)
            )

        category = filters.get("category")
        category_ids = _category_ids(category)
        if category_ids:
            packages = packages.filter(category_id__in=category_ids)
            addons = addons.filter(category_id__in=category_ids)

        duration_query = _duration_filter(filters.get("duration") or "")
        packages = packages.filter(duration_query)
        addons = addons.filter(duration_query)

        minimum = filters.get("min_price")
        maximum = filters.get("max_price")
        if minimum is not None:
            packages = packages.filter(catalogue_price__gte=minimum)
            addons = addons.filter(catalogue_price__gte=minimum)
        if maximum is not None:
            packages = packages.filter(catalogue_price__lte=maximum)
            addons = addons.filter(catalogue_price__lte=maximum)

        capacity = filters.get("capacity")
        if capacity:
            packages = packages.filter(included_guest_count__gte=int(capacity))

        minimum_rating = filters.get("min_rating")
        if minimum_rating:
            threshold = Decimal(minimum_rating)
            packages = packages.filter(average_rating__gte=threshold)
            addons = addons.filter(average_rating__gte=threshold)

        idea_type = filters.get("type") or "all"
        include_packages = idea_type in {"all", "package"}
        include_addons = idea_type in {"all", "experience"}
        if filters.get("featured"):
            include_packages = False
            addons = addons.filter(is_featured=True)

        cards: list[dict] = []
        if include_packages:
            cards.extend(_normalise_card(item, "package") for item in packages.distinct())
        if include_addons:
            cards.extend(_normalise_card(item, "experience") for item in addons.distinct())
        _sort_cards(cards, filters.get("sort") or "recommended")

        paginator = Paginator(cards, 12)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        base_query = _query_string(self.request.GET)

        main_categories = list(
            visible_categories()
            .filter(parent__isnull=True)
            .prefetch_related(
                Prefetch(
                    "children",
                    queryset=visible_categories().order_by("display_order", "name"),
                    to_attr="active_children",
                )
            )
        )
        active_filters = []
        labels = {
            "q": "Search",
            "min_price": "Minimum price",
            "max_price": "Maximum price",
            "capacity": "Minimum capacity",
            "duration": "Duration",
            "min_rating": "Rating",
            "featured": "Featured",
        }
        for key, label in labels.items():
            value = filters.get(key)
            if value:
                active_filters.append(
                    {
                        "label": f"{label}: {value if value is not True else 'yes'}",
                        "remove_query": _query_string(self.request.GET, **{key: None}),
                    }
                )
        if category and not self.get_forced_category():
            active_filters.append(
                {
                    "label": f"Category: {category}",
                    "remove_query": _query_string(self.request.GET, category=None),
                }
            )

        current_category = self.get_forced_category()
        current_category_children = (
            list(
                visible_categories().filter(parent=current_category).order_by(
                    "display_order", "name"
                )
            )
            if current_category and current_category.parent_id is None
            else []
        )
        available_type_values = _available_idea_types(current_category)
        selected_category_types = _available_idea_types(category) if category else ()

        # A type tab removes a selected category when that category cannot contain the requested
        # kind of idea. This lets customers move from packages to experiences without landing on
        # a logically empty combination.
        type_tabs = []
        for value, label in PartyIdeasFilterForm.TYPE_CHOICES:
            if value not in available_type_values:
                continue
            query_changes = {"type": value}
            if category and value not in selected_category_types:
                query_changes["category"] = None
            type_tabs.append(
                {
                    "value": value,
                    "label": label,
                    "translation_key": {
                        "all": "partyIdeas.all",
                        "package": "partyIdeas.startingPackages",
                        "experience": "partyIdeas.experiences",
                    }[value],
                    "active": idea_type == value,
                    "query": _query_string(self.request.GET, **query_changes),
                }
            )

        context.update(
            {
                "filter_form": form,
                "filters": filters,
                "page_obj": page_obj,
                "paginator": paginator,
                "result_count": paginator.count,
                "base_query": base_query,
                "main_categories": main_categories,
                "active_filters": active_filters,
                "current_category": current_category,
                "current_category_children": current_category_children,
                "type_tabs": type_tabs,
            }
        )
        return context


# This view coordinates the party ideas category view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyIdeasCategoryView(PartyIdeasListView):
    """Reuse the catalogue results while fixing the scope to one category."""

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.forced_category = get_object_or_404(
            visible_categories(), slug=kwargs["slug"]
        )
        return super().dispatch(request, *args, **kwargs)


# This view coordinates the party package detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyPackageDetailView(DetailView):
    """Present an active package as a flexible starting point."""

    template_name = "party_builder/party_ideas/package_detail.html"
    context_object_name = "package"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return public_package_queryset()

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recommendations"] = recommend_addons(
            selected_ids=[], package=self.object
        )
        return context


# This view coordinates the party addon detail view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class PartyAddonDetailView(DetailView):
    """Show one active experience and related ideas without private feedback."""

    template_name = "party_builder/party_ideas/addon_detail.html"
    context_object_name = "addon"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return public_addon_queryset()

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        package = resolve_active_package(self.request.session)
        if package is None:
            recommendations = []
        else:
            recommendations = recommend_addons(
                selected_ids=[self.object.pk], package=package
            )
        context.update({"recommendations": recommendations, "current_package": package})
        return context


# This view coordinates the start package view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class StartPackageView(View):
    """Put an active package into the builder through a protected POST action."""

    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, *args, **kwargs):
        package = get_object_or_404(
            public_package_queryset(), slug=kwargs["slug"]
        )
        select_package(request.session, package)
        messages.success(
            request,
            f"{package.name} is now your package. Add any experiences you would like.",
        )
        return redirect("party_builder:party_builder_package_options")


# This view coordinates the add addon view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class AddAddonView(View):
    """Add an active experience to the same session cart used at checkout."""

    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
    def post(self, request, *args, **kwargs):
        addon = get_object_or_404(
            public_addon_queryset(), slug=kwargs["slug"]
        )
        add_addon_to_session(request.session, addon)
        messages.success(request, f"{addon.name} was added to your party choices.")
        builder_url = reverse("party_builder:party_builder_package_options")
        return redirect(f"{builder_url}#addon-{addon.pk}")
