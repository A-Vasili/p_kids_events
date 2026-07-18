# This service applies trusted booking actions for full managers and, for the dedicated completion
# workflow, the worker who delivered the assigned party.
# It preserves the price and party-size history captured at checkout and records sensitive changes
# for later review.

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.permissions import can_access_full_management, is_worker
from party_builder.models import PartyBuild

from ..models import PartyAssignment
from .audit import record_audit


ALLOWED_STATUS_TRANSITIONS = {
    PartyBuild.Status.SUBMITTED: {PartyBuild.Status.CONTACTED, PartyBuild.Status.CANCELLED},
    PartyBuild.Status.CONTACTED: {PartyBuild.Status.CONFIRMED, PartyBuild.Status.CANCELLED},
    PartyBuild.Status.CONFIRMED: {PartyBuild.Status.COMPLETED, PartyBuild.Status.CANCELLED},
    PartyBuild.Status.COMPLETED: set(),
    PartyBuild.Status.CANCELLED: set(),
}


# This check describes the one narrow completion permission shared by management and the worker
# portal. Older bookings in this project may still say submitted or contacted after a worker has
# accepted them, so a past non-cancelled party may be completed without first repairing that
# historical workflow label. A worker must still be active and hold the accepted assignment for
# that exact booking.
def _validate_completion_access_and_state(
    *,
    booking: PartyBuild,
    actor,
    assignment: PartyAssignment | None = None,
) -> None:
    if not can_access_full_management(actor):
        if not is_worker(actor) or assignment is None:
            raise PermissionDenied(
                "Only an Administrator, Owner, or the accepted assigned worker can complete this party."
            )
        if assignment.worker_id != actor.worker_profile.pk:
            raise PermissionDenied("You can complete only a party assigned to you.")
        if assignment.party_build_id != booking.pk:
            raise PermissionDenied("That assignment does not belong to this party.")
        if assignment.status != PartyAssignment.Status.ACCEPTED:
            raise ValidationError("Only an accepted assignment can be marked as done.")

    if booking.status == PartyBuild.Status.COMPLETED:
        raise ValidationError("This party has already been marked as done.")
    if booking.status == PartyBuild.Status.CANCELLED:
        raise ValidationError("A cancelled party cannot be marked as done.")
    if booking.event_date > timezone.localdate():
        raise ValidationError("A party cannot be completed before its event date.")


# This helper gives page views a safe yes-or-no answer for showing the completion action. The
# completion service repeats every check after locking the database record, so hiding or showing a
# button is never treated as the security decision.
def can_mark_booking_completed(
    *,
    booking: PartyBuild,
    actor,
    assignment: PartyAssignment | None = None,
) -> bool:
    try:
        _validate_completion_access_and_state(
            booking=booking,
            actor=actor,
            assignment=assignment,
        )
    except (PermissionDenied, ValidationError):
        return False
    return True


# This helper turns an ineligible booking state into a short explanation that staff can understand
# on the page. It does not grant access and deliberately leaves assignment ownership to the trusted
# permission check above.
def booking_completion_block_reason(booking: PartyBuild) -> str:
    if booking.status == PartyBuild.Status.COMPLETED:
        return "This party has already been marked as done."
    if booking.status == PartyBuild.Status.CANCELLED:
        return "This booking was cancelled."
    if booking.event_date > timezone.localdate():
        return "The party date has not arrived yet."
    return ""


# This internal step records that the real event took place after the caller has locked the booking.
# It sets the completion time once, keeps the existing audit event type, and records whether the
# confirmation came from management or from the accepted assigned worker.
def _complete_locked_booking(
    *,
    booking: PartyBuild,
    actor,
    source: str,
    assignment: PartyAssignment | None = None,
    note: str = "",
) -> PartyBuild:
    _validate_completion_access_and_state(
        booking=booking,
        actor=actor,
        assignment=assignment,
    )
    before = booking.status
    booking.status = PartyBuild.Status.COMPLETED
    booking.completed_at = timezone.now()
    booking.save(update_fields=["status", "completed_at", "updated_at"])
    audit_after = {
        "status": booking.status,
        "note": note.strip(),
        "completed_at": booking.completed_at.isoformat(),
        "completion_source": source,
    }
    if assignment is not None:
        audit_after["assignment_id"] = assignment.pk
    record_audit(
        actor=actor,
        event_type="booking_status_changed",
        target=booking,
        summary=(
            f"{actor} changed booking {booking.public_id} from {before} "
            f"to {booking.status}."
        ),
        before={"status": before},
        after=audit_after,
    )
    return booking


