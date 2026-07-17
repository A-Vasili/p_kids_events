# This service combines worker availability, assigned parties, and management scheduling
# decisions.
# It prevents overlapping or unsuitable work from being presented as available and keeps schedule
# calculations consistent across staff pages.

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from accounts.models import WorkerProfile
from party_builder.models import PartyBuild

from ..models import PartyAssignment, WorkerAvailability


# This helper retrieves event window for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def get_event_window(party_build: PartyBuild):
    """Return aware start/end datetimes, or None until a start time is provided."""

    if not party_build.event_time:
        return None
    start = datetime.combine(party_build.event_date, party_build.event_time)
    if timezone.is_naive(start):
        start = timezone.make_aware(start, timezone.get_current_timezone())
    addon_minutes = sum(
        item.addon.duration_minutes for item in party_build.addon_items.select_related("addon")
    )
    end = start + timedelta(minutes=party_build.package.duration_minutes + addon_minutes)
    return start, end


# This function handles worker is available as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def worker_is_available(worker: WorkerProfile, start_at, end_at) -> bool:
    """Require one positive window covering the event and no blocking overlap."""

    periods = WorkerAvailability.objects.filter(worker=worker)
    positive = periods.filter(
        availability_type__in=(
            WorkerAvailability.AvailabilityType.AVAILABLE,
            WorkerAvailability.AvailabilityType.PREFERRED,
        ),
        start_at__lte=start_at,
        end_at__gte=end_at,
    ).exists()
    blocked = periods.filter(
        availability_type=WorkerAvailability.AvailabilityType.UNAVAILABLE,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).exists()
    return positive and not blocked


# This helper prepares find schedule conflicts for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def find_schedule_conflicts(
    worker: WorkerProfile,
    start_at,
    end_at,
    *,
    exclude_build_id: int | None = None,
) -> list[PartyAssignment]:
    """Return accepted assignments whose calculated event windows overlap."""

    assignments = (
        PartyAssignment.objects.filter(
            worker=worker,
            status=PartyAssignment.Status.ACCEPTED,
        )
        .select_related("party_build__package")
        .prefetch_related("party_build__addon_items__addon")
    )
    if exclude_build_id:
        assignments = assignments.exclude(party_build_id=exclude_build_id)

    conflicts = []
    for assignment in assignments:
        other_window = get_event_window(assignment.party_build)
        if other_window is None:
            continue
        other_start, other_end = other_window
        if other_start < end_at and other_end > start_at:
            conflicts.append(assignment)
    return conflicts


# This helper retrieves worker daily load for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def get_worker_daily_load(worker: WorkerProfile, event_date) -> int:
    return PartyAssignment.objects.filter(
        worker=worker,
        status=PartyAssignment.Status.ACCEPTED,
        party_build__event_date=event_date,
    ).count()
