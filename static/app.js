const API_BASE = "/api/plans";
const LOCATIONS_API = "/api/locations";

// Loaded once per page load - the list is managed on settings.html, so
// adding a location there means reloading this page to pick it.
let locations = [];

async function loadLocations() {
  locations = await Global.fetchJSON(LOCATIONS_API);
  fillLocationSelect(document.getElementById("new-location"), null);
}

// Picked from a list, never typed - see models.Location's docstring.
function fillLocationSelect(select, selectedId) {
  select.innerHTML = "";
  select.appendChild(Global.el("option", { value: "", text: locations.length ? "— None —" : "— None (add some in Settings) —" }));
  for (const loc of locations) {
    select.appendChild(Global.el("option", { value: String(loc.id), text: loc.name }));
  }
  select.value = selectedId == null ? "" : String(selectedId);
}

function locationSelectValue(select) {
  return select.value ? Number(select.value) : null;
}

// --- trips link (trip-planning) -----------------------------------------------
// Activities created from plans live in the trips app (Activity.plan_id);
// this page proxies to it via /api/trips-link - see routers/trips_link.py.
// Loaded once alongside the plans, and failing soft: if the trips app is
// down, plans still load, just without the Trips section.

const TRIPS_LINK_API = "/api/trips-link";
let trips = [];
let tripLinks = [];
let tripsUrl = "";
let tripsAvailable = false;

async function loadTripsLink() {
  try {
    const [tripList, linkData] = await Promise.all([
      Global.fetchJSON(`${TRIPS_LINK_API}/trips`),
      Global.fetchJSON(`${TRIPS_LINK_API}/links`),
    ]);
    trips = tripList;
    tripLinks = linkData.links;
    tripsUrl = linkData.trips_url;
    tripsAvailable = true;
  } catch (err) {
    tripsAvailable = false;
    console.error("Trips app unavailable", err);
  }
}

function linksForPlan(planId) {
  return tripLinks.filter((link) => link.plan_id === planId);
}

async function loadPlans() {
  const plans = await Global.fetchJSON(API_BASE);
  renderPlans(plans);
}

function renderPlans(plans) {
  const list = document.getElementById("plans-list");
  const emptyState = document.getElementById("empty-state");
  const count = document.getElementById("plan-count");
  list.innerHTML = "";
  count.textContent = plans.length ? `${plans.length}` : "";
  emptyState.hidden = plans.length !== 0;
  for (const plan of plans) {
    list.appendChild(planCardElement(plan));
  }
}

// Each plan is a collapsed-by-default accordion: a single-line summary row
// (title, source domain, date) that expands into the full edit form in
// place - no separate "view" vs "edit" mode, and no modal. This mirrors the
// jobs admin page (jobs.html/jobs.js) in time-management, which solves the
// same "lots of rows, only show the full form for the one you're touching"
// problem the same way.
function planCardElement(plan, { expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : ""), "data-id": plan.id });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: plan.name }));

  const domain = plan.url ? Global.domainFromUrl(plan.url) : null;
  if (domain) {
    const domainLink = Global.el("a", {
      class: "item-badge item-badge-domain",
      href: plan.url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: domain,
    });
    // Opening the source link shouldn't also toggle the accordion.
    domainLink.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(domainLink);
  }

  if (plan.location) {
    summary.appendChild(Global.el("span", { class: "item-badge", text: plan.location.name }));
  }

  const onTrips = [...new Set(linksForPlan(plan.id).map((l) => l.trip_location).filter(Boolean))];
  if (onTrips.length) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-trip", text: `✈ ${onTrips.join(", ")}` }));
  }

  const dateLabel = Global.formatDateBadge(plan.event_date);
  if (dateLabel) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  }

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

  Global.wireAccordionToggle(card, summary, details);

  card.append(summary, details);
  details.appendChild(buildPlanDetails(card, plan));
  return card;
}

