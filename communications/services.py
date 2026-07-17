# This file contains the trusted business actions for this feature.
# Keeping these actions outside views means the same permission, validation, history, and
# all-or-nothing database rules apply wherever the action is used.
# The surrounding pages collect intent, while these services decide what may safely change.

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from accounts.permissions import (
    OWNER_GROUP,
    WORKER_GROUP,
    can_respond_to_customer_chat,
    is_administrator,
    is_owner,
    is_worker,
    user_in_group,
)

from .models import ChatMessage, ChatReadState, CustomerChat


MESSAGE_LIMIT = 10
MESSAGE_WINDOW_MINUTES = 5


# This role check answers whether the current account qualifies as chat customer.
# Callers use the answer for navigation and convenience, while protected views and services still
# enforce access themselves.
def is_chat_customer(user) -> bool:
    """A customer is an active account without a protected business role."""

    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and not user.is_superuser
        and not user_in_group(user, OWNER_GROUP)
        and not user_in_group(user, WORKER_GROUP)
    )


# This helper chooses the role label saved beside a chat message so the history still makes sense
# if the sender’s account changes later.
def sender_role_for(user) -> str:
    if is_administrator(user):
        return ChatMessage.SenderRole.ADMINISTRATOR
    if is_owner(user):
        return ChatMessage.SenderRole.OWNER
    if is_worker(user):
        return ChatMessage.SenderRole.WORKER
    return ChatMessage.SenderRole.CUSTOMER


# This helper chooses the readable name saved beside a chat message while keeping the stored
# snapshot within its database limit.
def sender_name_for(user) -> str:
    return (user.get_full_name() or user.username)[:150]


# This helper prepares visible chats for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def visible_chats_for(user):
    """Return a role-restricted queryset used by every chat detail view."""

    queryset = CustomerChat.objects.select_related("customer", "last_message_by")
    if can_respond_to_customer_chat(user):
        return queryset
    if is_chat_customer(user):
        return queryset.filter(customer=user)
    return queryset.none()


# This validation prepares the submitted message and rejects values that would make the form
# misleading or unsafe.
def _clean_message(body: str) -> str:
    body = (body or "").strip()
    if not body:
        raise ValidationError("Enter a message before sending.")
    if len(body) > 5000:
        raise ValidationError("The message must be 5000 characters or fewer.")
    return body


# This safeguard verifies customer burst limit before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def _enforce_customer_burst_limit(customer) -> None:
    since = timezone.now() - timedelta(minutes=MESSAGE_WINDOW_MINUTES)
    recent = ChatMessage.objects.filter(
        sender=customer,
        sender_role=ChatMessage.SenderRole.CUSTOMER,
        created_at__gte=since,
    ).count()
    if recent >= MESSAGE_LIMIT:
        raise ValidationError(
            "Please wait a few minutes before sending another message."
        )


# This business action carries out add customer message.
# It validates the live records and permissions before changing anything, then keeps related
# updates together so partial results are not left behind.
@transaction.atomic
def add_customer_message(*, customer, body: str) -> tuple[CustomerChat, ChatMessage]:
    """Create or reuse the customer's one chat and append a trusted message."""

    if not is_chat_customer(customer):
        raise PermissionDenied("Only customer accounts can send customer chat messages.")
    body = _clean_message(body)
    _enforce_customer_burst_limit(customer)

    chat, _ = CustomerChat.objects.select_for_update().get_or_create(
        customer=customer,
        defaults={"last_message_at": timezone.now()},
    )
    now = timezone.now()
    message = ChatMessage.objects.create(
        chat=chat,
        sender=customer,
        sender_name=sender_name_for(customer),
        sender_role=ChatMessage.SenderRole.CUSTOMER,
        body=body,
    )
    chat.status = CustomerChat.Status.WAITING_STAFF
    chat.last_message_at = now
    chat.last_message_by = customer
    chat.save(update_fields=("status", "last_message_at", "last_message_by", "updated_at"))
    mark_chat_read(chat=chat, user=customer, read_at=now)
    return chat, message


# This business action carries out add staff message.
# It validates the live records and permissions before changing anything, then keeps related
# updates together so partial results are not left behind.
@transaction.atomic
def add_staff_message(*, chat_id: int, responder, body: str) -> ChatMessage:
    """Reply only after re-checking the responder's live delegation."""

    if not can_respond_to_customer_chat(responder):
        raise PermissionDenied("You do not have customer-chat access.")
    body = _clean_message(body)
    try:
        chat = visible_chats_for(responder).select_for_update().get(pk=chat_id)
    except CustomerChat.DoesNotExist as error:
        raise PermissionDenied("You no longer have access to this chat.") from error
    now = timezone.now()
    message = ChatMessage.objects.create(
        chat=chat,
        sender=responder,
        sender_name=sender_name_for(responder),
        sender_role=sender_role_for(responder),
        body=body,
    )
    chat.status = CustomerChat.Status.WAITING_CUSTOMER
    chat.last_message_at = now
    chat.last_message_by = responder
    chat.save(update_fields=("status", "last_message_at", "last_message_by", "updated_at"))
    mark_chat_read(chat=chat, user=responder, read_at=now)
    return message


# This step records that one specific person has seen the current chat; it never clears the unread
# state for other responders.
def mark_chat_read(*, chat: CustomerChat, user, read_at=None) -> None:
    if not getattr(user, "is_authenticated", False):
        return
    ChatReadState.objects.update_or_create(
        chat=chat,
        user=user,
        defaults={"last_read_at": read_at or timezone.now()},
    )


# This helper prepares unread chats for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def unread_chats_for(user):
    """Find unread chats without creating read rows for every possible responder."""

    if not getattr(user, "is_authenticated", False):
        return CustomerChat.objects.none()
    read_state = ChatReadState.objects.filter(
        chat=OuterRef("pk"),
        user=user,
        last_read_at__gte=OuterRef("last_message_at"),
    )
    return visible_chats_for(user).exclude(last_message_by=user).annotate(
        already_read=Exists(read_state)
    ).filter(already_read=False)


# This helper prepares unread chat count for the page or service that called it.
# It returns a consistent, permission-aware result so callers do not need to repeat the same
# selection rules.
def unread_chat_count(user) -> int:
    return unread_chats_for(user).count()


# This helper marks the already-loaded chat rows that are unread for the current person without
# running a separate query for every row.
def attach_unread_flags(chats, user) -> None:
    ids = {chat.pk for chat in chats}
    unread_ids = set(unread_chats_for(user).filter(pk__in=ids).values_list("pk", flat=True))
    for chat in chats:
        chat.is_unread_for_user = chat.pk in unread_ids
