/*
 * This script progressively enhances the bottom-right customer chat link into an on-page panel, while the full-page chat remains available when JavaScript is absent.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

/* Progressive enhancement for the floating chat link. The normal link and
 * full-page form remain usable when this script is unavailable. */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    const widget = document.querySelector("[data-chat-widget]");
    if (!widget) {
        return;
    }

    const launcher = widget.querySelector("[data-chat-launcher]");
    const panel = widget.querySelector("[data-chat-panel]");
    const panelBody = widget.querySelector("[data-chat-panel-body]");
    const closeButton = widget.querySelector("[data-chat-close]");
    const liveRegion = widget.querySelector("[data-chat-live]");
    const badge = widget.querySelector("[data-chat-badge]");
    const authenticated = widget.dataset.authenticated === "true";
    let pollTimer = null;
    let requestInFlight = false;
    let loaded = false;
    let lastActivity = "";

    const translations = window.popadooTranslations || {};
    // This helper carries out language for the visitor-facing interaction managed by this script.
    const language = () => document.documentElement.lang || "en";
    // This helper carries out translate for the visitor-facing interaction managed by this script.
    const translate = (key) => translations?.[language()]?.[key] ?? translations?.en?.[key] ?? key;

    // This helper updates translations while keeping the underlying server-owned data unchanged.
    const applyTranslations = (root) => {
        root.querySelectorAll("[data-i18n]").forEach((element) => {
            element.textContent = translate(element.dataset.i18n);
        });
        ["aria-label", "placeholder", "title"].forEach((attribute) => {
            root.querySelectorAll(`[data-i18n-${attribute}]`).forEach((element) => {
                element.setAttribute(attribute, translate(element.getAttribute(`data-i18n-${attribute}`)));
            });
        });
    };

    // This helper updates badge while keeping the underlying server-owned data unchanged.
    const updateBadge = (count) => {
        if (!badge) {
            return;
        }
        const safeCount = Number.parseInt(count, 10) || 0;
        badge.hidden = safeCount < 1;
        const visible = badge.querySelector("[aria-hidden='true']");
        const hidden = badge.querySelector(".visually-hidden");
        if (visible) {
            visible.textContent = String(safeCount);
        }
        if (hidden) {
            hidden.textContent = `${safeCount} ${translate(safeCount === 1 ? "chat.unreadMessage" : "chat.unreadMessages")}`;
        }
    };

    // This helper carries out scroll to latest for the visitor-facing interaction managed by this script.
    const scrollToLatest = () => {
        panelBody.querySelector("[data-chat-thread] li:last-child")?.scrollIntoView({ block: "end" });
    };

    // This helper updates panel while keeping the underlying server-owned data unchanged.
    const replacePanel = (html) => {
        // This HTML is produced by Django templates, where message text is
        // escaped. Raw browser-supplied text is never inserted directly.
        panelBody.innerHTML = html;
        applyTranslations(panelBody);
        const content = panelBody.querySelector("[data-chat-panel-content]");
        if (content?.dataset.lastMessageAt) {
            lastActivity = content.dataset.lastMessageAt;
        }
        scrollToLatest();
    };

    // This helper reads the page’s CSRF token so enhanced form requests receive the same protection as normal Django submissions.
    const csrfToken = () => panelBody.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";

    // This helper requests or submits panel and reports failure without pretending the server accepted the action.
    const loadPanel = async (refresh = false) => {
        if (!authenticated || requestInFlight) {
            return;
        }
        requestInFlight = true;
        try {
            const url = refresh ? widget.dataset.refreshUrl : widget.dataset.panelUrl;
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (response.status === 401 || response.status === 403) {
                window.location.assign(launcher.href);
                return;
            }
            if (!response.ok) {
                throw new Error("Chat request failed");
            }
            if (refresh) {
                const data = await response.json();
                updateBadge(data.unread_count);
                if (data.last_message_at && data.last_message_at === lastActivity) {
                    return;
                }
                const previousActivity = lastActivity;
                const currentTextarea = panelBody.querySelector("textarea[name='message']");
                const draft = currentTextarea?.value || "";
                const restoreFocus = document.activeElement === currentTextarea;
                replacePanel(data.html);
                const replacementTextarea = panelBody.querySelector("textarea[name='message']");
                if (replacementTextarea && draft) {
                    replacementTextarea.value = draft;
                    if (restoreFocus) {
                        replacementTextarea.focus();
                    }
                }
                if (data.last_message_at && previousActivity && data.last_message_at !== previousActivity) {
                    liveRegion.textContent = translate("chat.newMessagesReceived");
                }
                lastActivity = data.last_message_at || lastActivity;
            } else {
                replacePanel(await response.text());
                updateBadge(0);
                loaded = true;
            }
        } catch (error) {
            liveRegion.textContent = translate("chat.connectionLost");
        } finally {
            requestInFlight = false;
        }
    };

    // This helper controls polling so background work runs only while it is useful to the visitor.
    const stopPolling = () => {
        if (pollTimer) {
            window.clearInterval(pollTimer);
            pollTimer = null;
        }
    };

    // This helper controls polling so background work runs only while it is useful to the visitor.
    const startPolling = () => {
        stopPolling();
        if (!authenticated || panel.hidden || document.hidden) {
            return;
        }
        // Poll only while useful so closed panels do not create background load.
        pollTimer = window.setInterval(() => loadPanel(true), 18000);
    };

    // This helper changes panel while keeping keyboard focus and visible state in step for accessibility.
    const openPanel = () => {
        panel.hidden = false;
        launcher.setAttribute("aria-expanded", "true");
        closeButton.focus();
        if (authenticated && !loaded) {
            loadPanel(false);
        }
        startPolling();
    };

    // This helper changes panel while keeping keyboard focus and visible state in step for accessibility.
    const closePanel = (restoreFocus = true) => {
        panel.hidden = true;
        launcher.setAttribute("aria-expanded", "false");
        stopPolling();
        if (restoreFocus) {
            launcher.focus();
        }
    };

    // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
    launcher.addEventListener("click", (event) => {
        event.preventDefault();
        panel.hidden ? openPanel() : closePanel();
    });
    // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
    closeButton.addEventListener("click", () => closePanel());
    // This listener responds to the keydown event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !panel.hidden) {
            closePanel();
        }
    });
    // This listener responds to the visibilitychange event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("visibilitychange", () => {
        document.hidden ? stopPolling() : startPolling();
    });
    // This listener responds to the popadoo:language-applied event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("popadoo:language-applied", () => applyTranslations(widget));

    // This listener responds to the submit event and keeps the enhanced interface aligned with the visitor’s action.
    panelBody.addEventListener("submit", async (event) => {
        const form = event.target.closest("[data-widget-form]");
        if (!form) {
            return;
        }
        event.preventDefault();
        if (requestInFlight) {
            return;
        }
        const textarea = form.querySelector("textarea[name='message']");
        const submit = form.querySelector("[data-chat-submit]");
        const originalMessage = textarea?.value || "";
        requestInFlight = true;
        submit.disabled = true;
        submit.textContent = translate("chat.sending");
        try {
            const response = await fetch(widget.dataset.sendUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: new FormData(form),
            });
            const data = await response.json();
            replacePanel(data.html);
            updateBadge(data.unread_count);
            if (!response.ok || !data.ok) {
                const replacement = panelBody.querySelector("textarea[name='message']");
                if (replacement && !replacement.value) {
                    replacement.value = originalMessage;
                }
                liveRegion.textContent = translate("chat.sendError");
            } else {
                liveRegion.textContent = translate("chat.sent");
            }
        } catch (error) {
            textarea.value = originalMessage;
            liveRegion.textContent = translate("chat.sendError");
        } finally {
            requestInFlight = false;
            const currentSubmit = panelBody.querySelector("[data-chat-submit]");
            if (currentSubmit) {
                currentSubmit.disabled = false;
                currentSubmit.textContent = translate("chat.send");
            }
        }
    });

    applyTranslations(widget);
})();
