# This service manages customer ratings, written testimonials, and publication consent after a
# completed party.
# It separates private feedback from public display and preserves consent history so customer
# choices can be respected later.

from __future__ import annotations

from datetime import timedelta
from typing import Mapping

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from operations.services.audit import record_audit

from .analytics import review_score_updates
from .models import (
    AddonRating,
    PartyBuild,
    PartyBuildAddon,
    PartyReview,
    format_review_code,
)

REVIEW_AUTH_SESSION_KEY = "party_review_authorizations"
REVIEW_AUTH_LIFETIME = timedelta(minutes=30)
GENERIC_CODE_ERROR = "That party code is not valid for an eligible booking."


# Find an eligible booking without revealing codes owned by other users. The queryset applies the
# same visibility and activity restrictions for every caller.
def verify_review_code(*, user, submitted_code: str) -> PartyBuild:
    """Find an eligible booking without revealing codes owned by other users."""

    normalized = format_review_code(submitted_code)
    if not normalized or not getattr(user, "is_authenticated", False):
        raise ValidationError(GENERIC_CODE_ERROR)
    booking = (
        PartyBuild.objects.filter(
            customer=user,
            status=PartyBuild.Status.COMPLETED,
            review_code=normalized,
        )
        .select_related("package", "customer")
        .first()
    )
    if booking is None:
        raise ValidationError(GENERIC_CODE_ERROR)
    return booking


# Remember successful code verification for a short period in this session. It also removes stale
# session values and marks the browser session modified when cleanup occurs.
def authorize_review_session(request, booking: PartyBuild) -> None:
    """Remember successful code verification for a short period in this session."""

    markers = request.session.get(REVIEW_AUTH_SESSION_KEY, {})
    if not isinstance(markers, dict):
        markers = {}
    now = int(timezone.now().timestamp())
    markers = {
        key: timestamp
        for key, timestamp in markers.items()
        if isinstance(timestamp, int)
        and now - timestamp <= int(REVIEW_AUTH_LIFETIME.total_seconds())
    }
    markers[str(booking.public_id)] = now
    request.session[REVIEW_AUTH_SESSION_KEY] = markers
    request.session.modified = True


# Return whether this browser recently verified this booking's code.
def review_session_is_authorized(request, booking: PartyBuild) -> bool:
    """Return whether this browser recently verified this booking's code."""

    markers = request.session.get(REVIEW_AUTH_SESSION_KEY, {})
    if not isinstance(markers, dict):
        return False
    timestamp = markers.get(str(booking.public_id))
    if not isinstance(timestamp, int):
        return False
    return timezone.now().timestamp() - timestamp <= REVIEW_AUTH_LIFETIME.total_seconds()


# Load a completed booking owned by the authenticated customer. The selection is reused so callers
# cannot broaden the permitted records independently.
def get_reviewable_booking(*, user, public_id) -> PartyBuild:
    """Load a completed booking owned by the authenticated customer."""

    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied
    booking = (
        PartyBuild.objects.filter(
            public_id=public_id,
            customer=user,
            status=PartyBuild.Status.COMPLETED,
        )
        .select_related("package", "customer")
        .prefetch_related("addon_items__addon", "review__addon_ratings")
        .first()
    )
    if booking is None:
        raise PermissionDenied("This completed booking is not available to your account.")
    return booking


# This safeguard verifies review eligible before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def ensure_review_eligible(*, booking: PartyBuild, reviewer) -> None:
    """Reject reviews that are not owned, completed, and linked to an account."""

    if not getattr(reviewer, "is_authenticated", False):
        raise PermissionDenied
    if booking.customer_id is None or booking.customer_id != reviewer.pk:
        raise PermissionDenied("Only the booking customer can submit this review.")
    if booking.status != PartyBuild.Status.COMPLETED:
        raise PermissionDenied("Only completed parties can be reviewed.")


