/*
 * This script adds focused conveniences to the custom management panel without replacing the server-side forms and permissions that remain authoritative.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

/*
 * Management panel interactions
 *
 * Essential links and forms work without JavaScript. This file adds a mobile
 * drawer, theme preference, image preview, and duplicate-submit protection.
 */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    const sidebar = document.querySelector("[data-management-sidebar]");
    const sidebarToggle = document.querySelector("[data-management-sidebar-toggle]");
    const backdrop = document.querySelector("[data-management-backdrop]");
    const themeToggle = document.querySelector("#management-theme-toggle");
    const storageKey = "popadoo-theme";

    // This helper updates sidebar open while keeping the underlying server-owned data unchanged.
    const setSidebarOpen = (open) => {
        if (!sidebar || !sidebarToggle || !backdrop) {
            return;
        }
        sidebar.dataset.open = String(open);
        sidebarToggle.setAttribute("aria-expanded", String(open));
        backdrop.hidden = !open;
        document.body.style.overflow = open ? "hidden" : "";
    };

    // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
    sidebarToggle?.addEventListener("click", () => {
        setSidebarOpen(sidebar?.dataset.open !== "true");
    });
    // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
    backdrop?.addEventListener("click", () => setSidebarOpen(false));
    // This listener responds to the keydown event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && sidebar?.dataset.open === "true") {
            setSidebarOpen(false);
            sidebarToggle?.focus();
        }
    });

    // This helper updates theme toggle while keeping the underlying server-owned data unchanged.
    const updateThemeToggle = () => {
        if (!themeToggle) {
            return;
        }
        const dark = document.documentElement.dataset.theme === "dark";
        themeToggle.setAttribute("aria-checked", String(dark));
        themeToggle.setAttribute(
            "aria-label",
            dark ? "Switch to light mode" : "Switch to dark mode"
        );
    };

    // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
    themeToggle?.addEventListener("click", () => {
        const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        try {
            window.localStorage.setItem(storageKey, next);
        } catch (error) {
            /* Theme switching still works for this page when storage is blocked. */
        }
        updateThemeToggle();
    });
    updateThemeToggle();

    document.querySelectorAll("form[data-prevent-double-submit]").forEach((form) => {
        // This listener responds to the submit event and keeps the enhanced interface aligned with the visitor’s action.
        form.addEventListener("submit", () => {
            const button = form.querySelector('button[type="submit"]');
            if (!button) {
                return;
            }
            button.disabled = true;
            button.classList.add("is-submitting");
            button.dataset.originalText = button.textContent;
            button.textContent = "Saving…";
        });
    });

    document.querySelectorAll('input[type="file"]').forEach((input) => {
        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        input.addEventListener("change", () => {
            const file = input.files?.[0];
            const card = input.closest("form")?.querySelector("[data-image-preview]");
            const output = card?.querySelector("[data-image-preview-output]");
            const placeholder = card?.querySelector("[data-image-preview-placeholder]");
            if (!file || !output) {
                return;
            }
            if (!file.type.startsWith("image/")) {
                return;
            }
            const reader = new FileReader();
            // This listener responds to the load event and keeps the enhanced interface aligned with the visitor’s action.
            reader.addEventListener("load", () => {
                output.src = String(reader.result);
                output.hidden = false;
                placeholder?.setAttribute("hidden", "");
            });
            reader.readAsDataURL(file);
        });
    });

    const errorSummary = document.querySelector("[data-error-summary]");
    if (errorSummary) {
        errorSummary.focus();
    }
})();
