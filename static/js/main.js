/*
 * This script coordinates shared public-page behaviour, including language choice, theme preference, responsive navigation, and common form enhancements.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

/*
 * This script manages shared browser behaviour such as language choice, theme changes, navigation, and booking-form enhancements.
 * These comments explain the browser-side steps without changing the JavaScript behaviour.
 */

/*
 * Main site behavior.
 * Handles language switching, theme toggling, responsive navigation, and the
 * booking-form workflow shared across the Popadoo pages.
 */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    /* Global configuration, storage keys, and frequently used DOM references. */
    const translations = window.popadooTranslations;
    const supportedLanguages = Object.keys(translations ?? { en: {} });
    const languageStorageKey = "popadoo-language";
    const themeStorageKey = "popadoo-theme";
    const selectedPackageStorageKey = "popadoo-selected-package";
    const customPackageStorageKey = "popadoo-custom-package";
    const customPackageId = "custom-package";
    const navigationBreakpoint = window.matchMedia("(max-width: 72rem)");
    const navigationToggle = document.querySelector(".site-navigation-toggle");
    const navigationMenu = document.querySelector("#primary-navigation");
    const languageSelector = document.querySelector("#language-selector");
    const themeToggle = document.querySelector("#theme-toggle");
    const themeStatus = document.querySelector("[data-theme-status]");
    const metaDescription = document.querySelector('meta[name="description"]');
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    const bookingForm = document.querySelector("#booking-form");
    const bookingConfirmation = document.querySelector("#booking-confirmation");
    const bookingClearButton = document.querySelector("#booking-clear");
    const bookingName = document.querySelector("#booking-name");
    const bookingEmail = document.querySelector("#booking-email");
    const bookingPhone = document.querySelector("#booking-phone");
    const bookingDate = document.querySelector("#booking-date");
    const bookingTime = document.querySelector("#booking-time");
    const bookingGuests = document.querySelector("#booking-guest-count");
    const bookingPackage = document.querySelector("#booking-package");
    const bookingDetails = document.querySelector("#booking-details");
    const bookingPostalCode = document.querySelector("#booking-postal-code");

    /* currentLanguage drives translations, localized links, and validation messages. */
    let currentLanguage = "en";

    /* Safe localStorage wrappers keep preferences optional when browser storage is blocked. */
    // This helper reads stored value so later screen updates use the same fallback rules.
    const getStoredValue = (key) => {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    };

    // This function handles the store value part of the browser interaction.
    // This helper carries out store value for the visitor-facing interaction managed by this script.
    const storeValue = (key, value) => {
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            /* Preferences still work for the current page when storage is blocked. */
        }
    };

    /* Small validation helpers for language and package values. */
    // This helper checks supported language before the interface continues with the related action.
    const isSupportedLanguage = (language) => supportedLanguages.includes(language);

    // This function handles the has select option part of the browser interaction.
    // This helper checks select option before the interface continues with the related action.
    const hasSelectOption = (selectElement, value) => {
        return Boolean(selectElement)
            && Array.from(selectElement.options).some((option) => option.value === value);
    };

    // This function reads or prepares url language for the next step.
    // This helper reads url language so later screen updates use the same fallback rules.
    const getUrlLanguage = () => {
        const language = new URLSearchParams(window.location.search).get("lang");
        return isSupportedLanguage(language) ? language : null;
    };

    // This function reads or prepares url package for the next step.
    // This helper reads url package so later screen updates use the same fallback rules.
    const getUrlPackage = () => {
        const packageId = new URLSearchParams(window.location.search).get("package");
        return packageId && hasSelectOption(bookingPackage, packageId)
            ? packageId
            : null;
    };

    /* Translate a key in the active language, falling back to English and then the key. */
    // This helper carries out translate for the visitor-facing interaction managed by this script.
    const translate = (key) => {
        return translations?.[currentLanguage]?.[key]
            ?? translations?.en?.[key]
            ?? key;
    };

    /* Keep navigation toggle labels accurate for screen-reader users. */
    // This helper updates navigation toggle label while keeping the underlying server-owned data unchanged.
    const updateNavigationToggleLabel = () => {
        if (!navigationToggle) {
            return;
        }

        const isOpen = navigationToggle.getAttribute("aria-expanded") === "true";
        navigationToggle.setAttribute(
            "aria-label",
            translate(isOpen ? "nav.closeMenu" : "nav.openMenu")
        );
    };

    /* Synchronize theme controls, status text, and browser theme-color metadata. */
    // This helper updates theme control while keeping the underlying server-owned data unchanged.
    const updateThemeControl = () => {
        if (!themeToggle) {
            return;
        }

        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        themeToggle.setAttribute("aria-checked", String(isDark));
        themeToggle.setAttribute(
            "aria-label",
            translate(isDark ? "theme.switchToLight" : "theme.switchToDark")
        );

        if (themeStatus) {
            themeStatus.textContent = translate(isDark ? "theme.dark" : "theme.light");
        }

        if (themeColorMeta) {
            themeColorMeta.setAttribute("content", isDark ? "#15111c" : "#fff9fc");
        }
    };

    // This function handles the should localize href part of the browser interaction.
    // This helper checks localize href before the interface continues with the related action.
    const shouldLocalizeHref = (href) => {
        return href
            && !href.startsWith("#")
            && !href.startsWith("mailto:")
            && !href.startsWith("tel:")
            && !href.startsWith("javascript:");
    };

    // This function reads or prepares relative localized href for the next step.
    // This helper reads relative localized href so later screen updates use the same fallback rules.
    const getRelativeLocalizedHref = (url) => {
        return `${url.pathname}${url.search}${url.hash}`;
    };

    /*
     * Keep language state portable between pages.
     * localStorage remains the main preference store, while a lang query
     * parameter is added to internal links as a fallback for browsers that block
     * storage or users who open pages directly from a translated URL.
     */
    // This helper updates internal language links while keeping the underlying server-owned data unchanged.
    const updateInternalLanguageLinks = () => {
        document.querySelectorAll("a[href]").forEach((link) => {
            const originalHref = link.getAttribute("href");

            if (!shouldLocalizeHref(originalHref)) {
                return;
            }

            const url = new URL(originalHref, window.location.href);

            if (url.origin !== window.location.origin) {
                return;
            }

            url.searchParams.set("lang", currentLanguage);
            link.setAttribute("href", getRelativeLocalizedHref(url));
        });
    };

    // This function refreshes current url language so the page matches the latest user choice.
    // This helper updates current url language while keeping the underlying server-owned data unchanged.
    const updateCurrentUrlLanguage = () => {
        const url = new URL(window.location.href);
        url.searchParams.set("lang", currentLanguage);
        window.history.replaceState({}, "", getRelativeLocalizedHref(url));
    };

    /* Convert a Date to the yyyy-mm-dd format expected by date inputs. */
    // This helper carries out format date for input for the visitor-facing interaction managed by this script.
    const formatDateForInput = (date) => {
        const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
        return localDate.toISOString().slice(0, 10);
    };

    // This function applies default booking values in one consistent place.
    // This helper updates default booking values while keeping the underlying server-owned data unchanged.
    const setDefaultBookingValues = () => {
        /* A late-afternoon default makes the time field useful without forcing a choice. */
        if (bookingTime && !bookingTime.value) {
            bookingTime.value = "16:00";
        }

        if (bookingGuests && !bookingGuests.value) {
            bookingGuests.value = "10";
        }
    };

    /* Read the custom package built on packages.html, ignoring malformed stored data. */
    // This helper reads custom package so later screen updates use the same fallback rules.
    const getCustomPackage = () => {
        try {
            const customPackage = JSON.parse(getStoredValue(customPackageStorageKey) ?? "null");
            return customPackage?.id === customPackageId && Array.isArray(customPackage.characteristics)
                ? customPackage
                : null;
        } catch (error) {
            return null;
        }
    };

    /* Format custom-package characteristics as booking-form notes. */
    // This helper carries out build custom package details for the visitor-facing interaction managed by this script.
    const buildCustomPackageDetails = (customPackage) => {
        const characteristics = customPackage?.characteristics
            ?.map((characteristic) => translate(characteristic.labelKey))
            ?.filter(Boolean) ?? [];

        if (characteristics.length === 0) {
            return "";
        }

        return [
            translate("contact.customPackageDetailsIntro"),
            ...characteristics.map((characteristic) => `- ${characteristic}`)
        ].join("\n");
    };

    // This function applies custom package details to the current page.
    // This helper updates custom package details while keeping the underlying server-owned data unchanged.
    const applyCustomPackageDetails = () => {
        if (!bookingDetails || bookingPackage?.value !== customPackageId) {
            return;
        }

        const details = buildCustomPackageDetails(getCustomPackage());

        if (!details) {
            return;
        }

        /*
         * Custom package details are prefilled only when the box is empty or
         * when the previous value was auto-generated. User-written notes are
         * left untouched.
         */
        if (!bookingDetails.value.trim() || bookingDetails.dataset.autoCustomPackage === "true") {
            bookingDetails.value = details;
            bookingDetails.dataset.autoCustomPackage = "true";
        }
    };

    // This function applies selected package to booking form to the current page.
    // This helper updates selected package to booking form while keeping the underlying server-owned data unchanged.
    const applySelectedPackageToBookingForm = () => {
        if (!bookingPackage) {
            return;
        }

        /*
         * Package selections made on packages.html are carried here through a
         * URL parameter and localStorage. The URL wins so the newest clicked
         * package always fills the booking form first.
         */
        const selectedPackage = getUrlPackage() ?? getStoredValue(selectedPackageStorageKey);

        if (selectedPackage && hasSelectOption(bookingPackage, selectedPackage)) {
            bookingPackage.value = selectedPackage;
            storeValue(selectedPackageStorageKey, selectedPackage);
            applyCustomPackageDetails();
        }
    };

    // This function handles the hide booking confirmation part of the browser interaction.
    // This helper updates booking confirmation while keeping the underlying server-owned data unchanged.
    const hideBookingConfirmation = () => {
        if (bookingConfirmation && !bookingConfirmation.hidden) {
            bookingConfirmation.hidden = true;
        }
    };

    // This function returns booking form to its starting state.
    // This helper carries out clear booking form for the visitor-facing interaction managed by this script.
    const clearBookingForm = ({ preserveConfirmation = false } = {}) => {
        if (!bookingForm) {
            return;
        }

        /*
         * Clear returns the booking form to a neutral empty state without
         * showing validation errors. Required fields are checked again only
         * when the visitor submits a new reservation request.
         */
        bookingForm.reset();
        bookingForm.querySelectorAll("input, select, textarea").forEach((field) => {
            if (field.type === "checkbox" || field.type === "radio") {
                field.checked = false;
                return;
            }

            field.value = "";
            field.setCustomValidity("");
        });
        bookingForm.classList.remove("was-validated");
        document.dispatchEvent(new CustomEvent("popadoo:booking-form-reset"));

        if (!preserveConfirmation) {
            hideBookingConfirmation();
        }
    };

    /* Apply localized custom validity messages before native form validation runs. */
    // This helper checks booking fields before the interface continues with the related action.
    const validateBookingFields = () => {
        const validators = [
            {
                field: bookingName,
                key: "contact.invalidName",
                isValid: (value) => Boolean(value) && value.length <= 50
            },
            {
                field: bookingEmail,
                key: "contact.invalidEmail",
                isValid: (value) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/u.test(value)
            },
            {
                field: bookingPhone,
                key: "contact.invalidPhone",
                isValid: (value) => {
                    if (!value) {
                        return false;
                    }

                    const digitsOnly = value.replace(/\D/g, "");
                    return /^\+?[0-9\s().-]+$/u.test(value)
                        && digitsOnly.length >= 7
                        && digitsOnly.length <= 15;
                }
            },
            {
                field: bookingDate,
                key: "contact.invalidDate",
                isValid: (value) => Boolean(value) && Boolean(bookingDate?.min) && value >= bookingDate.min
            },
            {
                field: bookingGuests,
                key: "contact.invalidGuests",
                isValid: (value) => Number.parseInt(value, 10) >= 1
            },
            {
                field: bookingPostalCode,
                key: "contact.invalidPostalCode",
                isValid: (value) => Boolean(value) && /^[A-Za-z0-9][A-Za-z0-9\s-]{2,9}$/u.test(value)
            }
        ];

        validators.forEach(({ field, key, isValid }) => {
            if (!field) {
                return;
            }

            const trimmedValue = field.value.trim();
            field.setCustomValidity(isValid(trimmedValue) ? "" : translate(key));
        });
    };

    /* Apply translations to text, attributes, metadata, form errors, and page links. */
    // This helper updates language while keeping the underlying server-owned data unchanged.
    const applyLanguage = (language) => {
        currentLanguage = isSupportedLanguage(language) ? language : "en";
        document.documentElement.lang = currentLanguage;

        document.querySelectorAll("[data-i18n]").forEach((element) => {
            const key = element.getAttribute("data-i18n");
            element.textContent = translate(key);
        });

        document.querySelectorAll("[data-i18n-template]").forEach((element) => {
            let text = translate(element.getAttribute("data-i18n-template"));
            Array.from(element.attributes)
                .filter((attribute) => attribute.name.startsWith("data-i18n-value-"))
                .forEach((attribute) => {
                    const placeholder = attribute.name.replace("data-i18n-value-", "");
                    text = text.replaceAll(`{${placeholder}}`, attribute.value);
                });
            element.textContent = text;
        });

        ["aria-label", "alt", "placeholder", "title"].forEach((attributeName) => {
            const dataAttribute = `data-i18n-${attributeName}`;

            document.querySelectorAll(`[${dataAttribute}]`).forEach((element) => {
                const key = element.getAttribute(dataAttribute);
                element.setAttribute(attributeName, translate(key));
            });
        });

        const page = document.body.dataset.page;
        document.title = translate(`meta.${page}.title`);

        if (metaDescription) {
            metaDescription.setAttribute("content", translate(`meta.${page}.description`));
        }

        if (languageSelector) {
            languageSelector.value = currentLanguage;
        }

        updateNavigationToggleLabel();
        updateThemeControl();
        updateInternalLanguageLinks();
        applyCustomPackageDetails();
        validateBookingFields();
        storeValue(languageStorageKey, currentLanguage);
        updateCurrentUrlLanguage();
        document.dispatchEvent(new CustomEvent("popadoo:language-applied", { detail: { language: currentLanguage } }));
    };

    /* Responsive navigation helpers maintain aria-expanded and focus restoration. */
    // This helper changes navigation while keeping keyboard focus and visible state in step for accessibility.
    const closeNavigation = (returnFocus = false) => {
        if (!navigationToggle || !navigationMenu) {
            return;
        }

        navigationMenu.classList.remove("is-open");
        navigationToggle.setAttribute("aria-expanded", "false");
        updateNavigationToggleLabel();

        if (returnFocus) {
            navigationToggle.focus();
        }
    };

    // This function changes whether navigation is visible.
    // This helper changes navigation while keeping keyboard focus and visible state in step for accessibility.
    const openNavigation = () => {
        if (!navigationToggle || !navigationMenu) {
            return;
        }

        navigationMenu.classList.add("is-open");
        navigationToggle.setAttribute("aria-expanded", "true");
        updateNavigationToggleLabel();
    };

    /* Bind responsive navigation interactions only when the header is present. */
    if (navigationToggle && navigationMenu) {
        // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
        navigationToggle.addEventListener("click", () => {
            const isOpen = navigationToggle.getAttribute("aria-expanded") === "true";
            isOpen ? closeNavigation() : openNavigation();
        });

        // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
        navigationMenu.addEventListener("click", (event) => {
            if (event.target.closest("a") && navigationBreakpoint.matches) {
                closeNavigation();
            }
        });

        // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
        document.addEventListener("click", (event) => {
            if (
                navigationBreakpoint.matches
                && navigationMenu.classList.contains("is-open")
                && !event.target.closest(".site-navigation")
            ) {
                closeNavigation();
            }
        });

        // This listener responds to the keydown event and keeps the enhanced interface aligned with the visitor’s action.
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && navigationMenu.classList.contains("is-open")) {
                closeNavigation(true);
            }
        });

        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        navigationBreakpoint.addEventListener("change", (event) => {
            if (!event.matches) {
                closeNavigation();
            }
        });
    }

    /* Event delegation keeps the language dropdown working even if the header is re-rendered. */
    // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("change", (event) => {
        if (event.target.matches("#language-selector")) {
            applyLanguage(event.target.value);
        }
    });

    /* Persist the visitor-selected theme and update accessible control text. */
    if (themeToggle) {
        // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
        themeToggle.addEventListener("click", () => {
            const currentTheme = document.documentElement.getAttribute("data-theme");
            const nextTheme = currentTheme === "dark" ? "light" : "dark";

            document.documentElement.setAttribute("data-theme", nextTheme);
            storeValue(themeStorageKey, nextTheme);
            updateThemeControl();
        });
    }

    /*
     * Contact-form enhancement.
     * Native HTML validation stays active, while custom validation tightens name,
     * phone, guest-count, postal-code, and date rules before the demo response.
     */
    if (bookingDate) {
        bookingDate.min = formatDateForInput(new Date());
    }

    if (bookingForm) {
        setDefaultBookingValues();
        applySelectedPackageToBookingForm();
        validateBookingFields();

        // This listener responds to the submit event and keeps the enhanced interface aligned with the visitor’s action.
        bookingForm.addEventListener("submit", (event) => {
            event.preventDefault();
            event.stopPropagation();

            validateBookingFields();
            bookingForm.classList.add("was-validated");

            if (!bookingForm.checkValidity()) {
                bookingForm.querySelector(":invalid")?.focus();
                return;
            }

            clearBookingForm({ preserveConfirmation: true });

            if (bookingConfirmation) {
                bookingConfirmation.hidden = false;
                bookingConfirmation.focus();
                const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
                bookingConfirmation.scrollIntoView({
                    behavior: prefersReducedMotion ? "auto" : "smooth",
                    block: "center"
                });
            }
        });

        // This listener responds to the input event and keeps the enhanced interface aligned with the visitor’s action.
        bookingForm.addEventListener("input", (event) => {
            if (event.target === bookingDetails) {
                bookingDetails.dataset.autoCustomPackage = "false";
            }

            validateBookingFields();
            hideBookingConfirmation();
        });

        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        bookingPackage?.addEventListener("change", () => {
            if (bookingPackage.value === customPackageId) {
                applyCustomPackageDetails();
            }
        });

        // This listener responds to the change event and keeps the enhanced interface aligned with the visitor’s action.
        bookingForm.addEventListener("change", validateBookingFields);

        // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
        bookingClearButton?.addEventListener("click", () => {
            clearBookingForm();
            bookingForm.querySelector("input, select, textarea")?.focus();
        });
    }

    /* Choose the initial language from URL, saved preference, or browser language. */
    const savedLanguage = getStoredValue(languageStorageKey);
    const browserLanguage = navigator.language?.toLowerCase().startsWith("el") ? "el" : "en";
    const requestedLanguage = getUrlLanguage() ?? (isSupportedLanguage(savedLanguage) ? savedLanguage : browserLanguage);

    applyLanguage(requestedLanguage);
})();

