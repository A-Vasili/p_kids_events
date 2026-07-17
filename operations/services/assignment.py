# This service manages which worker is responsible for a completed party booking.
# It checks availability and role eligibility before changing an assignment, and preserves a clear
# history for staff and management users.
# Related database updates are treated as one action so an assignment is never left half-complete.

from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from accounts.models import WorkerProfile
from accounts.permissions import WORKER_GROUP, can_access_full_management
from party_builder.models import PartyBuild

from ..models import AuditEvent, PartyAssignment
from .scheduling import (
    find_schedule_conflicts,
    get_event_window,
    get_worker_daily_load,
    worker_is_available,
)


# This helper prepares find eligible workers for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def find_eligible_workers(party_build: PartyBuild, excluded_worker_ids=None):
    """Return active workers who are available, conflict-free, and below capacity."""

    excluded_worker_ids = set(excluded_worker_ids or [])
    event_window = get_event_window(party_build)
    if event_window is None:
        return []
    start_at, end_at = event_window

    workers = (
        WorkerProfile.objects.filter(
            is_active_worker=True,
            user__is_active=True,
            user__groups__name=WORKER_GROUP,
        )
        .exclude(pk__in=excluded_worker_ids)
        .select_related("user")
        .distinct()
    )

    eligible = []
    for worker in workers:
        if not worker_is_available(worker, start_at, end_at):
            continue
        if find_schedule_conflicts(worker, start_at, end_at):
            continue
        if get_worker_daily_load(worker, party_build.event_date) >= worker.max_daily_parties:
            continue
        eligible.append(worker)
    return eligible


# This function handles rank workers as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def rank_workers(workers, party_build: PartyBuild):
    """Use daily load, pending workload, and oldest recent assignment for fairness."""

    ranked = []
    for worker in workers:
        pending_count = worker.assignments.filter(status=PartyAssignment.Status.PENDING).count()
        last_assignment = worker.assignments.filter(
            status=PartyAssignment.Status.ACCEPTED
        ).aggregate(last=Max("assigned_at"))["last"]
        ranked.append(
            (
                get_worker_daily_load(worker, party_build.event_date),
                pending_count,
                last_assignment or datetime.min.replace(tzinfo=datetime_timezone.utc),
                worker.pk,
                worker,
            )
        )
    ranked.sort(key=lambda item: item[:-1])
    return [item[-1] for item in ranked]


# This function handles offer assignment as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def offer_assignment(party_build_id: int) -> PartyAssignment | None:
    """Offer a completed booking to the best available worker or flag owner review."""

    party_build = (
        PartyBuild.objects.select_for_update()
        .select_related("package")
        .prefetch_related("addon_items__addon")
        .get(pk=party_build_id)
    )
    if party_build.assignment_state == PartyBuild.AssignmentState.ASSIGNED:
        return party_build.assignments.filter(status=PartyAssignment.Status.ACCEPTED).first()
    if party_build.assignments.filter(status=PartyAssignment.Status.PENDING).exists():
        return party_build.assignments.filter(status=PartyAssignment.Status.PENDING).first()

    declined_ids = party_build.assignments.filter(
        status=PartyAssignment.Status.DECLINED
    ).values_list("worker_id", flat=True)
    candidates = rank_workers(
        find_eligible_workers(party_build, declined_ids),
        party_build,
    )
    if not candidates:
        party_build.assignment_state = PartyBuild.AssignmentState.MANUAL_REVIEW
        party_build.assignment_requested_at = timezone.now()
        party_build.save(update_fields=["assignment_state", "assignment_requested_at", "updated_at"])
        return None

    assignment = PartyAssignment.objects.create(
        party_build=party_build,
        worker=candidates[0],
        status=PartyAssignment.Status.PENDING,
        assignment_source=PartyAssignment.Source.AUTOMATIC,
    )
    party_build.assignment_state = PartyBuild.AssignmentState.PENDING
    party_build.assignment_requested_at = timezone.now()
    party_build.save(update_fields=["assignment_state", "assignment_requested_at", "updated_at"])
    return assignment


# This function handles accept assignment as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def accept_assignment(*, assignment_id: int, worker: WorkerProfile, actor=None) -> PartyAssignment:
    """Accept safely after rechecking conflicts under database row locks."""

    assignment = (
        PartyAssignment.objects.select_for_update()
        .select_related("party_build__package", "worker")
        .prefetch_related("party_build__addon_items__addon")
        .get(pk=assignment_id)
    )
    party_build = PartyBuild.objects.select_for_update().get(pk=assignment.party_build_id)
    if assignment.worker_id != worker.pk:
        raise ValidationError("This assignment belongs to another worker.")
    if assignment.status != PartyAssignment.Status.PENDING:
        raise ValidationError("This assignment is no longer awaiting a response.")
    event_window = get_event_window(assignment.party_build)
    if event_window is None:
        raise ValidationError("The owner must confirm an event time before acceptance.")
    start_at, end_at = event_window
    if not worker_is_available(worker, start_at, end_at):
        raise ValidationError("Your availability no longer covers this event.")
    if find_schedule_conflicts(worker, start_at, end_at, exclude_build_id=party_build.pk):
        raise ValidationError("This event now conflicts with an accepted party.")

    assignment.status = PartyAssignment.Status.ACCEPTED
    assignment.responded_at = timezone.now()
    assignment.save(update_fields=["status", "responded_at"])
    party_build.assignments.filter(status=PartyAssignment.Status.PENDING).exclude(
        pk=assignment.pk
    ).update(status=PartyAssignment.Status.SUPERSEDED, responded_at=timezone.now())
    party_build.assignment_state = PartyBuild.AssignmentState.ASSIGNED
    party_build.save(update_fields=["assignment_state", "updated_at"])
    AuditEvent.objects.create(
        actor=actor or worker.user,
        event_type="assignment_accepted",
        object_type="PartyAssignment",
        object_id=str(assignment.pk),
        summary=f"{worker} accepted party {party_build.public_id}.",
    )
    return assignment


