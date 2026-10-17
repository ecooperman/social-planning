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
  allPlans = await Global.fetchJSON(API_BASE);
  initFilters();
  renderPlans();
}

// --- filters ----------------------------------------------------------------
//
// All client-side over the full list (it's loaded whole anyway), same as
// trip-planning's places page: each multiselect narrows by its own field,
// empty means "any", and they combine with AND. Search matches name and
// description.

let allPlans = [];
const filters = { location: new Set(), source: new Set(), trips: new Set(), check: new Set(), search: "" };
const NO_LOCATION = "none";

function onTrip(plan) {
  return linksForPlan(plan.id).some((link) => link.trip_id);
}

// --- parsed location -----------------------------------------------------
//
// Imported plans carry where Claude read the place to be from its caption
// (parsed_city/region/country - see models.Plan), next to the location the
// whole import was filed under. locationCheck compares the most specific
// level both have: city (and region too, when both have one, so Salem MA
// vs Salem OR doesn't pass), else region, else country.

function parsedLocationLabel(plan) {
  return [plan.parsed_city, plan.parsed_region, plan.parsed_country].filter(Boolean).join(", ");
}

function locationCheck(plan) {
  const loc = plan.location;
  if (!loc || !parsedLocationLabel(plan)) return "unknown";
  const same = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase();
  const city = loc.city && loc.city.name;
  const region = loc.region && loc.region.name;
  const country = loc.country && loc.country.name;
  if (plan.parsed_city && city) {
    if (!same(plan.parsed_city, city)) return "different";
    return plan.parsed_region && region && !same(plan.parsed_region, region) ? "different" : "match";
  }
  if (plan.parsed_region && region) return same(plan.parsed_region, region) ? "match" : "different";
  if (plan.parsed_country && country) return same(plan.parsed_country, country) ? "match" : "different";
  return "unknown";
}

function planMatches(plan) {
  if (filters.location.size && !filters.location.has(plan.location_id == null ? NO_LOCATION : String(plan.location_id))) return false;
  if (filters.source.size && !filters.source.has(plan.imported ? "imported" : "manual")) return false;
  if (filters.trips.size && !filters.trips.has(onTrip(plan) ? "on" : "off")) return false;
  if (filters.check.size && !filters.check.has(locationCheck(plan))) return false;
  if (filters.search) {
    const haystack = `${plan.name} ${plan.description || ""}`.toLowerCase();
    if (!haystack.includes(filters.search)) return false;
  }
  return true;
}

function filtersActive() {
  return (
    filters.location.size > 0 ||
    filters.source.size > 0 ||
    filters.trips.size > 0 ||
    filters.check.size > 0 ||
    filters.search !== ""
  );
}

function renderPlans() {
  const list = document.getElementById("plans-list");
  list.innerHTML = "";
  const shown = allPlans.filter(planMatches);
  for (const plan of shown) list.appendChild(planCardElement(plan));
  updatePlanCounts(shown.length);
}

function updatePlanCounts(shownCount = document.querySelectorAll("#plans-list .item-card").length) {
  const count = document.getElementById("plan-count");
  count.textContent = !allPlans.length ? "" : filtersActive() ? `${shownCount} of ${allPlans.length}` : `${allPlans.length}`;
  document.getElementById("empty-state").hidden = allPlans.length !== 0;
  document.getElementById("filtered-empty").hidden = !(allPlans.length > 0 && shownCount === 0 && filtersActive());
}

function filterMultiSelect(mountId, key, options, placeholder) {
  const mount = document.getElementById(mountId);
  mount.innerHTML = "";
  // Drop any selection whose option no longer exists (e.g. a location that
  // no plan uses any more) so it can't silently hide everything.
  const valid = new Set(options.map((o) => String(o.value)));
  filters[key] = new Set([...filters[key]].filter((v) => valid.has(v)));
  mount.appendChild(
    Global.buildMultiSelect({
      options,
      selected: [...filters[key]],
      placeholder,
      onChange: (selected) => {
        filters[key] = new Set(selected);
        renderPlans();
      },
    })
  );
}

// Rebuilt after every full reload, so the location options track which
// locations plans actually use.
function initFilters() {
  const used = new Map();
  let anyWithout = false;
  for (const plan of allPlans) {
    if (plan.location) used.set(plan.location.id, plan.location.name);
    else anyWithout = true;
  }
  const locationOptions = [...used.entries()]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .map(([id, name]) => ({ value: id, label: name }));
  if (anyWithout) locationOptions.push({ value: NO_LOCATION, label: "No location" });
  filterMultiSelect("location-filter-mount", "location", locationOptions, "All locations");

  filterMultiSelect(
    "source-filter-mount",
    "source",
    [
      { value: "imported", label: "Imported" },
      { value: "manual", label: "Added by hand" },
    ],
    "All sources"
  );

  // Only meaningful when the trips app answered - see loadTripsLink.
  filterMultiSelect(
    "check-filter-mount",
    "check",
    [
      { value: "match", label: "Caption matches location" },
      { value: "different", label: "Caption suggests elsewhere" },
      { value: "unknown", label: "Caption doesn't say" },
    ],
    "Any location check"
  );

  const tripsMount = document.getElementById("trips-filter-mount");
  if (tripsAvailable) {
    filterMultiSelect(
      "trips-filter-mount",
      "trips",
      [
        { value: "on", label: "On a trip" },
        { value: "off", label: "Not on a trip yet" },
      ],
      "Any trip status"
    );
  } else {
    tripsMount.innerHTML = "";
    filters.trips = new Set();
  }
}

