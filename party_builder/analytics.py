# This file turns stored business records into summary figures used by the management analytics
# screens.
# It keeps reporting calculations separate from page rendering and avoids exposing private review
# or customer details unnecessarily.

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from itertools import combinations
from typing import Iterable

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from .models import (
    AddonExperience,
    PartyBuild,
    PartyBuildAddon,
    PartyPackage,
    PartyReview,
)

REPORTING_PERIODS = {"30": 30, "90": 90, "365": 365, "all": None}
DEFAULT_REPORTING_PERIOD = "365"

# An experience is publicly available only when both its own category and any
# parent category are active. This shared filter prevents archived catalogue
# sections from returning through recommendations or popularity badges.
PUBLIC_ADDON_CATEGORY_FILTER = Q(category__is_active=True) & (
    Q(category__parent__isnull=True) | Q(category__parent__is_active=True)
)


# Return a validated reporting-period key and its number of days. This keeps the same selection or
# calculation rule available to every caller.
def resolve_period(value: str | None) -> tuple[str, int | None]:
    """Return a validated reporting-period key and its number of days."""

    key = value if value in REPORTING_PERIODS else DEFAULT_REPORTING_PERIOD
    return key, REPORTING_PERIODS[key]


# Compute period start for the surrounding analytics or service workflow. Centralizing the
# calculation keeps date, status, and filtering rules consistent across callers.
def _period_start(days: int | None):
    return None if days is None else timezone.localdate() - timedelta(days=days)


# Compute completed filter for the surrounding analytics or service workflow. Centralizing the
# calculation keeps date, status, and filtering rules consistent across callers.
def _completed_filter(prefix: str, days: int | None) -> Q:
    query = Q(**{f"{prefix}status": PartyBuild.Status.COMPLETED})
    start = _period_start(days)
    if start is not None:
        query &= Q(**{f"{prefix}event_date__gte": start})
    return query


# Return active add-on usage and verified rating statistics. The queryset applies the same
# visibility and activity restrictions for every caller.
def addon_popularity(*, days: int | None = 365) -> dict:
    """Return active add-on usage and verified rating statistics.

    Counts use distinct completed bookings. The most-popular badge requires at
    least three completed bookings and is chosen by usage, rating, then name.
    """

    build_filter = _completed_filter("build_items__build__", days)
    rating_filter = _completed_filter(
        "build_items__ratings__review__booking__", days
    ) & Q(
        build_items__build_id=F("build_items__ratings__review__booking_id"),
        build_items__ratings__review__reviewer_id=F(
            "build_items__ratings__review__booking__customer_id"
        ),
    )
    addons = list(
        AddonExperience.objects.filter(is_active=True)
        .filter(PUBLIC_ADDON_CATEGORY_FILTER)
        .select_related("category")
        .annotate(
            completed_booking_count=Count(
                "build_items__build",
                filter=build_filter,
                distinct=True,
            ),
            rating_count=Count(
                "build_items__ratings",
                filter=rating_filter,
                distinct=True,
            ),
            average_rating=Avg(
                "build_items__ratings__score",
                filter=rating_filter,
            ),
        )
    )
    total_query = PartyBuild.objects.filter(status=PartyBuild.Status.COMPLETED)
    start = _period_start(days)
    if start is not None:
        total_query = total_query.filter(event_date__gte=start)
    total_completed = total_query.count()

    addons.sort(
        key=lambda addon: (
            -addon.completed_booking_count,
            -(float(addon.average_rating) if addon.average_rating is not None else 0.0),
            addon.name.casefold(),
        )
    )

    most_popular_id = next(
        (
            addon.pk
            for addon in addons
            if addon.completed_booking_count >= 3
        ),
        None,
    )
    rows = []
    for position, addon in enumerate(addons, start=1):
        rows.append(
            {
                "addon": addon,
                "completed_booking_count": addon.completed_booking_count,
                "selection_percentage": (
                    Decimal(addon.completed_booking_count * 100) / Decimal(total_completed)
                    if total_completed
                    else Decimal("0")
                ),
                "rating_count": addon.rating_count,
                "average_rating": addon.average_rating,
                "position": position,
                "is_most_popular": addon.pk == most_popular_id,
            }
        )
    return {
        "total_completed": total_completed,
        "rows": rows,
        "by_id": {row["addon"].pk: row for row in rows},
        "most_popular_id": most_popular_id,
    }