# This function handles decline assignment as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
@transaction.atomic
def decline_assignment(*, assignment_id: int, worker: WorkerProfile, reason: str, actor=None):
    """Preserve the decline and offer the booking to the next eligible worker."""

    assignment = PartyAssignment.objects.select_for_update().select_related("party_build").get(
        pk=assignment_id
    )
    if assignment.worker_id != worker.pk:
        raise ValidationError("This assignment belongs to another worker.")
    if assignment.status != PartyAssignment.Status.PENDING:
        raise ValidationError("This assignment is no longer awaiting a response.")
    assignment.status = PartyAssignment.Status.DECLINED
    assignment.decline_reason = reason.strip()
    assignment.responded_at = timezone.now()
    assignment.save(update_fields=["status", "decline_reason", "responded_at"])
    assignment.party_build.assignment_state = PartyBuild.AssignmentState.UNASSIGNED
    assignment.party_build.save(update_fields=["assignment_state", "updated_at"])
    AuditEvent.objects.create(
        actor=actor or worker.user,
        event_type="assignment_declined",
        object_type="PartyAssignment",
        object_id=str(assignment.pk),
        summary=f"{worker} declined party {assignment.party_build.public_id}.",
        after_data={"reason": reason.strip()},
    )
    transaction.on_commit(lambda: offer_assignment(assignment.party_build_id))
    return assignment


# This business action carries out assign manually.
# It validates the live records and permissions before changing anything, then keeps related
# updates together so partial results are not left behind.
@transaction.atomic
def assign_manually(
    *,
    party_build: PartyBuild,
    worker: WorkerProfile,
    owner,
    override_reason: str = "",
    already_agreed: bool = False,
):
    """Create an owner assignment, requiring a reason whenever a conflict is overridden."""

    if not can_access_full_management(owner) or not owner.has_perm("operations.manually_assign_party"):
        raise PermissionDenied("Administrator or Owner assignment permission is required.")
    if (
        not worker.is_active_worker
        or not worker.user.is_active
        or not worker.user.groups.filter(name=WORKER_GROUP).exists()
    ):
        raise ValidationError("Choose an active worker account.")

    locked_build = PartyBuild.objects.select_for_update().get(pk=party_build.pk)
    if locked_build.status in {
        PartyBuild.Status.COMPLETED,
        PartyBuild.Status.CANCELLED,
    }:
        raise ValidationError(
            "Completed or cancelled bookings cannot receive a worker assignment."
        )
    event_window = get_event_window(party_build)
    conflicts = []
    is_available = False
    if event_window:
        conflicts = find_schedule_conflicts(worker, *event_window, exclude_build_id=party_build.pk)
        is_available = worker_is_available(worker, *event_window)
    if (conflicts or not is_available) and not override_reason.strip():
        raise ValidationError(
            "Explain why an unavailable or conflicting worker is being assigned."
        )

    # Reassignment preserves the previous records for history but removes them
    # from confirmed schedules before the new offer is created.
    locked_build.assignments.filter(
        status__in=(PartyAssignment.Status.PENDING, PartyAssignment.Status.ACCEPTED)
    ).update(
        status=PartyAssignment.Status.SUPERSEDED,
        responded_at=timezone.now(),
    )
    status = PartyAssignment.Status.ACCEPTED if already_agreed else PartyAssignment.Status.PENDING
    assignment = PartyAssignment.objects.create(
        party_build=locked_build,
        worker=worker,
        status=status,
        assignment_source=(
            PartyAssignment.Source.ADMIN_OVERRIDE
            if owner.is_superuser
            else PartyAssignment.Source.OWNER_MANUAL
        ),
        assigned_by=owner,
        responded_at=timezone.now() if already_agreed else None,
        conflict_override_reason=override_reason.strip(),
    )
    locked_build.assignment_state = (
        PartyBuild.AssignmentState.ASSIGNED
        if already_agreed
        else PartyBuild.AssignmentState.PENDING
    )
    locked_build.assignment_requested_at = timezone.now()
    locked_build.save(update_fields=["assignment_state", "assignment_requested_at", "updated_at"])
    AuditEvent.objects.create(
        actor=owner,
        event_type="manual_assignment",
        object_type="PartyAssignment",
        object_id=str(assignment.pk),
        summary=f"{owner} assigned party {locked_build.public_id} to {worker}.",
        after_data={
            "worker_id": worker.pk,
            "already_agreed": already_agreed,
            "override_reason": override_reason.strip(),
        },
    )
    return assignment