// --- export -----------------------------------------------------------------
//
// Exactly what the filters currently show, as a CSV built right here from
// the loaded list (no server round trip, so it can't drift from what's on
// screen). The leading byte-order mark makes Excel read it as UTF-8, so
// accented names and emoji in Instagram captions come through intact.

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function exportPlans() {
  const shown = allPlans.filter(planMatches);
  if (!shown.length) {
    Global.showMessage("No plans to export with the current filters.", "error");
    return;
  }
  const header = [
    "Name",
    "Description",
    "URL",
    "Location",
    "City",
    "State / region",
    "Country",
    "Parsed location",
    "Location check",
    "Date",
    "Source",
    "Trips",
    "Added",
  ];
  const checkLabels = { match: "Matches", different: "Different", unknown: "Unknown" };
  const rows = shown.map((plan) => {
    const loc = plan.location;
    const trips = [...new Set(linksForPlan(plan.id).map((l) => l.trip_location || "Activity (no trip)"))].join("; ");
    return [
      plan.name,
      plan.description,
      plan.url,
      loc && loc.name,
      loc && loc.city && loc.city.name,
      loc && loc.region && loc.region.name,
      loc && loc.country && loc.country.name,
      parsedLocationLabel(plan),
      checkLabels[locationCheck(plan)],
      Global.toISODate(plan.event_date),
      plan.imported ? "Imported" : "Added by hand",
      trips,
      Global.toISODate(plan.created_at),
    ];
  });
  const csv = "\ufeff" + [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");

  // Name the file after the one location filtered to, when it's just one.
  const onlyLocation =
    filters.location.size === 1 ? allPlans.find((p) => String(p.location_id) === [...filters.location][0])?.location?.name : null;
  const slug = (onlyLocation || "plans").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const link = Global.el("a", {
    href: URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })),
    download: `${slug}-${new Date().toISOString().slice(0, 10)}.csv`,
  });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  Global.showMessage(`Exported ${shown.length} plan${shown.length === 1 ? "" : "s"}.`, "success");
}

function initSearch() {
  const input = document.getElementById("plan-search");
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      filters.search = input.value.trim().toLowerCase();
      renderPlans();
    }, 200);
  });
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

  if (locationCheck(plan) === "different") {
    summary.appendChild(
      Global.el("span", {
        class: "item-badge item-badge-warning",
        title: `The caption suggests this is in ${parsedLocationLabel(plan)}, not ${plan.location.name}`,
        text: `⚠ ${[plan.parsed_city, plan.parsed_region].filter(Boolean).join(", ") || plan.parsed_country}`,
      })
    );
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

  if (plan.imported) {
    wrap.appendChild(buildCaptionSection(plan));
  }

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
      allPlans = allPlans.filter((p) => p.id !== plan.id);
      Global.showMessage(`Deleted "${plan.name}".`, "success");
      updatePlanCounts();
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
        allPlans = allPlans.map((p) => (p.id === updated.id ? updated : p));
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

// What the import read off the source post: where the caption says the
// place is, and the caption itself (collapsed - they can be long).
function buildCaptionSection(plan) {
  const check = locationCheck(plan);
  const parsed = parsedLocationLabel(plan);
  let text;
  if (!plan.caption) text = "Not re-checked yet - re-import this collection with Re-check posts already imported.";
  else if (!parsed) text = "The caption doesn't say where this is.";
  else if (check === "different") text = `The caption suggests ${parsed} - not ${plan.location.name}.`;
  else text = `The caption suggests ${parsed}.`;

  const section = Global.el("div", { class: "caption-section" }, [
    Global.el("label", { text: "From the Instagram post" }),
    Global.el("p", { class: "caption-parsed" + (check === "different" ? " caption-parsed-warning" : ""), text }),
  ]);
  if (plan.caption) {
    section.appendChild(
      Global.el("details", { class: "caption-original" }, [
        Global.el("summary", { text: "Original caption" }),
        Global.el("p", { text: plan.caption }),
      ])
    );
  }
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
initSearch();
document.getElementById("export-plans").addEventListener("click", exportPlans);
Promise.all([loadLocations(), loadTripsLink()])
  .then(loadPlans)
  .catch((err) => console.error("Failed to load plans", err));
