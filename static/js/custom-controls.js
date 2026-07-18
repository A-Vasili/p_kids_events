/*
 * This script connects the project’s custom date and time controls to their real form fields so the accessible Django form remains the source of submitted values.
 * Django remains responsible for permissions, trusted prices, identities, and saved records; this file only improves the browser experience.
 * The comments describe the interaction without changing any statement, selector, translation key, or request address.
 */
"use strict";

/*
 * Accessible custom controls used by the language picker, booking date/time,
 * and worker availability forms.
 *
 * Each visible control is built from styleable div elements with ARIA roles.
 * A hidden input remains the source of truth submitted to Django, so all
 * values are still checked again by the server before they are stored.
 */
// This private setup runs once for the page and avoids placing temporary interface state on the global window object.
(() => {
    const DAY_MS = 24 * 60 * 60 * 1000;

    // This helper carries out current locale for the visitor-facing interaction managed by this script.
    const currentLocale = () => (
        document.documentElement.lang?.toLowerCase().startsWith("el")
            ? "el-GR"
            : "en-GB"
    );

    // This helper carries out activate div button for the visitor-facing interaction managed by this script.
    const activateDivButton = (element, callback) => {
        if (!element) {
            return;
        }

        // Run the shared activation callback when the custom div button is clicked.
        element.addEventListener("click", callback);
        // Treat Enter and Space on the custom div button like a click, preventing the default key action before
        // invoking the callback.
        element.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                callback(event);
            }
        });
    };

    // This helper carries out dispatch value change for the visitor-facing interaction managed by this script.
    const dispatchValueChange = (input) => {
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    };

    // This helper changes other popovers while keeping keyboard focus and visible state in step for accessibility.
    const closeOtherPopovers = (currentRoot) => {
        document.querySelectorAll("[data-custom-popover-open='true']").forEach((root) => {
            if (root !== currentRoot) {
                root.dispatchEvent(new CustomEvent("popadoo:close-control"));
            }
        });
    };

    // This helper carries out parse date for the visitor-facing interaction managed by this script.
    const parseDate = (value) => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) {
            return null;
        }

        const [year, month, day] = value.split("-").map(Number);
        const parsed = new Date(year, month - 1, day, 12, 0, 0, 0);

        if (
            parsed.getFullYear() !== year
            || parsed.getMonth() !== month - 1
            || parsed.getDate() !== day
        ) {
            return null;
        }

        return parsed;
    };

    // This helper carries out format date value for the visitor-facing interaction managed by this script.
    const formatDateValue = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    };

    // This helper controls of day so background work runs only while it is useful to the visitor.
    const startOfDay = (date) => new Date(
        date.getFullYear(),
        date.getMonth(),
        date.getDate(),
        12,
        0,
        0,
        0
    );

    // This helper carries out custom select for the visitor-facing interaction managed by this script.
    class CustomSelect {
        constructor(root) {
            this.root = root;
            this.input = root.querySelector("[data-custom-select-input]");
            this.trigger = root.querySelector("[data-custom-select-trigger]");
            this.valueDisplay = root.querySelector("[data-custom-select-value]");
            this.listbox = root.querySelector("[data-custom-select-options]");
            this.options = Array.from(root.querySelectorAll("[role='option']"));

            if (!this.input || !this.trigger || !this.listbox || !this.options.length) {
                return;
            }

            this.bindEvents();
            this.syncFromInput();
        }

        bindEvents() {
            // Toggle the custom select popup from its trigger while synchronizing aria-expanded, option focus, and
            // popup visibility.
            this.trigger.addEventListener("click", () => this.toggle());
            // Open the custom select from Enter, Space, or arrow keys and place focus on the appropriate option.
            this.trigger.addEventListener("keydown", (event) => this.onTriggerKeydown(event));
            // Navigate, select, close, or leave the custom select listbox with the expected arrow, Home/End,
            // Enter/Space, Escape, and Tab behavior.
            this.listbox.addEventListener("keydown", (event) => this.onListboxKeydown(event));

            this.options.forEach((option) => {
                // Select the clicked custom-select option, copy its value to the native input, close the popup, and
                // dispatch the input/change notifications.
                option.addEventListener("click", () => this.select(option, true));
            });

            // Synchronize the custom-select label, selected option, and ARIA state whenever its native input value
            // changes.
            this.input.addEventListener("change", () => this.syncFromInput());
            // This listener responds to the popadoo:close-control event and keeps the enhanced interface aligned with the visitor’s action.
            this.root.addEventListener("popadoo:close-control", () => this.close());
        }

        isOpen() {
            return this.trigger.getAttribute("aria-expanded") === "true";
        }

        open(focusDirection = 0) {
            closeOtherPopovers(this.root);
            this.root.dataset.customPopoverOpen = "true";
            this.trigger.setAttribute("aria-expanded", "true");
            this.listbox.hidden = false;

            const selectedIndex = Math.max(
                0,
                this.options.findIndex((option) => option.getAttribute("aria-selected") === "true")
            );
            const targetIndex = focusDirection < 0
                ? Math.max(0, selectedIndex - 1)
                : focusDirection > 0
                    ? Math.min(this.options.length - 1, selectedIndex + 1)
                    : selectedIndex;
            this.focusOption(targetIndex);
        }

        close(returnFocus = false) {
            delete this.root.dataset.customPopoverOpen;
            this.trigger.setAttribute("aria-expanded", "false");
            this.listbox.hidden = true;
            if (returnFocus) {
                this.trigger.focus();
            }
        }

        toggle() {
            if (this.isOpen()) {
                this.close();
            } else {
                this.open();
            }
        }

        focusOption(index) {
            this.options.forEach((option, optionIndex) => {
                option.tabIndex = optionIndex === index ? 0 : -1;
            });
            this.options[index]?.focus();
        }

        select(option, notify) {
            const value = option.dataset.value || "";
            const label = option.dataset.label || option.textContent.trim();

            this.options.forEach((item) => {
                const selected = item === option;
                item.setAttribute("aria-selected", String(selected));
                item.classList.toggle("is-selected", selected);
            });

            this.input.value = value;
            this.valueDisplay.textContent = label;
            this.close(true);

            if (notify) {
                dispatchValueChange(this.input);
            }
        }

        syncFromInput() {
            const matchingOption = this.options.find(
                (option) => option.dataset.value === this.input.value
            ) || this.options[0];
            this.select(matchingOption, false);
        }

        onTriggerKeydown(event) {
            if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
                event.preventDefault();
                this.open(event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0);
            }
        }

        onListboxKeydown(event) {
            const activeIndex = this.options.indexOf(document.activeElement);
            let nextIndex = activeIndex;

            if (event.key === "ArrowDown") {
                nextIndex = Math.min(this.options.length - 1, activeIndex + 1);
            } else if (event.key === "ArrowUp") {
                nextIndex = Math.max(0, activeIndex - 1);
            } else if (event.key === "Home") {
                nextIndex = 0;
            } else if (event.key === "End") {
                nextIndex = this.options.length - 1;
            } else if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                this.select(document.activeElement, true);
                return;
            } else if (event.key === "Escape") {
                event.preventDefault();
                this.close(true);
                return;
            } else if (event.key === "Tab") {
                this.close();
                return;
            } else {
                return;
            }

            event.preventDefault();
            this.focusOption(nextIndex);
        }
    }

    // This helper carries out date picker for the visitor-facing interaction managed by this script.
    class DatePicker {
        constructor(root) {
            this.root = root;
            this.input = root.querySelector("input[type='hidden']");
            this.trigger = root.querySelector("[data-date-trigger]");
            this.display = root.querySelector("[data-date-display]");
            this.panel = root.querySelector("[data-date-panel]");
            this.grid = root.querySelector("[data-date-grid]");
            this.weekdays = root.querySelector("[data-date-weekdays]");
            this.monthLabel = root.querySelector("[data-date-month-label]");
            this.previous = root.querySelector("[data-date-previous]");
            this.next = root.querySelector("[data-date-next]");
            this.placeholder = root.dataset.placeholder || "Choose a date";

            if (!this.input || !this.trigger || !this.panel || !this.grid) {
                return;
            }

            this.minimumDate = parseDate(this.input.dataset.min || this.input.min || "");
            this.maximumDate = parseDate(this.input.dataset.max || this.input.max || "");
            this.selectedDate = parseDate(this.input.value);
            this.focusDate = this.selectedDate || this.minimumDate || startOfDay(new Date());
            this.viewDate = new Date(this.focusDate.getFullYear(), this.focusDate.getMonth(), 1, 12);

            this.bindEvents();
            this.syncDisplay();
        }

        bindEvents() {
            // Toggle the date-picker popup from its trigger while keeping expanded state, calendar focus, and
            // visibility synchronized.
            this.trigger.addEventListener("click", () => this.toggle());
            // Open the date picker from Enter, Space, or ArrowDown and move focus into the calendar grid.
            this.trigger.addEventListener("keydown", (event) => this.onTriggerKeydown(event));
            activateDivButton(this.previous, () => this.changeMonth(-1));
            activateDivButton(this.next, () => this.changeMonth(1));
            // This listener responds to the popadoo:close-control event and keeps the enhanced interface aligned with the visitor’s action.
            this.root.addEventListener("popadoo:close-control", () => this.close());
            // Parse the changed native date value, update the selected and focused day, and refresh the visible date
            // label.
            this.input.addEventListener("change", () => {
                this.selectedDate = parseDate(this.input.value);
                this.focusDate = this.selectedDate || this.focusDate;
                this.syncDisplay();
            });
        }

        isOpen() {
            return this.trigger.getAttribute("aria-expanded") === "true";
        }

        open() {
            closeOtherPopovers(this.root);
            this.root.dataset.customPopoverOpen = "true";
            this.trigger.setAttribute("aria-expanded", "true");
            this.panel.hidden = false;
            this.render();
            requestAnimationFrame(() => this.focusCurrentDay());
        }

        close(returnFocus = false) {
            delete this.root.dataset.customPopoverOpen;
            this.trigger.setAttribute("aria-expanded", "false");
            this.panel.hidden = true;
            if (returnFocus) {
                this.trigger.focus();
            }
        }

        toggle() {
            if (this.isOpen()) {
                this.close();
            } else {
                this.open();
            }
        }

        isAllowed(date) {
            const value = startOfDay(date).getTime();
            return (!this.minimumDate || value >= this.minimumDate.getTime())
                && (!this.maximumDate || value <= this.maximumDate.getTime());
        }

        changeMonth(offset) {
            this.viewDate = new Date(
                this.viewDate.getFullYear(),
                this.viewDate.getMonth() + offset,
                1,
                12
            );
            this.focusDate = new Date(
                this.viewDate.getFullYear(),
                this.viewDate.getMonth(),
                1,
                12
            );
            this.render();
            this.focusCurrentDay();
        }

        selectDate(date) {
            if (!this.isAllowed(date)) {
                return;
            }
            this.selectedDate = startOfDay(date);
            this.focusDate = this.selectedDate;
            this.input.value = formatDateValue(this.selectedDate);
            this.syncDisplay();
            dispatchValueChange(this.input);
            this.close(true);
        }

        syncDisplay() {
            this.display.textContent = this.selectedDate
                ? new Intl.DateTimeFormat(currentLocale(), {
                    weekday: "short",
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                }).format(this.selectedDate)
                : this.placeholder;
        }

        renderWeekdays() {
            this.weekdays.textContent = "";
            const formatter = new Intl.DateTimeFormat(currentLocale(), { weekday: "short" });
            const monday = new Date(2024, 0, 1, 12);
            for (let index = 0; index < 7; index += 1) {
                const label = document.createElement("span");
                label.textContent = formatter.format(new Date(monday.getTime() + index * DAY_MS));
                this.weekdays.appendChild(label);
            }
        }

        render() {
            this.renderWeekdays();
            this.grid.textContent = "";
            this.monthLabel.textContent = new Intl.DateTimeFormat(currentLocale(), {
                month: "long",
                year: "numeric",
            }).format(this.viewDate);

            const firstDay = new Date(
                this.viewDate.getFullYear(),
                this.viewDate.getMonth(),
                1,
                12
            );
            const mondayOffset = (firstDay.getDay() + 6) % 7;
            const gridStart = new Date(firstDay.getTime() - mondayOffset * DAY_MS);

            for (let index = 0; index < 42; index += 1) {
                const date = new Date(gridStart.getTime() + index * DAY_MS);
                const cell = document.createElement("div");
                const dateValue = formatDateValue(date);
                const isCurrentMonth = date.getMonth() === this.viewDate.getMonth();
                const isSelected = this.selectedDate && dateValue === formatDateValue(this.selectedDate);
                const isFocused = dateValue === formatDateValue(this.focusDate);
                const isToday = dateValue === formatDateValue(startOfDay(new Date()));
                const allowed = this.isAllowed(date);

                cell.className = "custom-date-day";
                cell.setAttribute("role", "gridcell");
                cell.setAttribute("aria-label", new Intl.DateTimeFormat(currentLocale(), {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                }).format(date));
                cell.setAttribute("aria-selected", String(Boolean(isSelected)));
                cell.setAttribute("aria-disabled", String(!allowed));
                cell.tabIndex = isFocused ? 0 : -1;
                cell.dataset.date = dateValue;
                cell.textContent = String(date.getDate());
                cell.classList.toggle("is-other-month", !isCurrentMonth);
                cell.classList.toggle("is-selected", Boolean(isSelected));
                cell.classList.toggle("is-today", isToday);
                cell.classList.toggle("is-disabled", !allowed);

                // Select the clicked calendar day, write it to the native date input, close the picker, and return
                // focus to the trigger.
                cell.addEventListener("click", () => this.selectDate(date));
                // Support arrow, Home/End, PageUp/PageDown, Enter/Space, and Escape navigation for each calendar day
                // while preserving grid focus.
                cell.addEventListener("keydown", (event) => this.onDayKeydown(event, date));
                this.grid.appendChild(cell);
            }
        }

        focusCurrentDay() {
            this.grid.querySelector("[tabindex='0']")?.focus();
        }

        moveFocus(days) {
            let candidate = new Date(this.focusDate.getTime() + days * DAY_MS);
            if (this.minimumDate && candidate < this.minimumDate) {
                candidate = this.minimumDate;
            }
            if (this.maximumDate && candidate > this.maximumDate) {
                candidate = this.maximumDate;
            }
            this.focusDate = startOfDay(candidate);
            this.viewDate = new Date(candidate.getFullYear(), candidate.getMonth(), 1, 12);
            this.render();
            this.focusCurrentDay();
        }

        onTriggerKeydown(event) {
            if (["Enter", " ", "ArrowDown"].includes(event.key)) {
                event.preventDefault();
                this.open();
            }
        }

        onDayKeydown(event, date) {
            if (event.key === "ArrowRight") {
                event.preventDefault();
                this.moveFocus(1);
            } else if (event.key === "ArrowLeft") {
                event.preventDefault();
                this.moveFocus(-1);
            } else if (event.key === "ArrowDown") {
                event.preventDefault();
                this.moveFocus(7);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                this.moveFocus(-7);
            } else if (event.key === "Home") {
                event.preventDefault();
                this.moveFocus(-((date.getDay() + 6) % 7));
            } else if (event.key === "End") {
                event.preventDefault();
                this.moveFocus(6 - ((date.getDay() + 6) % 7));
            } else if (event.key === "PageUp") {
                event.preventDefault();
                this.changeMonth(-1);
            } else if (event.key === "PageDown") {
                event.preventDefault();
                this.changeMonth(1);
            } else if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                this.selectDate(date);
            } else if (event.key === "Escape") {
                event.preventDefault();
                this.close(true);
            }
        }
    }

    // This helper carries out time picker for the visitor-facing interaction managed by this script.
    class TimePicker {
        constructor(root) {
            this.root = root;
            this.input = root.querySelector("input[type='hidden']");
            this.trigger = root.querySelector("[data-time-trigger]");
            this.display = root.querySelector("[data-time-display]");
            this.listbox = root.querySelector("[data-time-options]");
            this.placeholder = root.dataset.placeholder || "Choose a time";
            this.start = root.dataset.timeStart || "10:00";
            this.end = root.dataset.timeEnd || "22:00";
            this.step = Number.parseInt(root.dataset.timeStep || "30", 10);
            this.optional = root.dataset.timeOptional === "true";
            this.options = [];

            if (!this.input || !this.trigger || !this.listbox) {
                return;
            }

            this.buildOptions();
            this.bindEvents();
            this.syncFromInput();
        }

        minutesFromValue(value) {
            const match = /^(\d{2}):(\d{2})$/.exec(value || "");
            return match ? Number(match[1]) * 60 + Number(match[2]) : null;
        }

        valueFromMinutes(minutes) {
            return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
        }

        formatTime(value) {
            if (!value) {
                return this.placeholder;
            }
            const [hours, minutes] = value.split(":").map(Number);
            return new Intl.DateTimeFormat(currentLocale(), {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            }).format(new Date(2024, 0, 1, hours, minutes));
        }

        buildOptions() {
            this.listbox.textContent = "";
            const entries = [];
            if (this.optional) {
                entries.push({ value: "", label: "To be confirmed" });
            }

            const startMinutes = this.minutesFromValue(this.start) ?? 600;
            const endMinutes = this.minutesFromValue(this.end) ?? 1320;
            for (let minutes = startMinutes; minutes <= endMinutes; minutes += this.step) {
                const value = this.valueFromMinutes(minutes);
                entries.push({ value, label: this.formatTime(value) });
            }

            entries.forEach((entry) => {
                const option = document.createElement("div");
                option.className = "custom-select-option custom-time-option";
                option.setAttribute("role", "option");
                option.setAttribute("aria-selected", "false");
                option.tabIndex = -1;
                option.dataset.value = entry.value;
                option.textContent = entry.label;
                // Select the clicked time option, copy it to the native input, close the listbox, and dispatch the
                // input/change notifications.
                option.addEventListener("click", () => this.select(option, true));
                this.listbox.appendChild(option);
            });

            this.options = Array.from(this.listbox.querySelectorAll("[role='option']"));
        }

        bindEvents() {
            // Toggle the time-picker listbox from its trigger while synchronizing expanded state, option focus, and
            // visibility.
            this.trigger.addEventListener("click", () => this.toggle());
            // Open the time picker from Enter, Space, or arrow keys and focus the selected or adjacent time option.
            this.trigger.addEventListener("keydown", (event) => this.onTriggerKeydown(event));
            // Navigate, select, close, or leave the time listbox with arrow, Home/End, Enter/Space, Escape, and Tab
            // behavior.
            this.listbox.addEventListener("keydown", (event) => this.onListboxKeydown(event));
            // Synchronize the time-picker label and selected option whenever the native time input changes.
            this.input.addEventListener("change", () => this.syncFromInput());
            // This listener responds to the popadoo:close-control event and keeps the enhanced interface aligned with the visitor’s action.
            this.root.addEventListener("popadoo:close-control", () => this.close());
        }

        isOpen() {
            return this.trigger.getAttribute("aria-expanded") === "true";
        }

        open(direction = 0) {
            closeOtherPopovers(this.root);
            this.root.dataset.customPopoverOpen = "true";
            this.trigger.setAttribute("aria-expanded", "true");
            this.listbox.hidden = false;
            const selected = Math.max(0, this.options.findIndex(
                (option) => option.getAttribute("aria-selected") === "true"
            ));
            this.focusOption(Math.max(0, Math.min(this.options.length - 1, selected + direction)));
        }

        close(returnFocus = false) {
            delete this.root.dataset.customPopoverOpen;
            this.trigger.setAttribute("aria-expanded", "false");
            this.listbox.hidden = true;
            if (returnFocus) {
                this.trigger.focus();
            }
        }

        toggle() {
            if (this.isOpen()) {
                this.close();
            } else {
                this.open();
            }
        }

        focusOption(index) {
            this.options.forEach((option, optionIndex) => {
                option.tabIndex = optionIndex === index ? 0 : -1;
            });
            this.options[index]?.focus();
        }

        select(option, notify) {
            const value = option.dataset.value || "";
            this.options.forEach((item) => {
                const selected = item === option;
                item.setAttribute("aria-selected", String(selected));
                item.classList.toggle("is-selected", selected);
            });
            this.input.value = value;
            this.display.textContent = value ? this.formatTime(value) : this.placeholder;
            this.close(true);
            if (notify) {
                dispatchValueChange(this.input);
            }
        }

        syncFromInput() {
            // This helper carries out option for the visitor-facing interaction managed by this script.
            const option = this.options.find((item) => item.dataset.value === this.input.value)
                || (this.optional ? this.options[0] : null);
            if (option) {
                this.select(option, false);
            } else {
                this.display.textContent = this.placeholder;
            }
        }

        onTriggerKeydown(event) {
            if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
                event.preventDefault();
                this.open(event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0);
            }
        }

        onListboxKeydown(event) {
            const activeIndex = this.options.indexOf(document.activeElement);
            let nextIndex = activeIndex;

            if (event.key === "ArrowDown") {
                nextIndex = Math.min(this.options.length - 1, activeIndex + 1);
            } else if (event.key === "ArrowUp") {
                nextIndex = Math.max(0, activeIndex - 1);
            } else if (event.key === "Home") {
                nextIndex = 0;
            } else if (event.key === "End") {
                nextIndex = this.options.length - 1;
            } else if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                this.select(document.activeElement, true);
                return;
            } else if (event.key === "Escape") {
                event.preventDefault();
                this.close(true);
                return;
            } else if (event.key === "Tab") {
                this.close();
                return;
            } else {
                return;
            }

            event.preventDefault();
            this.focusOption(nextIndex);
        }
    }

    // This helper carries out date time composite for the visitor-facing interaction managed by this script.
    class DateTimeComposite {
        constructor(root) {
            this.root = root;
            this.masterInput = root.querySelector("[data-datetime-input]");
            this.dateInput = root.querySelector("[data-datetime-date]");
            this.timeInput = root.querySelector("[data-datetime-time]");

            if (!this.masterInput || !this.dateInput || !this.timeInput) {
                return;
            }

            this.populateParts();
            // Combine the changed date with the current time into the hidden datetime input and dispatch its
            // input/change events.
            this.dateInput.addEventListener("change", () => this.combineParts());
            // Combine the changed time with the current date into the hidden datetime input and dispatch its
            // input/change events.
            this.timeInput.addEventListener("change", () => this.combineParts());
        }

        populateParts() {
            const value = this.masterInput.value || "";
            const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value);
            if (match) {
                this.dateInput.value = match[1];
                this.timeInput.value = match[2];
            }
        }

        combineParts() {
            this.masterInput.value = this.dateInput.value && this.timeInput.value
                ? `${this.dateInput.value}T${this.timeInput.value}`
                : "";
            dispatchValueChange(this.masterInput);
        }
    }

    document.querySelectorAll("[data-custom-datetime]").forEach(
        (root) => new DateTimeComposite(root)
    );
    document.querySelectorAll("[data-custom-select]").forEach(
        (root) => new CustomSelect(root)
    );
    document.querySelectorAll("[data-date-picker]").forEach(
        (root) => new DatePicker(root)
    );
    document.querySelectorAll("[data-time-picker]").forEach(
        (root) => new TimePicker(root)
    );

    // Close any open custom popover when a click lands outside its root, leaving clicks inside the active control
    // untouched.
    document.addEventListener("click", (event) => {
        document.querySelectorAll("[data-custom-popover-open='true']").forEach((root) => {
            if (!root.contains(event.target)) {
                root.dispatchEvent(new CustomEvent("popadoo:close-control"));
            }
        });
    });

    // Close every open custom popover on Escape so keyboard users can dismiss select, date, and time controls
    // consistently.
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            document.querySelectorAll("[data-custom-popover-open='true']").forEach((root) => {
                root.dispatchEvent(new CustomEvent("popadoo:close-control"));
            });
        }
    });

    /* Refresh language labels and formatted dates/times after the site language changes. */
    // This listener responds to the popadoo:language-applied event and keeps the enhanced interface aligned with the visitor’s action.
    document.addEventListener("popadoo:language-applied", () => {
        document.querySelectorAll("[data-custom-select-input]").forEach((input) => {
            input.dispatchEvent(new Event("change", { bubbles: false }));
        });
        document.querySelectorAll("[data-date-picker] input[type='hidden']").forEach((input) => {
            input.dispatchEvent(new Event("change", { bubbles: false }));
        });
        document.querySelectorAll("[data-time-picker] input[type='hidden']").forEach((input) => {
            input.dispatchEvent(new Event("change", { bubbles: false }));
        });
    });
})();
