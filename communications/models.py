# This file describes the business records stored by this part of Popadoo and the relationships
# between them.
# The models preserve important history and enforce rules that must remain true no matter which
# page changes the data.
# Views, forms, and services build on these records rather than keeping important information only
# in the browser.

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


# This model represents customer chat as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class CustomerChat(models.Model):
    """One continuing Popadoo support chat for one customer account."""

    # These named choices keep the allowed status values consistent in the database, forms, and
    # page labels.
    class Status(models.TextChoices):
        # This label names the hosted team while preserving the same stored status value and workflow meaning.
        WAITING_STAFF = "waiting_staff", "Waiting for P Kids Events"
        WAITING_CUSTOMER = "waiting_customer", "Waiting for customer"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_chat",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.WAITING_STAFF,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(default=timezone.now)
    last_message_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    # Order records by ('-last_message_at', '-created_at'); create the declared database index(es).
    # These options are enforced by Django rather than by template input.
    class Meta:
        ordering = ("-last_message_at", "-created_at")
        indexes = [
            models.Index(fields=("status", "last_message_at")),
            models.Index(fields=("last_message_at",)),
            models.Index(fields=("public_id",)),
        ]
        permissions = [
            ("respond_to_customer_chat", "Can view and reply to customer chats"),
        ]

    # This method handles str for the surrounding customer chat.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"Chat with {self.customer.get_full_name() or self.customer.username}"


# This model represents chat message as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class ChatMessage(models.Model):
    """An immutable message in a customer chat."""

    # These named choices keep the allowed sender role values consistent in the database, forms,
    # and page labels.
    class SenderRole(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        ADMINISTRATOR = "administrator", "Administrator"
        OWNER = "owner", "Owner"
        WORKER = "worker", "Worker"

    chat = models.ForeignKey(
        CustomerChat,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_customer_chat_messages",
    )
    # These snapshots keep an older conversation understandable after a name or
    # staff role changes. The live account is still used for access decisions.
    sender_name = models.CharField(max_length=150)
    sender_role = models.CharField(max_length=24, choices=SenderRole.choices)
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    # Order records by ('created_at', 'pk'); create the declared database index(es). These options
    # are enforced by Django rather than by template input.
    class Meta:
        ordering = ("created_at", "pk")
        indexes = [models.Index(fields=("chat", "created_at"))]

    # This method handles str for the surrounding chat message.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"{self.sender_name} at {self.created_at:%Y-%m-%d %H:%M}"


# This model represents chat read state as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class ChatReadState(models.Model):
    """Remember when one user last opened one chat."""

    chat = models.ForeignKey(
        CustomerChat,
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_chat_read_states",
    )
    last_read_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Enforce the declared database constraint(s); create the declared database index(es). These
    # options are enforced by Django rather than by template input.
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("chat", "user"),
                name="communications_unique_chat_reader",
            )
        ]
        indexes = [models.Index(fields=("user", "last_read_at"))]

    # This method handles str for the surrounding chat read state.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"{self.user} read {self.chat.public_id}"
