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
  function parseJsonAttr(el, name) {
    try { return JSON.parse(el.dataset[name] || "null"); } catch (_) { return null; }
  }
  function dynamicValue(spec, fallback) {
    if (!spec || typeof spec !== "object") return fallback;
    if (Array.isArray(spec.cases)) {
      for (const item of spec.cases) {
        if (item && conditionMatches(item.when) && Object.prototype.hasOwnProperty.call(item, "value")) return Number(item.value);
      }
      return Number(Object.prototype.hasOwnProperty.call(spec, "default") ? spec.default : fallback);
    }
    if (typeof spec.field === "string") {
      const raw = fieldValue(spec.field);
      if (spec.values && typeof spec.values === "object" && Object.prototype.hasOwnProperty.call(spec.values, raw)) {
        return Number(spec.values[raw]);
      }
      if (spec.direct === true && raw !== undefined && raw !== null && raw !== "") return Number(raw);
    }
    return Number(Object.prototype.hasOwnProperty.call(spec, "default") ? spec.default : fallback);
  }
  function refreshVisibility() {
    document.querySelectorAll("[data-ttl-visible-when]").forEach(el => {
      try {
        const cond = JSON.parse(el.dataset.ttlVisibleWhen || "{}");
        el.hidden = !conditionMatches(cond);
      } catch (_) { el.hidden = false; }
    });
  }
  function rebuildValueCells(container) {
    let max = dynamicValue(parseJsonAttr(container, "dynamicMax"), Number(container.dataset.max || 0));
    let min = dynamicValue(parseJsonAttr(container, "dynamicMin"), Number(container.dataset.min || 0));
    let columns = dynamicValue(parseJsonAttr(container, "dynamicColumns"), Number(container.dataset.columns || 5));
    max = Math.max(min, Math.floor(max || 0));
    min = Math.floor(min || 0);
    columns = Math.max(1, Math.floor(columns || 1));
    container.dataset.max = String(max);
    container.dataset.min = String(min);
    container.dataset.columns = String(columns);
    if (container.dataset.widgetType === "grid") container.style.setProperty("--ttl-grid-columns", String(columns));
    const current = Math.max(min, Math.min(max, Number(container.dataset.value || 0)));
    container.dataset.value = String(current);
    const disabled = container.dataset.editable === "0";
    container.replaceChildren();
    for (let index = 1; index <= max; index++) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ttl-track-cell" + (index <= current ? " is-filled" : "");
      button.dataset.value = String(index);
      button.disabled = disabled;
      container.appendChild(button);
    }
    const hidden = inputFor(container.dataset.fieldId || "");
    if (hidden) {
      hidden.dataset.max = String(max);
      if (Number(hidden.value || 0) > max) hidden.value = String(max);
    }
    const scope = container.closest(".ttl-pack-field,.ttl-overlay-region") || container.parentElement;
    const number = scope?.querySelector("[data-ttl-widget-number]");
    const maxLabel = scope?.querySelector("[data-ttl-widget-max]");
    if (number) number.textContent = String(current);
    if (maxLabel) maxLabel.textContent = String(max);
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
  function normalizeStateRows(widget, count) {
    const hidden = inputFor(widget.dataset.fieldId || "");
    let rows = [];
    if (hidden) {
      try { rows = JSON.parse(hidden.value || "[]"); } catch (_) { rows = []; }
    }
    if (!Array.isArray(rows)) rows = [];
    const states = parseJsonAttr(widget, "states") || [];
    const stateField = widget.dataset.stateField || "state";
    const defaultState = states[0]?.id || "empty";
    rows = rows.slice(0, count).map(row => (row && typeof row === "object") ? row : {[stateField]: defaultState});
    while (rows.length < count) rows.push({[stateField]: defaultState});
    if (hidden) hidden.value = JSON.stringify(rows);
    return {rows, states, stateField, defaultState};
  }
  function rebuildStateCells(widget) {
    let count = dynamicValue(parseJsonAttr(widget, "dynamicCount"), Number(widget.dataset.count || 0));
    let columns = dynamicValue(parseJsonAttr(widget, "dynamicColumns"), Number(widget.dataset.columns || 5));
    count = Math.max(0, Math.floor(count || 0));
    columns = Math.max(1, Math.floor(columns || 1));
    widget.dataset.count = String(count);
    widget.dataset.columns = String(columns);
    if (widget.dataset.widgetType === "state_grid") widget.style.setProperty("--ttl-grid-columns", String(columns));
    const disabled = widget.dataset.editable === "0";
    const positions = parseJsonAttr(widget, "positions");
    widget.classList.toggle("ttl-state-map", Array.isArray(positions) && positions.length > 0);
    const {rows, states, stateField, defaultState} = normalizeStateRows(widget, count);
    widget.replaceChildren();
    rows.forEach((row, index) => {
      const sid = String(row[stateField] ?? defaultState);
      const state = states.find(s => String(s.id) === sid) || states[0] || {id:sid,label:sid};
      const button = document.createElement("button");
      button.type = "button";
      button.className = `ttl-track-cell ttl-state-cell is-state-${CSS.escape(String(state.id))}`;
      button.dataset.index = String(index);
      button.dataset.state = String(state.id);
      button.title = state.label || String(state.id);
      button.setAttribute("aria-label", `${index + 1}: ${state.label || state.id}`);
      button.disabled = disabled;
      if (Array.isArray(positions) && positions[index] && typeof positions[index] === "object") {
        const pos = positions[index];
        button.style.position = "absolute";
        button.style.left = `${Number(pos.x || 0)}%`;
        button.style.top = `${Number(pos.y || 0)}%`;
        if (pos.width != null) button.style.width = `${Number(pos.width)}%`;
        if (pos.height != null) button.style.height = `${Number(pos.height)}%`;
      }
      widget.appendChild(button);
    });
  }
  function refreshDynamicWidgets() {
    document.querySelectorAll("[data-ttl-value-widget]").forEach(rebuildValueCells);
    document.querySelectorAll("[data-ttl-state-widget]").forEach(rebuildStateCells);
    document.querySelectorAll("[data-ttl-counter]").forEach(counter => {
      const min = dynamicValue(parseJsonAttr(counter, "dynamicMin"), Number(counter.dataset.min || 0));
      const max = dynamicValue(parseJsonAttr(counter, "dynamicMax"), Number(counter.dataset.max || 999999));
      counter.dataset.min = String(min); counter.dataset.max = String(max);
    });
  }
  document.querySelectorAll("[data-ttl-value-widget]").forEach(container => {
    container.addEventListener("click", ev => {
      const cell = ev.target.closest(".ttl-track-cell");
      if (!cell || cell.disabled) return;
      const clicked = Number(cell.dataset.value);
      const current = Number(container.dataset.value || 0);
      setWidgetValue(container, clicked === current ? clicked - 1 : clicked);
    });
  });
  document.querySelectorAll("[data-ttl-state-widget]").forEach(widget => {
    widget.addEventListener("click", ev => {
      const cell = ev.target.closest(".ttl-state-cell");
      if (!cell || cell.disabled) return;
      const hidden = inputFor(widget.dataset.fieldId || "");
      if (!hidden) return;
      let rows = [];
      try { rows = JSON.parse(hidden.value || "[]"); } catch (_) { rows = []; }
      const states = parseJsonAttr(widget, "states") || [];
      if (!states.length) return;
      const stateField = widget.dataset.stateField || "state";
      const index = Number(cell.dataset.index);
      while (rows.length <= index) rows.push({[stateField]: states[0].id});
      const current = String(rows[index]?.[stateField] ?? states[0].id);
      const currentIndex = Math.max(0, states.findIndex(s => String(s.id) === current));
      const next = states[(currentIndex + 1) % states.length];
      rows[index] = {...(rows[index] || {}), [stateField]: next.id};
      hidden.value = JSON.stringify(rows);
      hidden.dispatchEvent(new Event("input", {bubbles:true}));
      hidden.dispatchEvent(new Event("change", {bubbles:true}));
      rebuildStateCells(widget);
    });
  });
  document.querySelectorAll("[data-ttl-counter]").forEach(counter => {
    counter.addEventListener("click", ev => {
      const button = ev.target.closest("button[data-delta]");
      if (!button || button.disabled) return;
      const hidden = inputFor(counter.dataset.fieldId || "") || counter.closest(".ttl-pack-field")?.querySelector("[data-ttl-widget-input]");
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
  document.addEventListener("input", ev => {
    refreshVisibility();
    if (!ev.target.closest("[data-ttl-state-widget],[data-ttl-value-widget],[data-ttl-counter]")) refreshDynamicWidgets();
  });
  document.addEventListener("change", ev => {
    refreshVisibility();
    if (!ev.target.closest("[data-ttl-state-widget],[data-ttl-value-widget],[data-ttl-counter]")) refreshDynamicWidgets();
  });
  refreshVisibility();
  refreshDynamicWidgets();
})();