function buildPlanDetails(card, plan) {
  const wrap = Global.el("div", { class: "item-details-inner" });

  const nameInput = Global.el("input", { type: "text", value: plan.name, required: "required" });
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = plan.description || "";
  const urlInput = Global.el("input", { type: "url", value: plan.url || "" });
  const dateInput = Global.el("input", { type: "date", value: Global.toISODate(plan.event_date) });
  const locationSelect = Global.el("select");
  fillLocationSelect(locationSelect, plan.location_id);

  const fields = Global.el("div", { class: "item-fields" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Date" }), dateInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Location" }), locationSelect]),
  ]);
  wrap.appendChild(fields);

  if (plan.url) {
    wrap.appendChild(buildScrapeSection(card, plan));
  }

  if (tripsAvailable) {
    wrap.appendChild(buildTripsSection(card, plan));
  }

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${plan.name}"?`)) return;
      await Global.fetchJSON(`${API_BASE}/${plan.id}`, { method: "DELETE" });
      card.remove();
      Global.showMessage(`Deleted "${plan.name}".`, "success");
      const count = document.getElementById("plan-count");
      const remaining = document.querySelectorAll(".item-card").length;
      count.textContent = remaining ? `${remaining}` : "";
      document.getElementById("empty-state").hidden = remaining !== 0;
    },
  });

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Global.showMessage("Name is required.", "error");
        return;
      }
      try {
        const updated = await Global.fetchJSON(`${API_BASE}/${plan.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            event_date: Global.dateInputToISO(dateInput.value),
            location_id: locationSelectValue(locationSelect),
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        card.replaceWith(planCardElement(updated, { expanded: true }));
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildTripsSection(card, plan) {
  const section = Global.el("div", { class: "trips-section" });
  section.appendChild(Global.el("label", { text: "Trips" }));

  const links = linksForPlan(plan.id);
  if (links.length) {
    const list = Global.el("ul", { class: "trips-link-list" });
    for (const link of links) {
      const where = link.trip_id
        ? Global.el("a", { href: `${tripsUrl}/trip.html?id=${link.trip_id}`, target: "_blank", rel: "noopener", text: link.trip_location })
        : Global.el("a", { href: `${tripsUrl}/activities.html`, target: "_blank", rel: "noopener", text: "Activities (no trip yet)" });
      const status = link.done ? " · done" : link.archived ? " · archived" : "";
      list.appendChild(Global.el("li", {}, [where, status]));
    }
    section.appendChild(list);
  }

  const tripSelect = Global.el("select");
  tripSelect.appendChild(Global.el("option", { value: "", text: "— No trip, just an activity —" }));
  for (const trip of trips) {
    tripSelect.appendChild(Global.el("option", { value: String(trip.id), text: trip.location }));
  }

  const sendBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: "Send to trips",
    onclick: async () => {
      sendBtn.disabled = true;
      try {
        const result = await Global.fetchJSON(`${TRIPS_LINK_API}/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan_id: plan.id, trip_id: tripSelect.value ? Number(tripSelect.value) : null }),
        });
        const where = tripSelect.value ? tripSelect.selectedOptions[0].text : "trips as an activity";
        Global.showMessage(
          result.created ? `Sent "${plan.name}" to ${where}.` : `"${plan.name}" is already on ${where}.`,
          result.created ? "success" : "error"
        );
        await loadTripsLink();
        card.replaceWith(planCardElement(plan, { expanded: true }));
      } catch (err) {
        Global.showMessage(err.message, "error");
        sendBtn.disabled = false;
      }
    },
  });

  section.appendChild(Global.el("div", { class: "trips-send-row" }, [tripSelect, sendBtn]));
  return section;
}

function buildScrapeSection(card, plan) {
  const section = Global.el("div", { class: "scrape-section" });

  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: plan.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await Global.fetchJSON(`${API_BASE}/${plan.id}/scrape`, { method: "POST" });
        card.replaceWith(planCardElement(updated, { expanded: true }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapeStatus(plan));
  return section;
}

function renderScrapeStatus(plan) {
  if (plan.scrape_status === "success") {
    const preview = Global.el("div", { class: "scrape-preview" });
    if (plan.scraped_image_url) {
      preview.appendChild(Global.el("img", { src: plan.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Global.el("div", { class: "scrape-text" });
    if (plan.scraped_title) textWrap.appendChild(Global.el("div", { class: "scrape-title", text: plan.scraped_title }));
    if (plan.scraped_description) textWrap.appendChild(Global.el("div", { class: "scrape-description", text: plan.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (plan.scrape_status === "failed") {
    return Global.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${plan.scrape_error || "unknown error"}` });
  }
  if (plan.scrape_status === "unsupported") {
    return Global.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Global.el("div", { class: "scrape-note", text: "" });
}

function initAddPlanForm() {
  const form = document.getElementById("new-plan-form");
  const showBtn = document.getElementById("show-add-plan");
  const cancelBtn = document.getElementById("cancel-add-plan");

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    document.getElementById("new-name").focus();
  });

  cancelBtn.addEventListener("click", () => {
    form.reset();
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = form.name.value.trim();
    if (!name) return;
    const payload = {
      name,
      description: form.description.value.trim() || null,
      url: form.url.value.trim() || null,
      event_date: Global.dateInputToISO(form.event_date.value),
      location_id: locationSelectValue(form.location_id),
    };
    try {
      await Global.fetchJSON(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadPlans();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

initAddPlanForm();
Promise.all([loadLocations(), loadTripsLink()])
  .then(loadPlans)
  .catch((err) => console.error("Failed to load plans", err));
