# This file protects the private customer chat shared by customers and authorised Popadoo
# responders with automated regression checks.
# The scenarios describe what customers and staff should be allowed to do, and what must remain
# inaccessible or unchanged.
# Temporary test data is discarded after the checks, so real Popadoo records are not affected.
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from accounts.models import WorkerProfile
from accounts.permissions import (
    CHAT_RESPONDER_GROUP,
    OWNER_GROUP,
    PRICING_GROUP,
    WORKER_GROUP,
    can_respond_to_customer_chat,
)
from operations.models import AuditEvent
from operations.services.users import (
    customer_delete_blockers,
    demote_worker,
    grant_chat_responder_access,
    revoke_chat_responder_access,
)

from .models import ChatMessage, ChatReadState, CustomerChat
from .services import (
    add_customer_message,
    add_staff_message,
    mark_chat_read,
    unread_chat_count,
)

User = get_user_model()


# This group of tests protects the chat test base behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ChatTestBase(TestCase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com"
        )
        cls.owner = User.objects.create_user(
            username="owner", email="owner@example.com"
        )
        cls.customer = User.objects.create_user(
            username="customer",
            first_name="Chris",
            email="customer@example.com",
        )
        cls.other_customer = User.objects.create_user(
            username="other", email="other@example.com"
        )
        cls.worker = User.objects.create_user(
            username="worker", email="worker@example.com"
        )
        cls.other_worker = User.objects.create_user(
            username="other-worker",
            email="other-worker@example.com",
        )

        cls.owner_group, _ = Group.objects.get_or_create(name=OWNER_GROUP)
        cls.worker_group, _ = Group.objects.get_or_create(name=WORKER_GROUP)
        cls.pricing_group, _ = Group.objects.get_or_create(name=PRICING_GROUP)
        cls.chat_group, _ = Group.objects.get_or_create(name=CHAT_RESPONDER_GROUP)
        chat_permissions = Permission.objects.filter(
            codename__in={
                "view_customerchat",
                "view_chatmessage",
                "respond_to_customer_chat",
            }
        )
        cls.chat_group.permissions.add(*chat_permissions)
        cls.owner_group.user_set.add(cls.owner)
        cls.worker_group.user_set.add(cls.worker, cls.other_worker)
        cls.worker_profile = WorkerProfile.objects.create(
            user=cls.worker, display_name="Worker One", is_active_worker=True
        )
        cls.other_worker_profile = WorkerProfile.objects.create(
            user=cls.other_worker, display_name="Worker Two", is_active_worker=True
        )

    # This method handles delegate chat for the surrounding chat test base.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def delegate_chat(self, user=None):
        user = user or self.worker
        self.chat_group.user_set.add(user)
        user.refresh_from_db()
        return user


# This group of tests protects the chat model tests behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ChatModelTests(ChatTestBase):
    # Verify that the database’s one-to-one customer relation rejects a second CustomerChat for the
    # same customer, preserving one conversation thread per account.
    def test_one_customer_has_one_chat(self):
        CustomerChat.objects.create(customer=self.customer)
        with self.assertRaises(Exception):
            CustomerChat.objects.create(customer=self.customer)

    # Verify that chat uses UUID and waiting staff default. The required outcome is chat.public_id
    # is true and chat status is CustomerChat.Status.WAITING_STAFF.
    def test_chat_uses_uuid_and_waiting_staff_default(self):
        chat = CustomerChat.objects.create(customer=self.customer)
        self.assertTrue(chat.public_id)
        self.assertEqual(chat.status, CustomerChat.Status.WAITING_STAFF)

    # Verify that message keeps sender snapshot. The required outcome is message.sender_name equals
    # 'Chris' and message.sender_role equals ChatMessage.SenderRole.CUSTOMER.
    def test_message_keeps_sender_snapshot(self):
        chat, message = add_customer_message(customer=self.customer, body="Hello")
        self.customer.first_name = "Changed"
        self.customer.save(update_fields=["first_name"])
        message.refresh_from_db()
        self.assertEqual(message.sender_name, "Chris")
        self.assertEqual(message.sender_role, ChatMessage.SenderRole.CUSTOMER)

    # Verify that read state is unique per user and chat. The required outcome is
    # ChatReadState.objects.filter(chat=chat, user=self.admin) count is 1.
    def test_read_state_is_unique_per_user_and_chat(self):
        chat, _ = add_customer_message(customer=self.customer, body="Hello")
        mark_chat_read(chat=chat, user=self.admin)
        mark_chat_read(chat=chat, user=self.admin)
        self.assertEqual(
            ChatReadState.objects.filter(chat=chat, user=self.admin).count(), 1
        )

    # Verify that chat protects customer history. The required outcome is raises ProtectedError.
    def test_chat_protects_customer_history(self):
        CustomerChat.objects.create(customer=self.customer)
        with self.assertRaises(ProtectedError):
            self.customer.delete()