# This service records that a real party has taken place. It lets a full manager or the worker who
# accepted that exact assignment complete the booking, then unlocks the customer’s existing review
# journey without giving the worker permission to make any other status change.
@transaction.atomic
def mark_booking_completed(
    *,
    booking: PartyBuild,
    actor,
    assignment: PartyAssignment | None = None,
) -> PartyBuild:
    locked_booking = PartyBuild.objects.select_for_update().get(pk=booking.pk)
    locked_assignment = None
    source = "management"

    if not can_access_full_management(actor):
        if assignment is None:
            raise PermissionDenied(
                "Only the accepted assigned worker can complete this party."
            )
        try:
            locked_assignment = (
                PartyAssignment.objects.select_for_update()
                .select_related("worker__user")
                .get(pk=assignment.pk)
            )
        except PartyAssignment.DoesNotExist as error:
            raise PermissionDenied("That assignment is no longer available.") from error
        source = "assigned_worker"

    return _complete_locked_booking(
        booking=locked_booking,
        actor=actor,
        source=source,
        assignment=locked_assignment,
    )


# Return the change booking status result from PartyBuild, applying the filters encoded here so
# every caller sees the same eligible records.
@transaction.atomic
def change_booking_status(*, booking: PartyBuild, status: str, actor, note: str = "") -> PartyBuild:
    if not can_access_full_management(actor):
        raise PermissionDenied("Only an Administrator or Owner can change booking status.")
    locked = PartyBuild.objects.select_for_update().get(pk=booking.pk)
    if status not in ALLOWED_STATUS_TRANSITIONS.get(locked.status, set()):
        raise ValidationError("That booking status change is not allowed.")
    if status == PartyBuild.Status.COMPLETED:
        return _complete_locked_booking(
            booking=locked,
            actor=actor,
            source="management",
            note=note,
        )
    before = locked.status
    locked.status = status
    update_fields = ["status", "updated_at"]
    if status == PartyBuild.Status.CANCELLED:
        locked.assignments.filter(
            status__in=(PartyAssignment.Status.PENDING, PartyAssignment.Status.ACCEPTED)
        ).update(status=PartyAssignment.Status.CANCELLED, responded_at=timezone.now())
        locked.assignment_state = PartyBuild.AssignmentState.UNASSIGNED
        update_fields.append("assignment_state")
    locked.save(update_fields=update_fields)
    record_audit(
        actor=actor,
        event_type="booking_status_changed",
        target=locked,
        summary=f"{actor} changed booking {locked.public_id} from {before} to {status}.",
        before={"status": before},
        after={
            "status": status,
            "note": note.strip(),
            "completed_at": locked.completed_at.isoformat() if locked.completed_at else None,
        },
    )
    return locked


# Move an active booking into the owner attention queue. It locks the live row before applying
# changes so concurrent requests cannot leave partial state.
@transaction.atomic
def send_to_manual_review(*, booking: PartyBuild, actor, reason: str) -> PartyBuild:
    """Move an active booking into the owner attention queue.

    The permission check lives in the service as well as the view so future
    command-line or API entry points cannot bypass the same business rule.
    Completed and cancelled bookings are historical records and must not be
    returned to an operational assignment state.
    """

    if not can_access_full_management(actor):
        raise PermissionDenied("Only an Administrator or Owner can send bookings to manual review.")
    locked = PartyBuild.objects.select_for_update().get(pk=booking.pk)
    if locked.status in {PartyBuild.Status.COMPLETED, PartyBuild.Status.CANCELLED}:
        raise ValidationError(
            "Completed or cancelled bookings cannot be sent to manual review."
        )
    if locked.assignment_state == PartyBuild.AssignmentState.MANUAL_REVIEW:
        raise ValidationError("This booking is already waiting for manual review.")

    cleaned_reason = reason.strip()
    if not cleaned_reason:
        raise ValidationError("Explain why the booking needs manual review.")

    previous = locked.assignment_state
    # A booking under manual review must not remain on a worker's confirmed
    # schedule. Previous offers stay in history as superseded records.
    locked.assignments.filter(
        status__in=(PartyAssignment.Status.PENDING, PartyAssignment.Status.ACCEPTED)
    ).update(
        status=PartyAssignment.Status.SUPERSEDED,
        responded_at=timezone.now(),
    )
    locked.assignment_state = PartyBuild.AssignmentState.MANUAL_REVIEW
    locked.assignment_requested_at = timezone.now()
    locked.save(update_fields=["assignment_state", "assignment_requested_at", "updated_at"])
    record_audit(
        actor=actor,
        event_type="booking_manual_review",
        target=locked,
        summary=f"{actor} sent booking {locked.public_id} to manual review.",
        before={"assignment_state": previous},
        after={"assignment_state": locked.assignment_state, "reason": cleaned_reason},
    )
    return locked