# Create or update one verified review and its selected add-on ratings. It locks the live row before
# applying changes so concurrent requests cannot leave partial state.
@transaction.atomic
def save_party_review(
    *,
    booking: PartyBuild,
    reviewer,
    package_score: int,
    comment: str,
    addon_scores: Mapping[int, int],
    visibility: str,
    testimonial_name_display: str,
) -> tuple[PartyReview, bool, dict, dict]:
    """Create or update one verified review and its selected add-on ratings.

    Publication consent is handled explicitly here rather than in a hidden model
    save hook. This makes it clear when consent starts, remains active, or is
    withdrawn, while the same transaction continues to protect all ratings.
    """

    # The booking itself is the only row that must be locked while feedback is saved.
    # Loading the optional customer relation in the same locking query works in SQLite but
    # PostgreSQL rejects the resulting outer join, so related display data is loaded only when
    # it is actually needed later.
    locked = PartyBuild.objects.select_for_update().get(pk=booking.pk)
    ensure_review_eligible(booking=locked, reviewer=reviewer)

    valid_visibilities = {choice[0] for choice in PartyReview.Visibility.choices}
    valid_name_displays = {
        choice[0] for choice in PartyReview.TestimonialNameDisplay.choices
    }
    if visibility not in valid_visibilities:
        raise ValidationError({"visibility": "Choose a supported feedback visibility."})
    if testimonial_name_display not in valid_name_displays:
        raise ValidationError(
            {
                "testimonial_name_display": (
                    "Choose how your name may appear with the testimonial."
                )
            }
        )

    normalized_comment = (comment or "").strip()
    if visibility == PartyReview.Visibility.TESTIMONIAL and not normalized_comment:
        raise ValidationError(
            {"comment": "Write a comment before publishing a public testimonial."}
        )

    build_addons = list(
        PartyBuildAddon.objects.select_for_update()
        .filter(build=locked)
        .select_related("addon")
    )
    allowed_ids = {item.pk for item in build_addons}
    try:
        submitted_ids = {int(item_id) for item_id in addon_scores}
    except (TypeError, ValueError) as error:
        raise ValidationError(
            "The add-on ratings must exactly match the experiences in this booking."
        ) from error
    if submitted_ids != allowed_ids:
        raise ValidationError(
            "The add-on ratings must exactly match the experiences in this booking."
        )

    review = PartyReview.objects.select_for_update().filter(booking=locked).first()
    created = review is None
    old_visibility = (
        PartyReview.Visibility.PRIVATE if review is None else review.visibility
    )
    previous_consent_at = None if review is None else review.testimonial_consent_at

    if review is None:
        review = PartyReview(booking=locked, reviewer=reviewer)
    elif review.reviewer_id != reviewer.pk:
        raise PermissionDenied

    review.package_score = package_score
    review.comment = normalized_comment
    review.visibility = visibility

    if visibility == PartyReview.Visibility.PRIVATE:
        review.testimonial_name_display = (
            PartyReview.TestimonialNameDisplay.ANONYMOUS
        )
        review.testimonial_consent_at = None
    else:
        review.testimonial_name_display = testimonial_name_display
        if (
            old_visibility != PartyReview.Visibility.TESTIMONIAL
            or previous_consent_at is None
        ):
            review.testimonial_consent_at = timezone.now()
        else:
            # Editing an already-public testimonial does not silently renew or
            # replace the customer's original consent timestamp.
            review.testimonial_consent_at = previous_consent_at

    review.full_clean()
    review.save()

    existing_ratings = {
        rating.build_addon_id: rating
        for rating in AddonRating.objects.select_for_update().filter(review=review)
    }
    for build_addon in build_addons:
        rating = existing_ratings.get(build_addon.pk) or AddonRating(
            review=review,
            build_addon=build_addon,
        )
        rating.score = int(addon_scores[build_addon.pk])
        rating.full_clean()
        rating.save()

    record_audit(
        actor=reviewer,
        event_type="party_review_created" if created else "party_review_updated",
        target=review,
        summary=(
            f"{reviewer} {'created' if created else 'updated'} verified feedback "
            f"for booking {locked.public_id}."
        ),
        before={"visibility": old_visibility} if not created else {},
        after={
            "visibility": review.visibility,
            "testimonial_consent_active": review.testimonial_consent_at is not None,
            "package_score": package_score,
            "addon_rating_count": len(build_addons),
        },
    )
    stats = review_score_updates(
        package_id=locked.package_id,
        addon_ids=[item.addon_id for item in build_addons],
    )

    was_public = old_visibility == PartyReview.Visibility.TESTIMONIAL
    is_public = review.visibility == PartyReview.Visibility.TESTIMONIAL
    if is_public:
        message = "Your review was saved and published on the Testimonials page."
    elif was_public:
        message = (
            "Your review was updated and removed from the public Testimonials page."
        )
    else:
        # This response confirms that private feedback went only to the hosted P Kids Events team; visibility rules are unchanged.
        message = "Your review was saved as private feedback for P Kids Events."

    return review, created, stats, {
        "message": message,
        "visibility": review.visibility,
        "is_public_testimonial": is_public,
        "old_visibility": old_visibility,
    }
