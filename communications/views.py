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


# This class groups the information and behaviour needed for customer only mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class CustomerOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Reject staff accounts instead of letting them impersonate a customer."""

    raise_exception = True

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
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


# This class groups the information and behaviour needed for chat management access mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class ChatManagementAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow full managers and explicitly delegated active chat responders."""

    raise_exception = True

    # This test protects the business rule described by “func”.
    # It guards against a future change silently weakening the expected customer, staff, or data
    # behaviour.
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


# This class groups the information and behaviour needed for chat management context mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class ChatManagementContextMixin:
    management_page_title = "Messages"
    management_active_section = "messages"

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
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


# This function handles customer chat context as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
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


# This view coordinates the customer chat view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CustomerChatView(TemplateView):
    template_name = "communications/customer/chat.html"

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not is_chat_customer(request.user):
            if can_respond_to_customer_chat(request.user):
                return redirect("communications:management_inbox")
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context.update(_customer_chat_context(self.request))
        else:
            context.update({"chat": None, "thread_messages": (), "form": None, "hide_chat_launcher": True})
        return context


# This view coordinates the customer send view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CustomerSendView(CustomerOnlyMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
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


# This view coordinates the customer panel view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CustomerPanelView(CustomerOnlyMixin, View):
    http_method_names = ["get"]

    # This request method displays the current page and its permitted records.
    def get(self, request):
        return render(
            request,
            "communications/includes/chat_panel_content.html",
            _customer_chat_context(request, message_limit=50),
        )


# This view coordinates the customer refresh view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
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


# This view coordinates the customer widget send view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class CustomerWidgetSendView(CustomerOnlyMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
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


# This view coordinates the management inbox view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class ManagementInboxView(
    ChatManagementAccessMixin,
    ChatManagementContextMixin,
    ListView,
):
    template_name = "communications/management/inbox.html"
    context_object_name = "chats"
    paginate_by = 20

    # This helper retrieves filter form for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
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

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_chats = list(context["page_obj"].object_list)
        attach_unread_flags(page_chats, self.request.user)
        context["page_obj"].object_list = page_chats
        context["chats"] = page_chats
        context["filter_form"] = self.get_filter_form()
        return context


# This view coordinates the management chat view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class ManagementChatView(
    ChatManagementAccessMixin,
    ChatManagementContextMixin,
    TemplateView,
):
    template_name = "communications/management/chat.html"

    # This entry check decides whether the signed-in person may reach any method on the view,
    # preventing direct URLs from bypassing role restrictions.
    def dispatch(self, request, *args, **kwargs):
        self.chat = get_object_or_404(
            visible_chats_for(request.user).prefetch_related("messages__sender"),
            public_id=kwargs["public_id"],
        )
        mark_chat_read(chat=self.chat, user=request.user)
        return super().dispatch(request, *args, **kwargs)

    # This step gathers the additional labels, forms, and summary information the template needs
    # to explain the page clearly.
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


# This view coordinates the management reply view page or action.
# It prepares only the records allowed for the signed-in person before choosing the response shown
# in the browser.
class ManagementReplyView(ChatManagementAccessMixin, View):
    http_method_names = ["post"]

    # This request method processes the submitted action after validation and permission checks.
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
