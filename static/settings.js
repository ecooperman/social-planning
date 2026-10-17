// Settings - locations, and the country -> state/region -> city lists they
// point into.
//
// A location's place is picked level by level from cascading dropdowns:
// each lists the existing entries under the level above, plus "+ New ..."
// to add one in place (created on save, under the right parent - see
// crud.resolve_place). The optional Google search (proxied through
// /api/locations/lookup so the key stays server-side) fills every level in
// at once, reusing entries that already exist. If the lookup isn't
// configured or Google errors, the dropdowns still work on their own.

const LOCATIONS_API = "/api/locations";
const API = "/api";
const NEW = "__new__";
let lookupAvailable = false;
let countries = [];

// --- one level of the place hierarchy -------------------------------------
//
// A <select> of existing entries plus "+ New ...", which reveals a text box
// for the new name. setItems(..., {disabledText}) greys the whole level out
// with a reason, e.g. "Choose a country first".
function buildPicker({ label, emptyText, newText, newPlaceholder, onChange }) {
  const select = Global.el("select");
  const newInput = Global.el("input", { type: "text", class: "place-new-input hidden", placeholder: newPlaceholder });
  const hint = Global.el("p", { class: "place-hint" });

  function syncNewInput() {
    newInput.classList.toggle("hidden", select.value !== NEW);
  }
  select.addEventListener("change", () => {
    syncNewInput();
    if (select.value === NEW) newInput.focus();
    onChange();
  });

  return {
    element: Global.el("div", { class: "field" }, [Global.el("label", { text: label }), select, newInput, hint]),
    hint,
    setItems(items, { disabledText = null } = {}) {
      select.innerHTML = "";
      newInput.value = "";
      if (disabledText) {
        select.appendChild(Global.el("option", { value: "", text: disabledText }));
        select.disabled = true;
      } else {
        select.disabled = false;
        select.appendChild(Global.el("option", { value: "", text: emptyText }));
        for (const item of items) select.appendChild(Global.el("option", { value: String(item.id), text: item.name }));
        select.appendChild(Global.el("option", { value: NEW, text: newText }));
      }
      syncNewInput();
    },
    setValue(id) {
      select.value = id == null ? "" : String(id);
      syncNewInput();
    },
    setNew(name) {
      if (select.disabled) return;
      select.value = NEW;
      newInput.value = name;
      syncNewInput();
    },
    isNew: () => select.value === NEW,
    selectedId: () => (select.value && select.value !== NEW ? Number(select.value) : null),
    newName: () => (select.value === NEW ? newInput.value.trim() : ""),
    displayName: () =>
      select.value === NEW ? newInput.value.trim() : select.value ? select.selectedOptions[0].textContent : "",
  };
}

// --- the location form's fields --------------------------------------------

