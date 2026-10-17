// Settings - CRUD for locations, the reference list plans are tagged with.
//
// Each location can be filled in two ways, and both always work: search
// (the Google place lookup, proxied through /api/locations/lookup so the
// API key stays server-side) fills in name/city/region/country and pins
// the location to a real place; or type the fields yourself. If the
// lookup isn't configured or Google errors, the search box says so and
// typing is all that's left - nothing else depends on it.

const LOCATIONS_API = "/api/locations";
let lookupAvailable = false;

const FIELDS = [
  { key: "name", label: "Name", placeholder: "e.g. Salem, MA", required: true },
  { key: "city", label: "City", placeholder: "Salem" },
  { key: "region", label: "State / region", placeholder: "Massachusetts" },
  { key: "country", label: "Country", placeholder: "United States" },
];

// Text inputs for every editable field, plus the lookup-only values
// (place_id, latitude, longitude) carried alongside them. `values()`
// returns the full payload for a POST/PATCH.
function buildLocationFields(location = {}) {
  const inputs = {};
  const fieldEls = FIELDS.map((f) => {
    const input = Global.el("input", { type: "text", value: location[f.key] || "", placeholder: f.placeholder });
    if (f.required) input.required = true;
    inputs[f.key] = input;
    return Global.el("div", { class: "field" }, [Global.el("label", { text: f.label }), input]);
  });

  let pinned = {
    place_id: location.place_id || null,
    latitude: location.latitude ?? null,
    longitude: location.longitude ?? null,
  };
  const verified = Global.el("p", { class: "place-verified" });
  const unpin = Global.el("button", {
    type: "button",
    class: "link-btn",
    text: "unlink",
    onclick: () => {
      pinned = { place_id: null, latitude: null, longitude: null };
      renderVerified();
    },
  });
  function renderVerified() {
    verified.innerHTML = "";
    if (pinned.place_id) {
      verified.append("✓ Matched to a real place via Google - ", unpin);
    } else {
      verified.textContent = "Not matched to a place - entered by hand.";
    }
  }
  renderVerified();

  return {
    element: Global.el("div", {}, [Global.el("div", { class: "item-fields" }, fieldEls), verified]),
    fill(details) {
      for (const f of FIELDS) inputs[f.key].value = details[f.key] || "";
      pinned = { place_id: details.place_id, latitude: details.latitude, longitude: details.longitude };
      renderVerified();
    },
    values() {
      const out = {};
      for (const f of FIELDS) out[f.key] = inputs[f.key].value.trim() || null;
      return { ...out, ...pinned };
    },
    focus() {
      inputs.name.focus();
    },
  };
}

// The search box: debounced autocomplete, then full details for whichever
// suggestion is picked, handed to onPick. Fails soft - any error is shown
// inline and typing the fields by hand still works.
function buildPlaceSearch(onPick, initialQuery = "") {
  // type=text, not type=search, so it picks up the shared theme's input styling.
  const input = Global.el("input", { type: "text", class: "place-search-input", enterkeyhint: "search", placeholder: "Search for a place…", value: initialQuery });
  const results = Global.el("div", { class: "place-results" });
  const note = Global.el("p", { class: "settings-note" });
  let timer = null;
  let seq = 0;

  async function search() {
    const q = input.value.trim();
    const mine = ++seq;
    results.innerHTML = "";
    note.textContent = "";
    if (q.length < 2) return;
    try {
      const suggestions = await Global.fetchJSON(`${LOCATIONS_API}/lookup?q=${encodeURIComponent(q)}`);
      if (mine !== seq) return; // a newer keystroke's search already ran
      if (!suggestions.length) note.textContent = "No matches - try another spelling, or fill the fields in yourself.";
      for (const s of suggestions) {
        results.appendChild(
          Global.el("button", {
            type: "button",
            class: "place-result",
            text: s.label,
            onclick: async () => {
              try {
                onPick(await Global.fetchJSON(`${LOCATIONS_API}/lookup/${encodeURIComponent(s.place_id)}`));
                results.innerHTML = "";
              } catch (err) {
                note.textContent = `${err.message} - fill the fields in yourself instead.`;
              }
            },
          })
        );
      }
    } catch (err) {
      if (mine === seq) note.textContent = `${err.message} - fill the fields in yourself instead.`;
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(search, 300);
  });
  if (initialQuery) search();

  return Global.el("div", { class: "field place-search" }, [Global.el("label", { text: "Look up" }), input, results, note]);
}