# This group of tests protects the customer chat tests behaviour as one related customer or staff
# workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class CustomerChatTests(ChatTestBase):
    # Verify that anonymous page prompts for sign in. A guest sends GET to
    # communications:customer_chat; the required outcome is HTTP 200, renders 'Sign in to chat with
    # P Kids Events', and contains a link to accounts:accounts_sign_in.
    def test_anonymous_page_prompts_for_sign_in(self):
        response = self.client.get(reverse("communications:customer_chat"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in to chat with P Kids Events")
        self.assertContains(response, reverse("accounts:accounts_sign_in"))

    # Verify that anonymous user cannot send. A guest sends POST to communications:customer_send;
    # the required outcome is HTTP 302 and CustomerChat.objects count is 0.
    def test_anonymous_user_cannot_send(self):
        response = self.client.post(
            reverse("communications:customer_send"), {"message": "Hello"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomerChat.objects.count(), 0)

    # Verify that first message creates chat and later message reuses it. The customer sends POST to
    # communications:customer_send; the required outcome is
    # CustomerChat.objects.filter(customer=self.customer) count is 1 and
    # ChatMessage.objects.filter(chat__customer=self.customer) count is 2.
    def test_first_message_creates_chat_and_later_message_reuses_it(self):
        self.client.force_login(self.customer)
        self.client.post(
            reverse("communications:customer_send"), {"message": "First"}
        )
        self.client.post(
            reverse("communications:customer_send"), {"message": "Second"}
        )
        self.assertEqual(CustomerChat.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(ChatMessage.objects.filter(chat__customer=self.customer).count(), 2)

    # Verify that customer message sets waiting staff. The required outcome is chat status is
    # CustomerChat.Status.WAITING_STAFF.
    def test_customer_message_sets_waiting_staff(self):
        chat, _ = add_customer_message(customer=self.customer, body="Hello")
        self.delegate_chat()
        add_staff_message(chat_id=chat.pk, responder=self.worker, body="Reply")
        add_customer_message(customer=self.customer, body="Thank you")
        chat.refresh_from_db()
        self.assertEqual(chat.status, CustomerChat.Status.WAITING_STAFF)

    # Verify that whitespace only message is rejected. The customer sends POST to
    # communications:customer_send; the required outcome is HTTP 400 and ChatMessage.objects count
    # is 0.
    def test_whitespace_only_message_is_rejected(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("communications:customer_send"), {"message": "   "}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ChatMessage.objects.count(), 0)

    # Verify that customer cannot supply identity or status. The customer sends POST to
    # communications:customer_send; the required outcome is chat.customer equals self.customer, chat
    # status is CustomerChat.Status.WAITING_STAFF, and message.sender equals self.customer.
    def test_customer_cannot_supply_identity_or_status(self):
        self.client.force_login(self.customer)
        self.client.post(
            reverse("communications:customer_send"),
            {
                "message": "Hello",
                "customer": self.other_customer.pk,
                "sender": self.admin.pk,
                "status": CustomerChat.Status.WAITING_CUSTOMER,
            },
        )
        chat = CustomerChat.objects.get()
        message = chat.messages.get()
        self.assertEqual(chat.customer, self.customer)
        self.assertEqual(chat.status, CustomerChat.Status.WAITING_STAFF)
        self.assertEqual(message.sender, self.customer)

    # Verify that message HTML is escaped. The customer sends GET to communications:customer_chat;
    # the required outcome is renders '&lt;script&gt;alert(1)&lt;/script&gt;' and does not expose
    # '<script>alert(1)</script>'.
    def test_message_html_is_escaped(self):
        add_customer_message(customer=self.customer, body="<script>alert(1)</script>")
        self.client.force_login(self.customer)
        response = self.client.get(reverse("communications:customer_chat"))
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    # Verify that widget endpoint contains only signed-in customers chat. The customer sends GET to
    # communications:customer_panel; the required outcome is renders 'Mine' and does not expose 'Not
    # mine'.
    def test_widget_endpoint_contains_only_signed_in_customers_chat(self):
        add_customer_message(customer=self.customer, body="Mine")
        add_customer_message(customer=self.other_customer, body="Not mine")
        self.client.force_login(self.customer)
        response = self.client.get(reverse("communications:customer_panel"))
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Not mine")

    # Verify that staff accounts do not get customer composer. The admin sends GET to
    # communications:customer_chat; the required outcome is redirects to
    # communications:management_inbox.
    def test_staff_accounts_do_not_get_customer_composer(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("communications:customer_chat"))
        self.assertRedirects(response, reverse("communications:management_inbox"))

    # Verify that burst limit rejects eleventh recent message. The required outcome is raises
    # ValidationError.
    def test_burst_limit_rejects_eleventh_recent_message(self):
        for number in range(10):
            add_customer_message(customer=self.customer, body=f"Message {number}")
        with self.assertRaises(ValidationError):
            add_customer_message(customer=self.customer, body="Too many")


# This group of tests protects the management chat tests behaviour as one related customer or
# staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ManagementChatTests(ChatTestBase):
    # This setup prepares the shared accounts and business records used by the following scenarios
    # without touching real project data.
    def setUp(self):
        super().setUp()
        self.chat, _ = add_customer_message(customer=self.customer, body="Question")

    # Verify that administrator and owner can open messages. The user sends GET to
    # communications:management_inbox; the required outcome is HTTP 200.
    def test_administrator_and_owner_can_open_messages(self):
        for user in (self.admin, self.owner):
            self.client.force_login(user)
            response = self.client.get(reverse("communications:management_inbox"))
            self.assertEqual(response.status_code, 200)

    # Verify that full manager can reply. The admin sends POST to communications:management_reply;
    # the required outcome is redirects to communications:management_chat, self.chat status is
    # CustomerChat.Status.WAITING_CUSTOMER, and self.chat.messages.last().sender_role equals
    # 'administrator'.
    def test_full_manager_can_reply(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("communications:management_reply", args=[self.chat.public_id]),
            {"message": "Team reply"},
        )
        self.assertRedirects(
            response,
            reverse("communications:management_chat", args=[self.chat.public_id]),
        )
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.status, CustomerChat.Status.WAITING_CUSTOMER)
        self.assertEqual(self.chat.messages.last().sender_role, "administrator")

    # Verify that customer and ordinary worker are denied. The user sends GET to
    # communications:management_inbox; the required outcome is HTTP 403.
    def test_customer_and_ordinary_worker_are_denied(self):
        for user in (self.customer, self.worker):
            self.client.force_login(user)
            response = self.client.get(reverse("communications:management_inbox"))
            self.assertEqual(response.status_code, 403)

    # Verify that pricing only worker is denied. The worker sends GET to
    # communications:management_inbox; the required outcome is HTTP 403.
    def test_pricing_only_worker_is_denied(self):
        self.pricing_group.user_set.add(self.worker)
        self.client.force_login(self.worker)
        response = self.client.get(reverse("communications:management_inbox"))
        self.assertEqual(response.status_code, 403)

    # Verify that delegated active worker can view and reply. The worker sends GET to
    # communications:management_inbox; the required outcome is HTTP 200, HTTP 302, and
    # self.chat.messages.last().sender_role equals 'worker'.
    def test_delegated_active_worker_can_view_and_reply(self):
        self.delegate_chat()
        self.client.force_login(self.worker)
        response = self.client.get(reverse("communications:management_inbox"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("communications:management_reply", args=[self.chat.public_id]),
            {"message": "Worker reply"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.chat.messages.last().sender_role, "worker")

    # Verify that inactive delegated worker is denied. The worker sends GET to
    # communications:management_inbox; the required outcome is HTTP 403.
    def test_inactive_delegated_worker_is_denied(self):
        self.delegate_chat()
        self.worker_profile.is_active_worker = False
        self.worker_profile.save(update_fields=["is_active_worker"])
        self.client.force_login(self.worker)
        response = self.client.get(reverse("communications:management_inbox"))
        self.assertEqual(response.status_code, 403)

    # Verify that chat responder cannot access unrelated management sections. The worker sends GET
    # to management:management_dashboard; the required outcome is redirects to
    # communications:management_inbox, self returns HTTP 403, and self returns HTTP 403.
    def test_chat_responder_cannot_access_unrelated_management_sections(self):
        self.delegate_chat()
        self.client.force_login(self.worker)
        self.assertRedirects(
            self.client.get(reverse("management:management_dashboard")),
            reverse("communications:management_inbox"),
        )
        self.assertEqual(
            self.client.get(reverse("management:management_booking_list")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("management:management_user_list")).status_code,
            403,
        )

    # Verify that worker with pricing and chat keeps both sections. The worker sends GET to
    # communications:management_inbox; the required outcome is self returns HTTP 200 and self
    # returns HTTP 200.
    def test_worker_with_pricing_and_chat_keeps_both_sections(self):
        self.pricing_group.user_set.add(self.worker)
        self.delegate_chat()
        self.client.force_login(self.worker)
        self.assertEqual(
            self.client.get(reverse("communications:management_inbox")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("management:management_catalogue")).status_code,
            200,
        )

    # Verify that management search finds message text. The admin sends GET to
    # communications:management_inbox; the required outcome is renders 'self.customer.email'.
    def test_management_search_finds_message_text(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("communications:management_inbox"), {"search": "Question"}
        )
        self.assertContains(response, self.customer.email)


# This group of tests protects the chat role management tests behaviour as one related customer or
# staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ChatRoleManagementTests(ChatTestBase):
    # Verify that admin can grant and revoke chat access. The required outcome is self.worker
    # membership in CHAT_RESPONDER_GROUP exists and self.worker membership in CHAT_RESPONDER_GROUP
    # does not exist.
    def test_admin_can_grant_and_revoke_chat_access(self):
        grant_chat_responder_access(self.worker, self.admin)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.groups.filter(name=CHAT_RESPONDER_GROUP).exists())
        revoke_chat_responder_access(self.worker, self.admin)
        self.assertFalse(self.worker.groups.filter(name=CHAT_RESPONDER_GROUP).exists())

    # Verify that inactive worker cannot receive chat access. The required outcome is raises
    # ValidationError.
    def test_inactive_worker_cannot_receive_chat_access(self):
        self.worker_profile.is_active_worker = False
        self.worker_profile.save(update_fields=["is_active_worker"])
        with self.assertRaises(ValidationError):
            grant_chat_responder_access(self.worker, self.admin)

    # Verify that customer cannot receive chat access. The required outcome is raises
    # ValidationError.
    def test_customer_cannot_receive_chat_access(self):
        with self.assertRaises(ValidationError):
            grant_chat_responder_access(self.customer, self.admin)

    # Verify that grant and revoke create safe audit events. The required outcome is events count is
    # 2 and serialised.lower() omits 'customer message'.
    def test_grant_and_revoke_create_safe_audit_events(self):
        grant_chat_responder_access(self.worker, self.admin)
        revoke_chat_responder_access(self.worker, self.admin)
        events = AuditEvent.objects.filter(event_type__startswith="chat_responder")
        self.assertEqual(events.count(), 2)
        serialised = " ".join(
            f"{event.summary} {event.before_data} {event.after_data}" for event in events
        )
        self.assertNotIn("customer message", serialised.lower())

    # Verify that demoting worker removes chat access. The required outcome is self.worker
    # membership in CHAT_RESPONDER_GROUP does not exist and
    # can_respond_to_customer_chat(self.worker) is false.
    def test_demoting_worker_removes_chat_access(self):
        grant_chat_responder_access(self.worker, self.admin)
        demote_worker(self.worker, self.admin)
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.groups.filter(name=CHAT_RESPONDER_GROUP).exists())
        self.assertFalse(can_respond_to_customer_chat(self.worker))

    # Verify that management user action grants chat access. The admin sends POST to
    # management:management_user_action; the required outcome is HTTP 302 and self.worker membership
    # in CHAT_RESPONDER_GROUP exists.
    def test_management_user_action_grants_chat_access(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse(
                "management:management_user_action",
                args=[self.worker.pk, "grant_chat"],
            ),
            {"confirmation": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.worker.groups.filter(name=CHAT_RESPONDER_GROUP).exists()
        )


# This group of tests protects the chat unread and navigation tests behaviour as one related
# customer or staff workflow.
# Shared setup keeps each scenario focused on the business rule being checked.
class ChatUnreadAndNavigationTests(ChatTestBase):
    # Verify that unread state is independent for each responder. The required outcome is
    # unread_chat_count(self.worker) equals 1, unread_chat_count(self.other_worker) equals 1, and
    # unread_chat_count(self.worker) equals 0.
    def test_unread_state_is_independent_for_each_responder(self):
        chat, _ = add_customer_message(customer=self.customer, body="Hello")
        self.delegate_chat(self.worker)
        self.delegate_chat(self.other_worker)
        self.assertEqual(unread_chat_count(self.worker), 1)
        self.assertEqual(unread_chat_count(self.other_worker), 1)
        mark_chat_read(chat=chat, user=self.worker)
        self.assertEqual(unread_chat_count(self.worker), 0)
        self.assertEqual(unread_chat_count(self.other_worker), 1)

    # Verify that staff reply is unread for customer until opened. The customer sends GET to
    # communications:customer_panel; the required outcome is unread_chat_count(self.customer) equals
    # 1 and unread_chat_count(self.customer) equals 0.
    def test_staff_reply_is_unread_for_customer_until_opened(self):
        chat, _ = add_customer_message(customer=self.customer, body="Hello")
        self.delegate_chat()
        add_staff_message(chat_id=chat.pk, responder=self.worker, body="Reply")
        self.assertEqual(unread_chat_count(self.customer), 1)
        self.client.force_login(self.customer)
        self.client.get(reverse("communications:customer_panel"))
        self.assertEqual(unread_chat_count(self.customer), 0)

    # Verify that customer page contains launcher but staff page does not. The admin sends GET to
    # core:core_home; the required outcome is renders 'data-chat-launcher' and does not expose
    # 'data-chat-launcher'.
    def test_customer_page_contains_launcher_but_staff_page_does_not(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("core:core_home"))
        self.assertContains(response, "data-chat-launcher")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:core_home"))
        self.assertNotContains(response, "data-chat-launcher")

    # Verify that customer account menu contains messages. The customer sends GET to core:core_home;
    # the required outcome is contains a link to communications:customer_chat.
    def test_customer_account_menu_contains_messages(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("core:core_home"))
        self.assertContains(response, reverse("communications:customer_chat"))

    # Verify that chat responder navigation shows messages not bookings. The worker sends GET to
    # communications:management_inbox; the required outcome is renders '> Messages' and does not
    # expose '> Bookings'.
    def test_chat_responder_navigation_shows_messages_not_bookings(self):
        self.delegate_chat()
        self.client.force_login(self.worker)
        response = self.client.get(reverse("communications:management_inbox"))
        self.assertContains(response, "> Messages")
        self.assertNotContains(response, "> Bookings")

    # Verify that a customer with chat messages reports customer chat history as a deletion blocker,
    # preventing safe-deletion workflows from removing the account.
    def test_chat_history_blocks_safe_customer_deletion(self):
        add_customer_message(customer=self.customer, body="Keep this")
        self.assertIn("customer chat history", customer_delete_blockers(self.customer))
