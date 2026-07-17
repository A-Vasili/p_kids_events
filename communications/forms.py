# This file defines the information people may submit through Popadoo forms and the checks applied
# before it is accepted.
# The forms keep browser input separate from trusted database values and return clear errors when
# information is incomplete or unsafe.
# Views use these forms so the same validation applies to normal pages and enhanced interactions.

from __future__ import annotations

from django import forms
from django.db.models import Q

from .models import CustomerChat


# This form collects and validates the information needed for message form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class MessageForm(forms.Form):
    message = forms.CharField(
        label="Write your message",
        max_length=5000,
        help_text="Plain text only. Maximum 5000 characters.",
        error_messages={"required": "Enter a message before sending."},
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "autocomplete": "off",
                "data-i18n-placeholder": "chat.writeMessage",
                "placeholder": "Write your message",
            }
        ),
    )

    # This method handles init for the surrounding message form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["message"].widget.attrs["aria-describedby"] = "id_message-help"
        if self.is_bound:
            # Error attributes are added only after validation so assistive
            # technology receives accurate state without changing the field.
            self.errors
            if "message" in self.errors:
                self.fields["message"].widget.attrs.update(
                    {
                        "aria-invalid": "true",
                        "aria-describedby": "id_message-help id_message-error",
                    }
                )

    # This validation prepares the submitted message and rejects values that would make the form
    # misleading or unsafe.
    def clean_message(self) -> str:
        message = (self.cleaned_data.get("message") or "").strip()
        if not message:
            raise forms.ValidationError("Enter a message before sending.")
        return message


# This form collects and validates the information needed for chat filter form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class ChatFilterForm(forms.Form):
    SORT_CHOICES = (
        ("recent", "Most recent"),
        ("oldest", "Oldest activity"),
        ("customer", "Customer name"),
    )

    search = forms.CharField(required=False, max_length=120)
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"), *CustomerChat.Status.choices),
    )
    unread_only = forms.BooleanField(required=False)
    ordering = forms.ChoiceField(required=False, choices=SORT_CHOICES)

    # This method handles apply for the surrounding chat filter form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def apply(self, queryset):
        if not self.is_valid():
            return queryset.order_by("-last_message_at")
        search = (self.cleaned_data.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(customer__username__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
                | Q(customer__email__icontains=search)
                | Q(messages__body__icontains=search)
            ).distinct()
        status = self.cleaned_data.get("status")
        if status:
            queryset = queryset.filter(status=status)
        ordering = self.cleaned_data.get("ordering") or "recent"
        allowed = {
            "recent": ("-last_message_at", "-pk"),
            "oldest": ("last_message_at", "pk"),
            "customer": ("customer__last_name", "customer__first_name", "customer__username"),
        }
        return queryset.order_by(*allowed[ordering])