function buildLocationFields(location = {}) {
  const nameInput = Global.el("input", { type: "text", value: location.name || "", placeholder: "e.g. Salem, MA", required: "required" });

  let countryHasRegions = false;
  const country = buildPicker({
    label: "Country",
    emptyText: "— Choose a country —",
    newText: "+ New country…",
    newPlaceholder: "Country name",
    onChange: async () => {
      await loadRegionOptions();
      await loadCityOptions();
    },
  });
  const region = buildPicker({
    label: "State / region",
    emptyText: "— None —",
    newText: "+ New state / region…",
    newPlaceholder: "State, province, or region",
    onChange: () => loadCityOptions(),
  });
  const city = buildPicker({
    label: "City",
    emptyText: "— None —",
    newText: "+ New city…",
    newPlaceholder: "City name",
    onChange: () => {},
  });

  async function loadRegionOptions() {
    countryHasRegions = false;
    if (country.isNew()) {
      region.setItems([]);
    } else if (!country.selectedId()) {
      region.setItems([], { disabledText: "— Choose a country first —" });
    } else {
      const regions = await Global.fetchJSON(`${API}/regions?country_id=${country.selectedId()}`);
      countryHasRegions = regions.length > 0;
      region.setItems(regions);
    }
  }

  // Which cities to offer depends on the level above: a chosen region's
  // cities; or, in a country with no regions at all, the cities that sit
  // directly under it. A country that has regions needs one picked first.
  async function loadCityOptions() {
    city.hint.textContent = "";
    if (!country.isNew() && !country.selectedId()) {
      city.setItems([], { disabledText: "— Choose a country first —" });
    } else if (region.isNew()) {
      city.setItems([]);
    } else if (region.selectedId()) {
      city.setItems(await Global.fetchJSON(`${API}/cities?region_id=${region.selectedId()}`));
    } else if (countryHasRegions) {
      city.setItems([], { disabledText: "— Choose a state / region first —" });
    } else {
      const items = country.selectedId()
        ? await Global.fetchJSON(`${API}/cities?country_id=${country.selectedId()}&no_region=true`)
        : [];
      city.setItems(items);
      const name = country.displayName() || "This country";
      city.hint.textContent = `${name} has no states or regions yet, so a city goes directly under the country. If it should have them, add one above first.`;
    }
  }

  // Sets all three levels in order, waiting for each level's options to
  // load before choosing within it.
  async function setPlace({ countryId, newCountry, regionId, newRegion, cityId, newCity }) {
    if (newCountry) country.setNew(newCountry);
    else country.setValue(countryId);
    await loadRegionOptions();
    if (newRegion) region.setNew(newRegion);
    else region.setValue(regionId);
    await loadCityOptions();
    if (newCity) city.setNew(newCity);
    else city.setValue(cityId);
  }

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
    if (pinned.place_id) verified.append("✓ Matched to a real place via Google - ", unpin);
    else verified.textContent = "Not matched to a place - entered by hand.";
  }
  renderVerified();

  country.setItems(countries);
  const ready = setPlace({ countryId: location.country_id, regionId: location.region_id, cityId: location.city_id });

  return {
    element: Global.el("div", {}, [
      Global.el("div", { class: "item-fields" }, [
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
        country.element,
        region.element,
        city.element,
      ]),
      verified,
    ]),
    ready,
    // From the Google lookup: select levels that already exist, offer the
    // rest as "+ New" prefilled with Google's name for them.
    async fill(details) {
      nameInput.value = details.name || "";
      await setPlace({
        countryId: details.country_id,
        newCountry: details.country_id ? null : details.country,
        regionId: details.region_id,
        newRegion: details.region_id ? null : details.region,
        cityId: details.city_id,
        newCity: details.city_id ? null : details.city,
      });
      pinned = { place_id: details.place_id, latitude: details.latitude, longitude: details.longitude };
      renderVerified();
    },
    // Returns [payload, error] - every place field is always sent, so a
    // save re-resolves the whole country/region/city set.
    values() {
      const name = nameInput.value.trim();
      if (!name) return [null, "Name is required."];
      if (!country.selectedId() && !country.newName()) return [null, "Choose a country, or add a new one."];
      if (region.isNew() && !region.newName()) return [null, "Type the new state / region's name, or pick None."];
      if (city.isNew() && !city.newName()) return [null, "Type the new city's name, or pick None."];
      return [
        {
          name,
          country_id: country.selectedId(),
          new_country: country.newName() || null,
          region_id: region.selectedId(),
          new_region: region.newName() || null,
          city_id: city.selectedId(),
          new_city: city.newName() || null,
          ...pinned,
        },
        null,
      ];
    },
  };
}

// The search box: debounced autocomplete, then full details for whichever
// suggestion is picked, handed to onPick. Fails soft - any error is shown
// inline and the dropdowns still work.
function buildPlaceSearch(onPick) {
  // type=text, not type=search, so it picks up the shared theme's input styling.
  const input = Global.el("input", { type: "text", class: "place-search-input", enterkeyhint: "search", placeholder: "Search for a place…" });
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
                await onPick(await Global.fetchJSON(`${LOCATIONS_API}/lookup/${encodeURIComponent(s.place_id)}`));
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

  return Global.el("div", { class: "field place-search" }, [Global.el("label", { text: "Look up" }), input, results, note]);
}

