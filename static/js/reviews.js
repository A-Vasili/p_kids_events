/*
 * This script improves the review experience with clearer live feedback while the normal form remains available and the server still decides what may be published.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    const form = document.querySelector("[data-review-form]");
    if (!form) return;

    const status = form.querySelector("[data-review-status]");
    const submit = form.querySelector("[data-review-submit]");
    const csrf = form.querySelector("input[name='csrfmiddlewaretoken']");
    const nameSection = form.querySelector("[data-testimonial-name-section]");
    const visibilityInputs = Array.from(
        form.querySelectorAll("input[name='visibility']")
    );

    // This helper carries out selected visibility for the visitor-facing interaction managed by this script.
    const selectedVisibility = () => (
        visibilityInputs.find((input) => input.checked)?.value || "private"
    );

    // This helper updates name section while keeping the underlying server-owned data unchanged.
    const updateNameSection = () => {
        if (!nameSection) return;
        const isTestimonial = selectedVisibility() === "testimonial";
        nameSection.hidden = !isTestimonial;
        nameSection.setAttribute("aria-hidden", String(!isTestimonial));
    };

    visibilityInputs.forEach((input) => {
        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        input.addEventListener("change", updateNameSection);
    });
    updateNameSection();

    if (!window.fetch) return;

    // This helper updates status while keeping the underlying server-owned data unchanged.
    const showStatus = (message, kind) => {
        status.hidden = false;
        status.className = `review-alert ${kind}`;
        status.textContent = message;
        status.focus();
    };

    // This helper carries out clear errors for the visitor-facing interaction managed by this script.
    const clearErrors = () => {
        form.querySelectorAll("[data-error-for]").forEach((node) => {
            node.replaceChildren();
        });
        form.querySelectorAll("[aria-invalid='true']").forEach((node) => {
            node.removeAttribute("aria-invalid");
        });
    };

    // This listener responds to the submit event and keeps the enhanced interface aligned with the visitor’s action.
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearErrors();
        submit.disabled = true;
        submit.textContent = "Saving…";

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                credentials: "same-origin",
                headers: {
                    "X-CSRFToken": csrf.value,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
            });
            const payload = await response.json();

            if (!response.ok) {
                Object.entries(payload.errors || {}).forEach(([name, messages]) => {
                    const escapedName = CSS.escape(name);
                    const container = form.querySelector(
                        `[data-error-for='${escapedName}']`
                    );
                    const field = form.querySelector(`[name='${escapedName}']`);
                    if (container) container.textContent = messages.join(" ");
                    if (field) field.setAttribute("aria-invalid", "true");
                });
                updateNameSection();
                showStatus(
                    payload.message || "The review could not be saved.",
                    "error"
                );
                return;
            }

            const packageStats = payload.stats?.package;
            const packageSummary = form.querySelector(
                "[data-package-rating-summary]"
            );
            if (packageSummary && packageStats) {
                packageSummary.textContent = packageStats.count
                    ? `Community average: ${packageStats.average.toFixed(1)} / 5 from ${packageStats.count} review${packageStats.count === 1 ? "" : "s"}.`
                    : "No verified package ratings yet.";
            }

            Object.entries(payload.stats?.addons || {}).forEach(
                ([addonId, addonStats]) => {
                    const summary = form.querySelector(
                        `[data-addon-rating-summary='${CSS.escape(addonId)}']`
                    );
                    if (summary) {
                        summary.textContent = addonStats.count
                            ? `Community average: ${addonStats.average.toFixed(1)} / 5 from ${addonStats.count} review${addonStats.count === 1 ? "" : "s"}.`
                            : "No verified ratings yet.";
                    }
                }
            );

            showStatus(payload.message, "success");
        } catch (_error) {
            showStatus(
                "The review could not be sent. Please try the normal form again.",
                "error"
            );
        } finally {
            submit.disabled = false;
            submit.textContent = "Save review";
        }
    });
})();
