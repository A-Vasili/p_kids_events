# This file coordinates page requests for this area of Popadoo.
# Each view checks who is making the request, gathers only the records they are allowed to see,
# and chooses the template or response to return.
# Multi-step business changes are delegated to services so page handling remains separate from
# data rules.

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.db.models import OuterRef, Subquery
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView

from accounts.permissions import can_respond_to_customer_chat

from .forms import ChatFilterForm, MessageForm
from .models import ChatMessage
from .services import (
    add_customer_message,
    add_staff_message,
    attach_unread_flags,
    is_chat_customer,
    mark_chat_read,
    unread_chats_for,
    visible_chats_for,
)


# Reject staff accounts instead of letting them impersonate a customer. Requires authentication;
# applies a role predicate before dispatch.
class CustomerOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Reject staff accounts instead of letting them impersonate a customer."""

    raise_exception = True

    # Allow the view only when the current account satisfies chat customer. UserPassesTestMixin
    # turns a false result into the configured redirect or permission denial.
    def test_func(self):
        return is_chat_customer(self.request.user)

    # This method handles handle no permission for the surrounding customer only mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied


# Allow full managers and explicitly delegated active chat responders. Requires authentication;
# applies a role predicate before dispatch.
class ChatManagementAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow full managers and explicitly delegated active chat responders."""

    raise_exception = True

    # Allow the view only when the current account satisfies can respond to customer chat.
    # UserPassesTestMixin turns a false result into the configured redirect or permission denial.
    def test_func(self):
        return can_respond_to_customer_chat(self.request.user)

    # This method handles handle no permission for the surrounding chat management access mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied


# Provide the page title, active navigation section, breadcrumbs, and pagination query shared by
# chat-management views. Subclasses add only their page-specific records.
class ChatManagementContextMixin:
    management_page_title = "Messages"
    management_active_section = "messages"

    # Add management page title, management active section, management breadcrumbs, and pagination
    # query to ChatManagementContextMixin’s template context. The base context is preserved, and
    # values are derived from the current request or object rather than client input.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.copy()
        query.pop("page", None)
        context.update(
            {
                "management_page_title": self.management_page_title,
                "management_active_section": self.management_active_section,
                "management_breadcrumbs": (("Messages", None),),
                "pagination_query": query.urlencode(),
            }
        )
        return context


# Compute customer chat context for the surrounding analytics or service workflow. Centralizing the
# calculation keeps date, status, and filtering rules consistent across callers.
def _customer_chat_context(request, *, form=None, message_limit=None):
    chat = visible_chats_for(request.user).prefetch_related("messages__sender").first()
    if chat:
        mark_chat_read(chat=chat, user=request.user)
    thread_messages = ()
    if chat:
        if message_limit:
            thread_messages = list(
                reversed(list(chat.messages.order_by("-created_at", "-pk")[:message_limit]))
            )
        else:
            thread_messages = chat.messages.all()
    return {
        "chat": chat,
        "thread_messages": thread_messages,
        "form": form or MessageForm(),
        "hide_chat_launcher": True,
    }


# Render communications/customer/chat.html for the customer chat journey. Responses continue through
# communications:management_inbox.
class CustomerChatView(TemplateView):
    template_name = "communications/customer/chat.html"

    # Let guests and active customer accounts use the customer chat route; delegated responders are
    # redirected to the management inbox and other staff accounts receive HTTP 403.
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not is_chat_customer(request.user):
            if can_respond_to_customer_chat(request.user):
                return redirect("communications:management_inbox")
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    # Add chat, thread messages, form, and hide chat launcher to CustomerChatView’s template
    # context. The base context is preserved, and values are derived from the current request or
    # object rather than client input.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context.update(_customer_chat_context(self.request))
        else:
            context.update({"chat": None, "thread_messages": (), "form": None, "hide_chat_launcher": True})
        return context


# Coordinate the customer send route. Access is limited to customers; responses continue through
# communications:customer_chat.
class CustomerSendView(CustomerOnlyMixin, View):
    http_method_names = ["post"]

    # Validate the customer message, append it through the rate-limited chat service, and redirect
    # to the customer thread on success; validation errors return the chat page with HTTP 400.
    def post(self, request):
        form = MessageForm(request.POST)
        if form.is_valid():
            try:
                add_customer_message(
                    customer=request.user,
                    body=form.cleaned_data["message"],
                )
            except ValidationError as error:
                form.add_error("message", error)
            else:
                # The confirmation names the hosted support team while the message is still stored and routed exactly as before.
                messages.success(request, "Your message was sent to the P Kids Events team.")
                return redirect("communications:customer_chat")
        return render(
            request,
            "communications/customer/chat.html",
            _customer_chat_context(request, form=form),
            status=400,
        )


# Coordinate the customer panel route. Access is limited to customers.
class CustomerPanelView(CustomerOnlyMixin, View):
    http_method_names = ["get"]

    # This request method displays the current page and its permitted records.
    def get(self, request):
        return render(
            request,
            "communications/includes/chat_panel_content.html",
            _customer_chat_context(request, message_limit=50),
        )


