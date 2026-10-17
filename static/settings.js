// Settings - CRUD for locations, the reference list plans are tagged with.
// Deliberately plain: inline rows, no accordion (same as finances'
// settings page).

const LOCATIONS_API = "/api/locations";
const locationListEl = document.getElementById("location-list");

function locationRow(loc) {
  const nameInput = Global.el("input", { type: "text", value: loc.name });

  const save = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: "Save",
    onclick: async () => {
      try {
        await Global.fetchJSON(`${LOCATIONS_API}/${loc.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: nameInput.value.trim() }),
        });
        Global.showMessage("Saved.", "success");
        refresh();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });
  const del = Global.el("button", {
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
  });

  return Global.el("div", { class: "settings-row" }, [nameInput, save, del]);
}

document.getElementById("add-location-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  try {
    await Global.fetchJSON(LOCATIONS_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: form.name.value.trim() }),
    });
    form.reset();
    refresh();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
});

async function refresh() {
  const locations = await Global.fetchJSON(LOCATIONS_API);
  locationListEl.innerHTML = "";
  locations.forEach((loc) => locationListEl.appendChild(locationRow(loc)));
  if (!locations.length) {
    locationListEl.appendChild(Global.el("p", { class: "empty-state", text: "No locations yet." }));
  }
}

refresh();