async function saveLocation(method, url, payload) {
  if (!payload.name) {
    Global.showMessage("Name is required.", "error");
    return false;
  }
  try {
    await Global.fetchJSON(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return true;
  } catch (err) {
    Global.showMessage(err.message, "error");
    return false;
  }
}

function locationSummaryText(loc) {
  return [loc.city !== loc.name ? loc.city : null, loc.region, loc.country].filter(Boolean).join(", ");
}

// Collapsed-by-default accordion, same pattern as the plan cards - a
// one-line summary that expands into the edit form in place.
function locationCard(loc) {
  const card = Global.el("div", { class: "item-card", "data-id": loc.id });
  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": "false" });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: loc.name }));
  const where = locationSummaryText(loc);
  if (where) summary.appendChild(Global.el("span", { class: "item-badge", text: where }));
  if (loc.place_id) summary.appendChild(Global.el("span", { class: "item-badge", title: "Matched to a real place", text: "✓" }));
  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details hidden" });
  Global.wireAccordionToggle(card, summary, details);

  const fields = buildLocationFields(loc);
  const inner = Global.el("div", { class: "item-details-inner" });
  if (lookupAvailable) inner.appendChild(buildPlaceSearch(fields.fill));
  inner.appendChild(fields.element);
  inner.appendChild(
    Global.el("div", { class: "item-actions" }, [
      Global.el("button", {
        type: "button",
        class: "danger-btn",
        text: "Delete",
        onclick: async () => {
          if (!confirm(`Delete "${loc.name}"?`)) return;
          try {
            await Global.fetchJSON(`${LOCATIONS_API}/${loc.id}`, { method: "DELETE" });
            Global.showMessage("Deleted.", "success");
            refresh();
          } catch (err) {
            Global.showMessage(err.message, "error");
          }
        },
      }),
      Global.el("button", {
        type: "button",
        class: "save-btn",
        text: "Save",
        onclick: async () => {
          if (await saveLocation("PATCH", `${LOCATIONS_API}/${loc.id}`, fields.values())) {
            Global.showMessage("Saved.", "success");
            refresh();
          }
        },
      }),
    ])
  );
  details.appendChild(inner);
  card.append(summary, details);
  return card;
}

function initAddLocation() {
  const showBtn = document.getElementById("show-add-location");
  const cardEl = document.getElementById("add-location-card");
  let fields;

  function render() {
    cardEl.innerHTML = "";
    fields = buildLocationFields();
    if (lookupAvailable) {
      cardEl.appendChild(buildPlaceSearch(fields.fill));
    } else {
      cardEl.appendChild(Global.el("p", { class: "settings-note", text: "Place lookup isn't set up (no Google Maps key) - fill the fields in yourself." }));
    }
    cardEl.appendChild(fields.element);
    cardEl.appendChild(
      Global.el("div", { class: "item-actions" }, [
        Global.el("button", { type: "button", class: "cancel-btn", text: "Cancel", onclick: close }),
        Global.el("button", {
          type: "button",
          class: "save-btn",
          text: "Add location",
          onclick: async () => {
            if (await saveLocation("POST", LOCATIONS_API, fields.values())) {
              Global.showMessage("Added.", "success");
              close();
              refresh();
            }
          },
        }),
      ])
    );
  }

  function close() {
    cardEl.classList.add("hidden");
    showBtn.classList.remove("hidden");
  }

  showBtn.addEventListener("click", () => {
    render();
    cardEl.classList.remove("hidden");
    showBtn.classList.add("hidden");
    const search = cardEl.querySelector(".place-search-input");
    (search || cardEl.querySelector("input")).focus();
  });
}

async function refresh() {
  const locations = await Global.fetchJSON(LOCATIONS_API);
  const list = document.getElementById("location-list");
  list.innerHTML = "";
  document.getElementById("location-count").textContent = locations.length ? `${locations.length}` : "";
  locations.forEach((loc) => list.appendChild(locationCard(loc)));
  if (!locations.length) list.appendChild(Global.el("p", { class: "empty-state", text: "No locations yet." }));
}

async function init() {
  try {
    lookupAvailable = (await Global.fetchJSON(`${LOCATIONS_API}/lookup/available`)).available;
  } catch (err) {
    lookupAvailable = false;
  }
  initAddLocation();
  refresh();
}

init();
