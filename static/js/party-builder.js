/*
 * This script updates the Make Your Own Party page as customers select packages and experiences, while all final prices and eligibility checks are recalculated by Django.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

/*
 * The server remains responsible for validation and pricing. This file only
 * makes the builder faster to explore by updating visible choices and totals.
 */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    const currencyFormatter = new Intl.NumberFormat("en-IE", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 2,
    });
    // This helper carries out to number for the visitor-facing interaction managed by this script.
    const toNumber = (value) => Number.parseFloat(value || "0") || 0;
    // This helper carries out active language for the visitor-facing interaction managed by this script.
    const activeLanguage = () => document.documentElement.lang || "en";
    // This helper carries out translate for the visitor-facing interaction managed by this script.
    const translate = (key) => {
        const language = activeLanguage();
        return window.popadooTranslations?.[language]?.[key]
            ?? window.popadooTranslations?.en?.[key]
            ?? key;
    };
    // This helper carries out optional translation for the visitor-facing interaction managed by this script.
    const optionalTranslation = (key) => {
        const language = activeLanguage();
        return window.popadooTranslations?.[language]?.[key]
            ?? window.popadooTranslations?.en?.[key]
            ?? null;
    };
    // This helper carries out interpolate for the visitor-facing interaction managed by this script.
    const interpolate = (template, values = {}) => Object.entries(values).reduce(
        (text, [name, value]) => text.replaceAll(`{${name}}`, String(value ?? "")),
        template
    );
    // This helper carries out catalogue text for the visitor-facing interaction managed by this script.
    const catalogueText = (kind, slug, field, fallback = "") => {
        if (!slug) return fallback;
        return optionalTranslation(`catalogue.${kind}.${slug}.${field}`) ?? fallback;
    };
    // This helper carries out recommendation reason text for the visitor-facing interaction managed by this script.
    const recommendationReasonText = (element) => {
        const key = element.dataset.recommendationReasonKey;
        if (!key) return element.textContent;
        const addonName = catalogueText(
            "addon",
            element.dataset.recommendationAddonSlug,
            "name",
            element.dataset.recommendationAddonName
        );
        const packageName = catalogueText(
            "package",
            element.dataset.recommendationPackageSlug,
            "name",
            element.dataset.recommendationPackageName
        );
        return interpolate(translate(key), {
            addon: addonName,
            package: packageName,
            count: element.dataset.recommendationCount,
        });
    };
    // This helper updates builder translations while keeping the underlying server-owned data unchanged.
    const applyBuilderTranslations = (root = document) => {
        root.querySelectorAll("[data-catalogue-i18n]").forEach((element) => {
            if (!element.dataset.catalogueOriginal) {
                element.dataset.catalogueOriginal = element.textContent;
            }
            element.textContent = optionalTranslation(element.dataset.catalogueI18n)
                ?? element.dataset.catalogueOriginal;
        });
        root.querySelectorAll("[data-recommendation-reason-key]").forEach((element) => {
            element.textContent = recommendationReasonText(element);
        });
        root.querySelectorAll("[data-i18n-aria-label][data-i18n-value-rating]").forEach((element) => {
            element.setAttribute("aria-label", interpolate(translate(element.dataset.i18nAriaLabel), {
                rating: element.dataset.i18nValueRating,
                count: element.dataset.i18nValueCount,
            }));
        });
    };

    const optionsForm = document.querySelector("[data-party-options-form]");
    if (optionsForm) {
        const packageRadios = Array.from(optionsForm.querySelectorAll("[data-package-radio]"));
        const addonCheckboxes = Array.from(optionsForm.querySelectorAll("[data-addon-checkbox]"));
        const addonOptions = Array.from(optionsForm.querySelectorAll("[data-addon-option]"));
        const recommendationSection = document.querySelector("[data-recommendations]");
        const recommendationList = recommendationSection?.querySelector("[data-recommendation-list]");
        const selectedPackageName = document.querySelector("[data-selected-package-name]");
        const selectedPackageCapacity = document.querySelector("#selected-package-capacity");
        const selectedPackagePrice = document.querySelector("#selected-package-price");
        const addonSummary = document.querySelector("#selected-addon-summary");
        const emptySummary = document.querySelector("#summary-empty");
        const totalOutput = document.querySelector("#party-total");
        const liveStatus = document.querySelector("#builder-live-status");
        let recommendationController = null;

        // This helper carries out selected package for the visitor-facing interaction managed by this script.
        const selectedPackage = () => packageRadios.find((radio) => radio.checked);
        // This helper carries out selected package id for the visitor-facing interaction managed by this script.
        const selectedPackageId = () => selectedPackage()?.value || "";

        // This helper updates choice labels while keeping the underlying server-owned data unchanged.
        const updateChoiceLabels = () => {
            packageRadios.forEach((radio) => {
                const action = radio.closest(".package-option")?.querySelector("[data-package-action]");
                if (action) {
                    const key = radio.checked ? "builder.selectedPackage" : "builder.choosePackageAction";
                    action.dataset.i18n = key;
                    action.textContent = translate(key);
                }
            });
            addonCheckboxes.forEach((checkbox) => {
                const action = checkbox.closest(".addon-option")?.querySelector("[data-addon-action]");
                if (action) {
                    const key = checkbox.checked ? "builder.addedRemove" : "builder.addExperience";
                    action.dataset.i18n = key;
                    action.textContent = translate(key);
                }
            });
        };

        // This helper updates cart while keeping the underlying server-owned data unchanged.
        const renderCart = ({ announce = false } = {}) => {
            const packageChoice = selectedPackage();
            // This helper carries out selected addons for the visitor-facing interaction managed by this script.
            const selectedAddons = addonCheckboxes.filter((checkbox) => checkbox.checked);
            const packagePrice = toNumber(packageChoice?.dataset.packagePrice);
            const addonTotal = selectedAddons.reduce(
                (total, checkbox) => total + toNumber(checkbox.dataset.addonPrice),
                0
            );
            const total = packagePrice + addonTotal;

            if (recommendationSection) recommendationSection.dataset.packageId = selectedPackageId();
            if (selectedPackageName) {
                selectedPackageName.textContent = packageChoice
                    ? catalogueText("package", packageChoice.dataset.packageSlug, "name", packageChoice.dataset.packageName)
                    : "";
                selectedPackageName.dataset.packageSlug = packageChoice?.dataset.packageSlug || "";
            }
            if (selectedPackageCapacity) {
                selectedPackageCapacity.textContent = packageChoice
                    ? translate("builder.upToChildren").replace(
                        "{count}",
                        packageChoice.dataset.packageCapacity
                    )
                    : translate("builder.choosePackage");
            }
            if (selectedPackagePrice) selectedPackagePrice.textContent = packageChoice ? currencyFormatter.format(packagePrice) : "—";
            if (totalOutput) totalOutput.textContent = packageChoice ? currencyFormatter.format(total) : "—";

            if (addonSummary) {
                addonSummary.replaceChildren();
                selectedAddons.forEach((checkbox) => {
                    const item = document.createElement("li");
                    const name = document.createElement("span");
                    const price = document.createElement("strong");
                    item.className = "summary-addon-item";
                    name.textContent = catalogueText(
                        "addon",
                        checkbox.dataset.addonSlug,
                        "name",
                        checkbox.dataset.addonName
                    );
                    price.textContent = currencyFormatter.format(toNumber(checkbox.dataset.addonPrice));
                    item.append(name, price);
                    addonSummary.append(item);
                });
            }
            if (emptySummary) emptySummary.hidden = selectedAddons.length > 0;
            updateChoiceLabels();
            if (announce && liveStatus) {
                liveStatus.textContent = packageChoice
                    ? translate("builder.partyUpdated")
                        .replace("{count}", String(selectedAddons.length))
                        .replace("{total}", currencyFormatter.format(total))
                    : translate("builder.choosePackage");
            }
        };

        // This helper carries out add keyboard navigation for the visitor-facing interaction managed by this script.
        const addKeyboardNavigation = (container, controls) => {
            // This listener responds to the keydown event and keeps the enhanced interface aligned with the visitor’s action.
            container?.addEventListener("keydown", (event) => {
                // This helper carries out visible controls for the visitor-facing interaction managed by this script.
                const visibleControls = controls.filter((control) => !control.closest("[hidden]"));
                const currentIndex = visibleControls.indexOf(event.target);
                if (currentIndex === -1) return;
                const destinations = {
                    ArrowRight: currentIndex + 1, ArrowDown: currentIndex + 1,
                    ArrowLeft: currentIndex - 1, ArrowUp: currentIndex - 1,
                    Home: 0, End: visibleControls.length - 1,
                };
                if (!(event.key in destinations)) return;
                event.preventDefault();
                const destination = (destinations[event.key] + visibleControls.length) % visibleControls.length;
                visibleControls[destination]?.focus();
            });
        };

        // This helper updates recommendations while keeping the underlying server-owned data unchanged.
        const renderRecommendations = (items) => {
            if (!recommendationList) return;
            recommendationList.replaceChildren();
            if (!items.length) {
                const empty = document.createElement("p");
                empty.dataset.i18n = "builder.noAdditionalSuggestions";
                empty.textContent = translate("builder.noAdditionalSuggestions");
                recommendationList.append(empty);
                return;
            }
            items.forEach((item) => {
                const card = document.createElement("article");
                card.className = "recommendation-card";
                const content = document.createElement("div");
                const footer = document.createElement("div");
                const heading = document.createElement("h3");
                const description = document.createElement("p");
                const reason = document.createElement("p");
                const price = document.createElement("strong");
                const button = document.createElement("button");
                content.className = "recommendation-card-content";
                footer.className = "recommendation-card-footer";
                heading.dataset.catalogueI18n = `catalogue.addon.${item.slug}.name`;
                heading.textContent = catalogueText("addon", item.slug, "name", item.name);
                description.className = "recommendation-description";
                description.dataset.catalogueI18n = `catalogue.addon.${item.slug}.description`;
                description.textContent = catalogueText("addon", item.slug, "description", item.short_description);
                reason.className = "recommendation-reason";
                reason.dataset.recommendationReasonKey = item.reason_key || "";
                reason.dataset.recommendationCount = item.reason_values?.count || "";
                reason.dataset.recommendationAddonName = item.reason_values?.addon_name || "";
                reason.dataset.recommendationAddonSlug = item.reason_values?.addon_slug || "";
                reason.dataset.recommendationPackageName = item.reason_values?.package_name || "";
                reason.dataset.recommendationPackageSlug = item.reason_values?.package_slug || "";
                reason.textContent = item.reason_key ? recommendationReasonText(reason) : item.reason;
                price.className = "recommendation-price";
                price.textContent = currencyFormatter.format(toNumber(item.price));
                button.type = "button";
                button.className = "button button-outline recommendation-action";
                button.dataset.i18n = "builder.selectExperience";
                button.textContent = translate("builder.selectExperience");
                // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
                button.addEventListener("click", () => {
                    const checkbox = optionsForm.querySelector(`[data-addon-checkbox][value='${CSS.escape(String(item.id))}']`);
                    if (checkbox && !checkbox.checked) {
                        checkbox.checked = true;
                        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                    checkbox?.focus();
                });
                content.append(heading, description, reason);
                footer.append(price, button);
                card.append(content, footer);
                recommendationList.append(card);
                applyBuilderTranslations(card);
            });
        };

        // This helper requests or submits recommendations and reports failure without pretending the server accepted the action.
        const refreshRecommendations = async () => {
            if (!recommendationSection || !recommendationList) return;
            recommendationController?.abort();
            recommendationController = new AbortController();
            const url = new URL(recommendationSection.dataset.endpoint, window.location.origin);
            url.searchParams.set("package", selectedPackageId());
            addonCheckboxes.filter((item) => item.checked).forEach((item) => url.searchParams.append("addons", item.value));
            try {
                const response = await fetch(url, { headers: { Accept: "application/json" }, signal: recommendationController.signal });
                if (response.ok) renderRecommendations((await response.json()).recommendations || []);
            } catch (error) {
                if (error.name !== "AbortError") {
                    // Server-rendered suggestions remain usable when the network is unavailable.
                }
            }
        };

        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        packageRadios.forEach((radio) => radio.addEventListener("change", () => {
            renderCart({ announce: true });
            refreshRecommendations();
        }));
        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        addonCheckboxes.forEach((checkbox) => checkbox.addEventListener("change", () => {
            renderCart({ announce: true });
            refreshRecommendations();
        }));

        const searchInput = optionsForm.querySelector("[data-addon-search]");
        const filterButtons = Array.from(optionsForm.querySelectorAll("[data-addon-filter]"));
        const filterStatus = optionsForm.querySelector("[data-addon-filter-status]");
        const filterEmpty = optionsForm.querySelector("[data-addon-filter-empty]");
        let activeCategory = "all";
        // This helper compares each experience with both its specific subcategory and its broader
        // parent. A broad choice such as Creative Activities therefore reveals all matching child
        // experiences instead of incorrectly reporting an empty result.
        const applyAddonFilter = () => {
            const term = (searchInput?.value || "").trim().toLocaleLowerCase();
            let visibleCount = 0;
            addonOptions.forEach((option) => {
                const slug = option.querySelector("[data-addon-checkbox]")?.dataset.addonSlug || "";
                const categorySlugs = (option.dataset.addonCategories || option.dataset.addonCategory || "")
                    .split(/\s+/)
                    .filter(Boolean);
                const translatedSearch = [
                    option.dataset.addonSearch,
                    catalogueText("addon", slug, "name"),
                    catalogueText("addon", slug, "description"),
                    ...categorySlugs.map((categorySlug) => optionalTranslation(`catalogue.category.${categorySlug}`)),
                ].filter(Boolean).join(" ").toLocaleLowerCase();
                const matchesText = !term || translatedSearch.includes(term);
                const matchesCategory = activeCategory === "all" || categorySlugs.includes(activeCategory);
                option.hidden = !(matchesText && matchesCategory);
                if (!option.hidden) visibleCount += 1;
            });
            if (filterStatus) {
                const key = visibleCount === 1 ? "builder.experienceShown" : "builder.experiencesShown";
                filterStatus.textContent = translate(key).replace("{count}", String(visibleCount));
            }
            if (filterEmpty) filterEmpty.hidden = visibleCount > 0;
        };
        // This listener responds to the input event and keeps the enhanced interface aligned with the visitor’s action.
        searchInput?.addEventListener("input", applyAddonFilter);
        // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
        filterButtons.forEach((button) => button.addEventListener("click", () => {
            activeCategory = button.dataset.addonFilter;
            filterButtons.forEach((item) => {
                const active = item === button;
                item.classList.toggle("active", active);
                item.setAttribute("aria-pressed", String(active));
            });
            applyAddonFilter();
        }));

        addKeyboardNavigation(optionsForm.querySelector("[data-package-grid]"), packageRadios);
        addKeyboardNavigation(optionsForm.querySelector("[data-addon-grid]"), addonCheckboxes);
        // This listener responds to the popadoo:language-applied event and keeps the enhanced interface aligned with the visitor’s action.
        document.addEventListener("popadoo:language-applied", () => {
            applyBuilderTranslations();
            applyAddonFilter();
            renderCart();
        });
        applyBuilderTranslations();
        applyAddonFilter();
        renderCart();
    }

    const cardNumberInput = document.querySelector("[data-card-number]");
    // This listener responds to the input event and keeps the enhanced interface aligned with the visitor’s action.
    cardNumberInput?.addEventListener("input", () => {
        const digits = cardNumberInput.value.replace(/\D/g, "").slice(0, 19);
        cardNumberInput.value = digits.replace(/(.{4})/g, "$1 ").trim();
    });

    const paymentForm = document.querySelector("[data-payment-form]");
    // This listener responds to the submit event and keeps the enhanced interface aligned with the visitor’s action.
    paymentForm?.addEventListener("submit", () => {
        const submitButton = paymentForm.querySelector("[data-checkout-submit]");
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = translate("builder.completingSimulation");
        }
    });
})();
