# This file supplies small chat-navigation facts to templates on every page, such as the correct
# inbox link and personal unread count.
# The calculation respects the signed-in role and uses bounded queries so navigation does not
# reveal inaccessible chats or slow down with each conversation.

from django.urls import reverse

from accounts.permissions import can_respond_to_customer_chat

from .services import is_chat_customer, unread_chat_count


# Build navigation URLs, launcher visibility, responder capability, and unread counts from the
# current account’s chat role. Guests receive safe zero-count defaults without querying private
# chats.
def chat_navigation_context(request):
    user = request.user
    context = {
        "customer_chat_url": reverse("communications:customer_chat"),
        "management_chat_url": reverse("communications:management_inbox"),
        "chat_unread_count": 0,
        "chat_has_unread": False,
        "nav_can_respond_to_chat": False,
        "show_customer_chat_launcher": not getattr(user, "is_authenticated", False),
    }
    if not getattr(user, "is_authenticated", False):
        return context

    responder = can_respond_to_customer_chat(user)
    customer = is_chat_customer(user)
    context["nav_can_respond_to_chat"] = responder
    context["show_customer_chat_launcher"] = customer
    if responder or customer:
        count = unread_chat_count(user)
        context["chat_unread_count"] = count
        context["chat_has_unread"] = count > 0
    return context