# Coordinate the customer refresh route. Access is limited to customers.
class CustomerRefreshView(CustomerOnlyMixin, View):
    http_method_names = ["get"]

    # This request method displays the current page and its permitted records.
    def get(self, request):
        context = _customer_chat_context(request, message_limit=50)
        html = render_to_string(
            "communications/includes/chat_panel_content.html",
            context,
            request=request,
        )
        return JsonResponse(
            {
                "html": html,
                "unread_count": 0,
                "status": context["chat"].status if context["chat"] else "waiting_staff",
                "last_message_at": context["chat"].last_message_at.isoformat() if context["chat"] else "",
            }
        )


# Coordinate the customer widget send route. Access is limited to customers; POST is the only
# state-changing method.
class CustomerWidgetSendView(CustomerOnlyMixin, View):
    http_method_names = ["post"]

    # Validate the widget message and append it through the customer chat service, then return
    # refreshed panel HTML with HTTP 200 or field errors with HTTP 400.
    def post(self, request):
        form = MessageForm(request.POST)
        if form.is_valid():
            try:
                add_customer_message(
                    customer=request.user,
                    body=form.cleaned_data["message"],
                )
            except ValidationError as error:
                form.add_error("message", error)
        context = _customer_chat_context(request, form=form, message_limit=50)
        html = render_to_string(
            "communications/includes/chat_panel_content.html",
            context,
            request=request,
        )
        return JsonResponse(
            {
                "ok": not form.errors,
                "html": html,
                "unread_count": 0,
            },
            status=200 if not form.errors else 400,
        )


# Render communications/management/inbox.html for the management inbox journey. The queryset method
# limits which records can be loaded.
class ManagementInboxView(
    ChatManagementAccessMixin,
    ChatManagementContextMixin,
    ListView,
):
    template_name = "communications/management/inbox.html"
    context_object_name = "chats"
    paginate_by = 20

    # Build the inbox filter form from the current query string so status and search selections
    # remain visible while the chat queryset is filtered.
    def get_filter_form(self):
        return ChatFilterForm(self.request.GET or None)

    # This query defines the complete set of records the current person may see, so later lookups
    # cannot accidentally expose another customer or staff area.
    def get_queryset(self):
        latest_body = ChatMessage.objects.filter(chat=OuterRef("pk")).order_by("-created_at", "-pk").values("body")[:1]
        queryset = visible_chats_for(self.request.user).annotate(latest_preview=Subquery(latest_body))
        form = self.get_filter_form()
        queryset = form.apply(queryset)
        if form.is_valid() and form.cleaned_data.get("unread_only"):
            queryset = queryset.filter(
                pk__in=unread_chats_for(self.request.user).values("pk")
            )
        return queryset

    # Add chats, filter form, and page obj to ManagementInboxView’s template context. The base
    # context is preserved, and values are derived from the current request or object rather than
    # client input.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_chats = list(context["page_obj"].object_list)
        attach_unread_flags(page_chats, self.request.user)
        context["page_obj"].object_list = page_chats
        context["chats"] = page_chats
        context["filter_form"] = self.get_filter_form()
        return context


# Render communications/management/chat.html for the management chat journey. Responses continue
# through communications:management_inbox.
class ManagementChatView(
    ChatManagementAccessMixin,
    ChatManagementContextMixin,
    TemplateView,
):
    template_name = "communications/management/chat.html"

    # Resolve the requested chat only from the current user’s visible-chat queryset, mark it read,
    # and return HTTP 404 when the public ID is outside that permission scope.
    def dispatch(self, request, *args, **kwargs):
        self.chat = get_object_or_404(
            visible_chats_for(request.user).prefetch_related("messages__sender"),
            public_id=kwargs["public_id"],
        )
        mark_chat_read(chat=self.chat, user=request.user)
        return super().dispatch(request, *args, **kwargs)

    # Add chat, thread messages, form, management page title, and management breadcrumbs to
    # ManagementChatView’s template context. The base context is preserved, and values are derived
    # from the current request or object rather than client input.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "chat": self.chat,
                "thread_messages": self.chat.messages.all(),
                "form": MessageForm(),
                "management_page_title": "Customer chat",
                "management_breadcrumbs": (
                    ("Messages", reverse("communications:management_inbox")),
                    (self.chat.customer.get_full_name() or self.chat.customer.username, None),
                ),
            }
        )
        return context


# Coordinate the management reply route. Responses continue through communications:management_chat
# and communications:management_inbox.
class ManagementReplyView(ChatManagementAccessMixin, View):
    http_method_names = ["post"]

    # Load only a chat visible to the responder, validate the reply, and append it through the
    # delegated-access service; failures redisplay the thread without saving a message.
    def post(self, request, public_id):
        chat = get_object_or_404(visible_chats_for(request.user), public_id=public_id)
        form = MessageForm(request.POST)
        if form.is_valid():
            try:
                add_staff_message(
                    chat_id=chat.pk,
                    responder=request.user,
                    body=form.cleaned_data["message"],
                )
            except (PermissionDenied, ValidationError) as error:
                form.add_error("message", error)
            else:
                messages.success(request, "Your reply was sent.")
                return redirect("communications:management_chat", public_id=chat.public_id)

        mark_chat_read(chat=chat, user=request.user)
        return render(
            request,
            "communications/management/chat.html",
            {
                "chat": chat,
                "thread_messages": chat.messages.select_related("sender").all(),
                "form": form,
                "management_page_title": "Customer chat",
                "management_active_section": "messages",
                "management_breadcrumbs": (
                    ("Messages", reverse("communications:management_inbox")),
                    (chat.customer.get_full_name() or chat.customer.username, None),
                ),
            },
            status=400,
        )
