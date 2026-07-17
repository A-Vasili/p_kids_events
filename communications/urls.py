# This file maps readable website addresses to the part of Popadoo responsible for answering each
# request.
# The route order also protects specialised management and messaging paths from being swallowed by
# broader URL groups.
# It contains no page logic; the matched view performs the actual work.
from django.urls import path

from . import views

app_name = "communications"

# These named routes connect stable website addresses to the views that handle each customer or
# staff request.
# Permission checks remain inside the views, so knowing an address never grants access by itself.
urlpatterns = [
    path("accounts/messages/", views.CustomerChatView.as_view(), name="customer_chat"),
    path("accounts/messages/send/", views.CustomerSendView.as_view(), name="customer_send"),
    path("accounts/messages/panel/", views.CustomerPanelView.as_view(), name="customer_panel"),
    path("accounts/messages/refresh/", views.CustomerRefreshView.as_view(), name="customer_refresh"),
    path("accounts/messages/send-widget/", views.CustomerWidgetSendView.as_view(), name="customer_widget_send"),
    path("management/messages/", views.ManagementInboxView.as_view(), name="management_inbox"),
    path("management/messages/<uuid:public_id>/", views.ManagementChatView.as_view(), name="management_chat"),
    path("management/messages/<uuid:public_id>/reply/", views.ManagementReplyView.as_view(), name="management_reply"),
]