async function saveLocation(method, url, fields) {
  const [payload, error] = fields.values();
  if (error) {
    Global.showMessage(error, "error");
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

function locationWhere(loc) {
  return [loc.city && loc.city.name !== loc.name ? loc.city.name : null, loc.region && loc.region.name, loc.country && loc.country.name]
    .filter(Boolean)
    .join(", ");
}

// Collapsed-by-default accordion, same pattern as the plan cards - a
// one-line summary that expands into the edit form in place.
function locationCard(loc) {
  const card = Global.el("div", { class: "item-card", "data-id": loc.id });
  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": "false" });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: loc.name }));
  const where = locationWhere(loc);
  summary.appendChild(Global.el("span", { class: "item-badge", text: where || "needs a country" }));
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
          if (await saveLocation("PATCH", `${LOCATIONS_API}/${loc.id}`, fields)) {
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

  function close() {
    cardEl.classList.add("hidden");
    showBtn.classList.remove("hidden");
  }

  showBtn.addEventListener("click", () => {
    cardEl.innerHTML = "";
    const fields = buildLocationFields();
    if (lookupAvailable) {
      cardEl.appendChild(buildPlaceSearch(fields.fill));
    } else {
      cardEl.appendChild(Global.el("p", { class: "settings-note", text: "Place lookup isn't set up (no Google Maps key) - pick or add the country, state, and city yourself." }));
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
            if (await saveLocation("POST", LOCATIONS_API, fields)) {
              Global.showMessage("Added.", "success");
              close();
              refresh();
            }
          },
        }),
      ])
    );
    cardEl.classList.remove("hidden");
    showBtn.classList.add("hidden");
    (cardEl.querySelector(".place-search-input") || cardEl.querySelector("input")).focus();
  });
}

// --- countries / states / cities lists ------------------------------------

function geoRow(item, kind, context) {
  const input = Global.el("input", { type: "text", value: item.name });
  const children = [input];
  if (context) children.push(Global.el("span", { class: "settings-row-context", text: context }));
  children.push(
    Global.el("button", {
      type: "button",
      class: "secondary-btn",
      text: "Save",
      onclick: async () => {
        try {
          await Global.fetchJSON(`${API}/${kind}/${item.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: input.value.trim() }),
          });
          Global.showMessage("Saved.", "success");
          refresh();
        } catch (err) {
          Global.showMessage(err.message, "error");
        }
      },
    }),
    Global.el("button", {
      type: "button",
      class: "danger-btn",
      text: "Delete",
      onclick: async () => {
        if (!confirm(`Delete "${item.name}"?`)) return;
        try {
          await Global.fetchJSON(`${API}/${kind}/${item.id}`, { method: "DELETE" });
          Global.showMessage("Deleted.", "success");
          refresh();
        } catch (err) {
          Global.showMessage(err.message, "error");
        }
      },
    })
  );
  return Global.el("div", { class: "settings-row" }, children);
}

function renderGeoList(id, rows) {
  const list = document.getElementById(id);
  list.innerHTML = "";
  if (!rows.length) list.appendChild(Global.el("p", { class: "empty-state", text: "None yet." }));
  rows.forEach((row) => list.appendChild(row));
}

async function refreshGeoLists() {
  const [regions, cities] = await Promise.all([Global.fetchJSON(`${API}/regions`), Global.fetchJSON(`${API}/cities`)]);
  const countryName = Object.fromEntries(countries.map((c) => [c.id, c.name]));
  const regionName = Object.fromEntries(regions.map((r) => [r.id, r.name]));
  renderGeoList("country-list", countries.map((c) => geoRow(c, "countries")));
  renderGeoList("region-list", regions.map((r) => geoRow(r, "regions", countryName[r.country_id])));
  renderGeoList(
    "city-list",
    cities.map((c) => geoRow(c, "cities", [regionName[c.region_id], countryName[c.country_id]].filter(Boolean).join(", ")))
  );
}

// --- load -------------------------------------------------------------------

async function refresh() {
  const [locations, countryList] = await Promise.all([
    Global.fetchJSON(LOCATIONS_API),
    Global.fetchJSON(`${API}/countries`),
  ]);
  countries = countryList;
  const list = document.getElementById("location-list");
  list.innerHTML = "";
  document.getElementById("location-count").textContent = locations.length ? `${locations.length}` : "";
  locations.forEach((loc) => list.appendChild(locationCard(loc)));
  if (!locations.length) list.appendChild(Global.el("p", { class: "empty-state", text: "No locations yet." }));
  refreshGeoLists();
}

async function init() {
  try {
    lookupAvailable = (await Global.fetchJSON(`${LOCATIONS_API}/lookup/available`)).available;
  } catch (err) {
    lookupAvailable = false;
  }
  await refresh();
  initAddLocation();
}

init();