# Return the completed addon sets result from PartyBuildAddon, applying the filters encoded here so
# every caller sees the same eligible records.
def _completed_addon_sets(*, days: int | None, package_id: int | None = None):
    queryset = PartyBuildAddon.objects.filter(
        build__status=PartyBuild.Status.COMPLETED,
        addon__is_active=True,
        addon__category__is_active=True,
    ).filter(
        Q(addon__category__parent__isnull=True)
        | Q(addon__category__parent__is_active=True)
    )
    start = _period_start(days)
    if start is not None:
        queryset = queryset.filter(build__event_date__gte=start)
    if package_id is not None:
        queryset = queryset.filter(build__package_id=package_id)

    booking_addons: dict[int, set[int]] = defaultdict(set)
    for build_id, addon_id in queryset.values_list("build_id", "addon_id"):
        booking_addons[build_id].add(addon_id)
    return booking_addons


# Return frequent completed-booking pairs with directional confidence. The queryset applies the same
# visibility and activity restrictions for every caller.
def common_addon_pairs(
    *,
    days: int | None = 365,
    limit: int = 20,
    popularity_by_id: dict | None = None,
) -> list[dict]:
    """Return frequent completed-booking pairs with directional confidence.

    For a displayed pair A → B, confidence is pair_count / bookings containing A.
    """

    booking_addons = _completed_addon_sets(days=days)
    base_counts: dict[int, int] = defaultdict(int)
    pair_counts: dict[tuple[int, int], int] = defaultdict(int)
    for addon_ids in booking_addons.values():
        for addon_id in addon_ids:
            base_counts[addon_id] += 1
        for first_id, second_id in combinations(sorted(addon_ids), 2):
            pair_counts[(first_id, second_id)] += 1

    addon_map = {
        addon.pk: addon
        for addon in AddonExperience.objects.filter(
            is_active=True,
            pk__in={item for pair in pair_counts for item in pair},
        ).filter(PUBLIC_ADDON_CATEGORY_FILTER).select_related("category")
    }
    popularity = popularity_by_id or addon_popularity(days=days)["by_id"]
    rows = []
    for (first_id, second_id), pair_count in pair_counts.items():
        first = addon_map.get(first_id)
        second = addon_map.get(second_id)
        if not first or not second:
            continue
        if pair_count < 2:
            continue
        confidence = (
            Decimal(pair_count) / Decimal(base_counts[first_id])
            if base_counts[first_id]
            else Decimal("0")
        )
        rows.append(
            {
                "addon_a": first,
                "addon_b": second,
                "pair_count": pair_count,
                "confidence": confidence,
                "confidence_percentage": confidence * Decimal("100"),
                "average_rating": max(
                    popularity.get(first_id, {}).get("average_rating") or 0,
                    popularity.get(second_id, {}).get("average_rating") or 0,
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["pair_count"],
            -float(row["confidence"]),
            -float(row["average_rating"] or 0),
            row["addon_a"].name.casefold(),
            row["addon_b"].name.casefold(),
        )
    )
    return rows[:limit]


# Return the fallback recommendations result from AddonExperience, applying the filters encoded here
# so every caller sees the same eligible records.
def _fallback_recommendations(
    *,
    selected: list[AddonExperience],
    excluded_ids: set[int],
    limit: int,
) -> list[dict]:
    selected_categories = {addon.category_id for addon in selected}
    candidates = list(
        AddonExperience.objects.filter(is_active=True)
        .filter(PUBLIC_ADDON_CATEGORY_FILTER)
        .exclude(pk__in=excluded_ids)
        .select_related("category")
    )
    candidates.sort(
        key=lambda addon: (
            0 if addon.category_id in selected_categories else 1,
            addon.display_order,
            addon.name.casefold(),
        )
    )
    featured = [addon for addon in candidates if addon.is_featured]
    suggestion_pool = featured if featured else candidates
    return [
        {
            "addon": addon,
            "reason": "Featured suggestion based on your current party choices.",
            "pair_count": None,
            "confidence": None,
            "kind": "general",
            "reason_key": "builder.recommendationFeatured",
            "reason_values": {},
        }
        for addon in suggestion_pool[:limit]
    ]


# Recommend up to three active add-ons from completed booking patterns. The queryset applies the
# same visibility and activity restrictions for every caller.
def recommend_addons(
    *,
    selected_ids: Iterable[int],
    package: PartyPackage,
    days: int | None = 365,
    limit: int = 3,
    popularity_by_id: dict | None = None,
) -> list[dict]:
    """Recommend up to three active add-ons from completed booking patterns."""

    selected = list(
        AddonExperience.objects.filter(pk__in=set(selected_ids), is_active=True)
        .filter(PUBLIC_ADDON_CATEGORY_FILTER)
        .select_related("category")
    )
    selected_ids_set = {addon.pk for addon in selected}
    popularity = popularity_by_id or addon_popularity(days=days)["by_id"]

    if selected:
        booking_addons = _completed_addon_sets(days=days)
        base_counts: dict[int, int] = defaultdict(int)
        pair_counts: dict[tuple[int, int], int] = defaultdict(int)
        for addon_ids in booking_addons.values():
            selected_in_booking = selected_ids_set & addon_ids
            other_ids = addon_ids - selected_ids_set
            for anchor_id in selected_in_booking:
                base_counts[anchor_id] += 1
                for candidate_id in other_ids:
                    pair_counts[(anchor_id, candidate_id)] += 1

        candidate_ids = {candidate_id for _anchor_id, candidate_id in pair_counts}
        candidates = AddonExperience.objects.filter(
            is_active=True,
            pk__in=candidate_ids,
        ).filter(PUBLIC_ADDON_CATEGORY_FILTER).select_related("category")
        recommendations = []
        for candidate in candidates:
            strongest = None
            for anchor in selected:
                pair_count = pair_counts[(anchor.pk, candidate.pk)]
                confidence = (
                    Decimal(pair_count) / Decimal(base_counts[anchor.pk])
                    if base_counts[anchor.pk]
                    else Decimal("0")
                )
                score = (pair_count, confidence)
                if strongest is None or score > strongest[0]:
                    strongest = (score, anchor, pair_count, confidence)
            if strongest and strongest[2] >= 2:
                recommendations.append(
                    {
                        "addon": candidate,
                        "reason": (
                            f"Chosen with {strongest[1].name} in "
                            f"{strongest[2]} completed parties."
                        ),
                        "pair_count": strongest[2],
                        "confidence": strongest[3],
                        "average_rating": popularity.get(candidate.pk, {}).get(
                            "average_rating"
                        ),
                        "kind": "pair",
                        "reason_key": "builder.recommendationPair",
                        "reason_values": {
                            "addon_name": strongest[1].name,
                            "addon_slug": strongest[1].slug,
                            "count": strongest[2],
                        },
                    }
                )
        recommendations.sort(
            key=lambda row: (
                -row["pair_count"],
                -float(row["confidence"]),
                -float(row["average_rating"] or 0),
                row["addon"].name.casefold(),
            )
        )
        if recommendations:
            return recommendations[:limit]
        return _fallback_recommendations(
            selected=selected,
            excluded_ids=selected_ids_set,
            limit=limit,
        )

    package_sets = _completed_addon_sets(days=days, package_id=package.pk)
    package_counts: dict[int, int] = defaultdict(int)
    for addon_ids in package_sets.values():
        for addon_id in addon_ids:
            package_counts[addon_id] += 1
    candidates = list(
        AddonExperience.objects.filter(
            is_active=True,
            pk__in=package_counts,
        ).filter(PUBLIC_ADDON_CATEGORY_FILTER).select_related("category")
    )
    candidates.sort(
        key=lambda addon: (
            -package_counts[addon.pk],
            -float(popularity.get(addon.pk, {}).get("average_rating") or 0),
            addon.name.casefold(),
        )
    )
    if candidates:
        return [
            {
                "addon": addon,
                "reason": (
                    f"Selected in {package_counts[addon.pk]} completed parties "
                    f"using {package.name}."
                ),
                "pair_count": None,
                "confidence": None,
                "kind": "package",
                "reason_key": "builder.recommendationPackage",
                "reason_values": {
                    "package_name": package.name,
                    "package_slug": package.slug,
                    "count": package_counts[addon.pk],
                },
            }
            for addon in candidates[:limit]
        ]
    return _fallback_recommendations(selected=[], excluded_ids=set(), limit=limit)


# Return current average/count values for an AJAX success response. The queryset applies the same
# visibility and activity restrictions for every caller.
def review_score_updates(*, package_id: int, addon_ids: Iterable[int]) -> dict:
    """Return current average/count values for an AJAX success response."""

    package = PartyPackage.objects.filter(pk=package_id).annotate(
        rating_count=Count(
            "builds__review",
            filter=Q(builds__status=PartyBuild.Status.COMPLETED),
            distinct=True,
        ),
        average_rating=Avg(
            "builds__review__package_score",
            filter=Q(builds__status=PartyBuild.Status.COMPLETED),
        ),
    ).first()
    rating_filter = Q(
        build_items__ratings__review__booking__status=PartyBuild.Status.COMPLETED
    )
    addons = AddonExperience.objects.filter(pk__in=set(addon_ids)).annotate(
        rating_count=Count("build_items__ratings", filter=rating_filter, distinct=True),
        average_rating=Avg("build_items__ratings__score", filter=rating_filter),
    )
    return {
        "package": {
            "average": float(package.average_rating) if package and package.average_rating else None,
            "count": package.rating_count if package else 0,
        },
        "addons": {
            str(addon.pk): {
                "average": float(addon.average_rating) if addon.average_rating else None,
                "count": addon.rating_count,
            }
            for addon in addons
        },
    }


# Build the owner analytics report without exposing payment information. The queryset applies the
# same visibility and activity restrictions for every caller.
def analytics_report(*, days: int | None = 365) -> dict:
    """Build the owner analytics report without exposing payment information."""

    completed = PartyBuild.objects.filter(status=PartyBuild.Status.COMPLETED)
    start = _period_start(days)
    if start is not None:
        completed = completed.filter(event_date__gte=start)
    completed_count = completed.count()
    reviews = PartyReview.objects.filter(booking__in=completed)
    review_count = reviews.count()
    average_package_score = reviews.aggregate(value=Avg("package_score"))["value"]
    total_addon_selections = PartyBuildAddon.objects.filter(build__in=completed).count()

    popularity = addon_popularity(days=days)
    package_filter = Q(builds__status=PartyBuild.Status.COMPLETED)
    if start is not None:
        package_filter &= Q(builds__event_date__gte=start)
    packages = list(
        PartyPackage.objects.annotate(
            review_count=Count(
                "builds__review",
                filter=package_filter,
                distinct=True,
            ),
            average_rating=Avg(
                "builds__review__package_score",
                filter=package_filter,
            ),
        ).filter(review_count__gt=0).order_by("-review_count", "name")
    )
    comments = list(
        reviews.exclude(comment="")
        .select_related("reviewer", "booking__package")
        .order_by("-updated_at")[:10]
    )
    return {
        "summary": {
            "completed_parties": completed_count,
            "reviews_submitted": review_count,
            "review_completion_rate": (
                Decimal(review_count * 100) / Decimal(completed_count)
                if completed_count
                else Decimal("0")
            ),
            "average_package_score": average_package_score,
            "total_addon_selections": total_addon_selections,
        },
        "addon_rows": popularity["rows"],
        "pair_rows": common_addon_pairs(
            days=days,
            popularity_by_id=popularity["by_id"],
        ),
        "package_rows": packages,
        "recent_comments": comments,
    }