/* Accessible account dropdown used by the global utility stripe. */
/*
 * Accessible account dropdowns for the upper utility stripe.
 *
 * The same controller works for guest and signed-in menus. It supports mouse,
 * touch, arrow keys, Home/End, Escape, and normal Tab navigation.
 */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    // This helper carries out account menu for the visitor-facing interaction managed by this script.
    class AccountMenu {
        constructor(root) {
            this.root = root;
            this.button = root.querySelector("[data-account-menu-button]");
            this.panel = root.querySelector("[data-account-menu-panel]");
            this.items = Array.from(
                root.querySelectorAll("[data-account-menu-item]")
            );

            if (!this.button || !this.panel) {
                return;
            }

            this.bindEvents();
        }

        bindEvents() {
            // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
            this.button.addEventListener("click", () => this.toggle());
            // This listener responds to the keydown event and keeps the enhanced interface aligned with the visitor’s action.
            this.button.addEventListener("keydown", (event) => {
                if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
                    event.preventDefault();
                    this.open(event.key === "ArrowUp" ? this.items.length - 1 : 0);
                } else if (event.key === "Escape") {
                    this.close(true);
                }
            });

            // This listener responds to the keydown event and keeps the enhanced interface aligned with the visitor’s action.
            this.panel.addEventListener("keydown", (event) => {
                this.handlePanelKeyboard(event);
            });

            // This listener responds to the click event and keeps the enhanced interface aligned with the visitor’s action.
            document.addEventListener("click", (event) => {
                if (!this.root.contains(event.target)) {
                    this.close();
                }
            });
        }

        isOpen() {
            return this.button.getAttribute("aria-expanded") === "true";
        }

        open(focusIndex = null) {
            this.panel.hidden = false;
            this.button.setAttribute("aria-expanded", "true");

            /* Close the language popover so two menus never overlap. */
            document.querySelectorAll("[data-custom-popover-open='true']").forEach((control) => {
                control.dispatchEvent(new CustomEvent("popadoo:close-control"));
            });

            if (Number.isInteger(focusIndex) && this.items.length) {
                this.items[Math.max(0, Math.min(focusIndex, this.items.length - 1))].focus();
            }
        }

        close(returnFocus = false) {
            this.panel.hidden = true;
            this.button.setAttribute("aria-expanded", "false");

            if (returnFocus) {
                this.button.focus();
            }
        }

        toggle() {
            if (this.isOpen()) {
                this.close();
            } else {
                this.open();
            }
        }

        focusItem(index) {
            if (!this.items.length) {
                return;
            }

            const safeIndex = (index + this.items.length) % this.items.length;
            this.items[safeIndex].focus();
        }

        handlePanelKeyboard(event) {
            const currentIndex = this.items.indexOf(document.activeElement);

            if (event.key === "Escape") {
                event.preventDefault();
                this.close(true);
                return;
            }

            if (currentIndex < 0) {
                return;
            }

            if (event.key === "ArrowDown") {
                event.preventDefault();
                this.focusItem(currentIndex + 1);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                this.focusItem(currentIndex - 1);
            } else if (event.key === "Home") {
                event.preventDefault();
                this.focusItem(0);
            } else if (event.key === "End") {
                event.preventDefault();
                this.focusItem(this.items.length - 1);
            } else if (event.key === "Tab") {
                window.setTimeout(() => {
                    if (!this.root.contains(document.activeElement)) {
                        this.close();
                    }
                }, 0);
            }
        }
    }

    document.querySelectorAll("[data-account-menu]").forEach(
        (root) => new AccountMenu(root)
    );
})();
