(() => {
  function inputFor(fieldId) {
    return document.getElementById(`field__${fieldId}`) || document.querySelector(`[name="field__${CSS.escape(fieldId)}"]`);
  }
  function fieldValue(fieldId) {
    const el = inputFor(fieldId);
    if (!el) return undefined;
    if (el.type === "checkbox") return !!el.checked;
    if (el.multiple) return Array.from(el.selectedOptions).map(o => o.value);
    if (el.type === "number") return el.value === "" ? null : Number(el.value);
    return el.value;
  }
  function conditionMatches(cond) {
    if (!cond || typeof cond !== "object") return true;
    if (Array.isArray(cond.all)) return cond.all.every(conditionMatches);
    if (Array.isArray(cond.any)) return cond.any.some(conditionMatches);
    if (cond.not) return !conditionMatches(cond.not);
    const value = fieldValue(cond.field);
    if (Object.prototype.hasOwnProperty.call(cond, "equals")) return value == cond.equals;
    if (Object.prototype.hasOwnProperty.call(cond, "not_equals")) return value != cond.not_equals;
    if (Array.isArray(cond.in)) return cond.in.some(v => value == v);
    if (Array.isArray(cond.not_in)) return !cond.not_in.some(v => value == v);
    if (cond.exists === true) return value !== undefined && value !== null && value !== "";
    if (cond.exists === false) return value === undefined || value === null || value === "";
    if (cond.truthy === true) return !!value;
    if (cond.truthy === false) return !value;
    return true;
  }
  function refreshVisibility() {
    document.querySelectorAll("[data-ttl-visible-when]").forEach(el => {
      try {
        const cond = JSON.parse(el.dataset.ttlVisibleWhen || "{}");
        el.hidden = !conditionMatches(cond);
      } catch (_) { el.hidden = false; }
    });
  }
  function setWidgetValue(container, value) {
    const min = Number(container.dataset.min || 0);
    const max = Number(container.dataset.max || value);
    value = Math.max(min, Math.min(max, Number(value) || 0));
    container.dataset.value = String(value);
    const fieldId = container.dataset.fieldId;
    const hidden = fieldId ? inputFor(fieldId) : container.closest(".ttl-pack-field,.ttl-overlay-region")?.querySelector("[data-ttl-widget-input]");
    if (hidden) {
      hidden.value = String(value);
      hidden.dispatchEvent(new Event("input", {bubbles:true}));
      hidden.dispatchEvent(new Event("change", {bubbles:true}));
    }
    container.querySelectorAll(".ttl-track-cell").forEach(cell => {
      cell.classList.toggle("is-filled", Number(cell.dataset.value) <= value);
    });
    const scope = container.closest(".ttl-pack-field,.ttl-overlay-region") || container.parentElement;
    const number = scope?.querySelector("[data-ttl-widget-number]");
    if (number) number.textContent = String(value);
    refreshVisibility();
  }
  document.querySelectorAll("[data-ttl-value-widget]").forEach(container => {
    if (container.dataset.widgetType === "grid") {
      container.style.setProperty("--ttl-grid-columns", container.dataset.columns || "5");
    }
    container.addEventListener("click", ev => {
      const cell = ev.target.closest(".ttl-track-cell");
      if (!cell || cell.disabled) return;
      const clicked = Number(cell.dataset.value);
      const current = Number(container.dataset.value || 0);
      setWidgetValue(container, clicked === current ? clicked - 1 : clicked);
    });
  });
  document.querySelectorAll("[data-ttl-counter]").forEach(counter => {
    counter.addEventListener("click", ev => {
      const button = ev.target.closest("button[data-delta]");
      if (!button || button.disabled) return;
      const hidden = counter.closest(".ttl-pack-field")?.querySelector("[data-ttl-widget-input]");
      if (!hidden) return;
      const min = Number(counter.dataset.min || 0), max = Number(counter.dataset.max || 999999);
      const next = Math.max(min, Math.min(max, Number(hidden.value || 0) + Number(button.dataset.delta)));
      hidden.value = String(next);
      counter.dataset.value = String(next);
      const display = counter.querySelector("[data-ttl-widget-number]");
      if (display) display.textContent = String(next);
      hidden.dispatchEvent(new Event("input", {bubbles:true}));
      hidden.dispatchEvent(new Event("change", {bubbles:true}));
      refreshVisibility();
    });
  });
  document.addEventListener("input", refreshVisibility);
  document.addEventListener("change", refreshVisibility);
  refreshVisibility();
})();
