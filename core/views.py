# This file coordinates page requests for this area of Popadoo.
# Each view checks who is making the request, gathers only the records they are allowed to see,
# and chooses the template or response to return.
# Multi-step business changes are delegated to services so page handling remains separate from
# data rules.

from django.db.models import F
from django.db.models.functions import Trim
from django.views.generic import ListView

from party_builder.models import PartyBuild, PartyReview


# Publish only explicitly consented feedback from completed parties. The queryset method limits
# which records can be loaded.
class TestimonialsView(ListView):
    """Publish only explicitly consented feedback from completed parties."""

    template_name = "core/testimonials.html"
    context_object_name = "testimonials"
    paginate_by = 9

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        return (
            PartyReview.objects.filter(
                visibility=PartyReview.Visibility.TESTIMONIAL,
                testimonial_consent_at__isnull=False,
                booking__status=PartyBuild.Status.COMPLETED,
                booking__customer__isnull=False,
                booking__customer_id=F("reviewer_id"),
            )
            .annotate(public_comment=Trim("comment"))
            .exclude(public_comment="")
            .select_related("reviewer", "booking", "booking__package")
            .order_by("-updated_at", "-pk")
        )
