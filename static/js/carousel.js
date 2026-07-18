/*
 * This script makes the public image carousel respond to buttons, indicators, and keyboard-friendly controls while leaving the page content usable without it.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

/*
 * This script controls the home-page image carousel and keeps its buttons, indicators, and announcements synchronized.
 * These comments explain the browser-side steps without changing the JavaScript behaviour.
 */

/*
 * Home-page carousel enhancement.
 *
 * CSS provides a graceful fallback slideshow if JavaScript is unavailable.
 * When this module loads, it adds managed active-slide state, icon-only arrow
 * controls, keyboard support, bottom-center dots, and continuous autoplay.
 */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    const carousel = document.querySelector("[data-home-carousel]");

    if (!carousel) {
        return;
    }

    const slides = Array.from(carousel.querySelectorAll(".hero-carousel-slide"));
    const previousButton = carousel.querySelector("[data-carousel-previous]");
    const nextButton = carousel.querySelector("[data-carousel-next]");
    const indicatorButtons = Array.from(carousel.querySelectorAll("[data-carousel-indicator]"));
    const status = carousel.querySelector("[data-carousel-status]");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const autoplayInterval = 5000;

    if (slides.length === 0 || !previousButton || !nextButton) {
        return;
    }

    /* Track the currently visible slide; wrapping is handled by showSlide(). */
    let activeIndex = 0;
    let autoplayTimer = null;

    /* Build localized screen-reader text for the current slide position. */
    // This helper reads status message so later screen updates use the same fallback rules.
    const getStatusMessage = () => {
        const current = activeIndex + 1;
        const total = slides.length;
        const language = document.documentElement.lang;

        return language === "el"
            ? `Φωτογραφία ${current} από ${total}`
            : `Photo ${current} of ${total}`;
    };

    // This function reads or prepares indicator label for the next step.
    // This helper reads indicator label so later screen updates use the same fallback rules.
    const getIndicatorLabel = (index) => {
        const position = index + 1;
        const language = document.documentElement.lang;

        return language === "el"
            ? `Εμφάνιση εικόνας ${position}`
            : `Show image ${position}`;
    };

    // This function refreshes status so the page matches the latest user choice.
    // This helper updates status while keeping the underlying server-owned data unchanged.
    const updateStatus = () => {
        if (status) {
            status.textContent = getStatusMessage();
        }
    };

    /* Keep dot labels and active state useful for screen readers and keyboard users. */
    // This helper updates indicators while keeping the underlying server-owned data unchanged.
    const updateIndicators = () => {
        indicatorButtons.forEach((button, index) => {
            const isActive = index === activeIndex;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-current", String(isActive));
            button.setAttribute("aria-label", getIndicatorLabel(index));
        });
    };

    /* Activate one slide, hide the others from assistive tech, and refresh controls. */
    // This helper updates slide while keeping the underlying server-owned data unchanged.
    const showSlide = (nextIndex) => {
        activeIndex = (nextIndex + slides.length) % slides.length;

        slides.forEach((slide, index) => {
            const isActive = index === activeIndex;
            slide.classList.toggle("is-active", isActive);
            slide.setAttribute("aria-hidden", String(!isActive));
        });

        updateIndicators();
        updateStatus();
    };

    // This function handles the show previous slide part of the browser interaction.
    // This helper updates previous slide while keeping the underlying server-owned data unchanged.
    const showPreviousSlide = () => {
        showSlide(activeIndex - 1);
    };

    // This function handles the show next slide part of the browser interaction.
    // This helper updates next slide while keeping the underlying server-owned data unchanged.
    const showNextSlide = () => {
        showSlide(activeIndex + 1);
    };

    // This function handles the stop autoplay part of the browser interaction.
    // This helper controls autoplay so background work runs only while it is useful to the visitor.
    const stopAutoplay = () => {
        window.clearInterval(autoplayTimer);
        autoplayTimer = null;
    };

    // This function handles the start autoplay part of the browser interaction.
    // This helper controls autoplay so background work runs only while it is useful to the visitor.
    const startAutoplay = () => {
        stopAutoplay();

        /* Honour reduced-motion preferences while keeping manual controls available. */
        if (slides.length < 2 || prefersReducedMotion.matches) {
            return;
        }

        autoplayTimer = window.setInterval(showNextSlide, autoplayInterval);
    };

    /* Manual navigation restarts the timer so auto-sliding never jumps immediately after a click. */
    // This helper carries out navigate manually for the visitor-facing interaction managed by this script.
    const navigateManually = (navigationCallback) => {
        navigationCallback();
        startAutoplay();
    };

    carousel.classList.add("is-carousel-enhanced");
    showSlide(activeIndex);
    startAutoplay();

    // Move to the previous carousel slide, restart manual-navigation timing, and update the active indicator and live
    // status.
    previousButton.addEventListener("click", () => {
        navigateManually(showPreviousSlide);
    });

    // Move to the next carousel slide, restart manual-navigation timing, and update the active indicator and live
    // status.
    nextButton.addEventListener("click", () => {
        navigateManually(showNextSlide);
    });

    indicatorButtons.forEach((button) => {
        // Show the slide selected by the clicked indicator, then restart autoplay timing and refresh the indicator and
        // status state.
        button.addEventListener("click", () => {
            navigateManually(() => {
                showSlide(Number(button.dataset.carouselIndicator));
            });
        });
    });

    // Use ArrowLeft and ArrowRight to navigate the carousel, preventing page scrolling while the slide, indicator, and
    // status are updated.
    carousel.addEventListener("keydown", (event) => {
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            navigateManually(showPreviousSlide);
        }

        if (event.key === "ArrowRight") {
            event.preventDefault();
            navigateManually(showNextSlide);
        }
    });

    /* Avoid wasting work while the tab is hidden; restart the loop as soon as it is visible. */
    // This listener responds to the visibilitychange event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopAutoplay();
            return;
        }

        startAutoplay();
    });

    if (typeof prefersReducedMotion.addEventListener === "function") {
        // Re-evaluate carousel autoplay when the visitor’s reduced-motion preference changes, keeping motion disabled
        // whenever that preference is active.
        prefersReducedMotion.addEventListener("change", startAutoplay);
    } else if (typeof prefersReducedMotion.addListener === "function") {
        prefersReducedMotion.addListener(startAutoplay);
    }

    /* Refresh translated carousel labels when main.js changes the document language. */
    // This helper carries out language observer for the visitor-facing interaction managed by this script.
    const languageObserver = new MutationObserver(() => {
        updateIndicators();
        updateStatus();
    });

    languageObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["lang"]
    });
})();
