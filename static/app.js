const API_BASE = "/api/ideas";

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `${url} -> ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (e) {
      // ignore, use default detail
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function toISODate(isoDateTime) {
  if (!isoDateTime) return "";
  return isoDateTime.slice(0, 10);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

async function loadIdeas() {
  const ideas = await fetchJSON(API_BASE);
  renderIdeas(ideas);
}

function renderIdeas(ideas) {
  const list = document.getElementById("ideas-list");
  const emptyState = document.getElementById("empty-state");
  const count = document.getElementById("idea-count");
  list.innerHTML = "";
  count.textContent = ideas.length ? `${ideas.length}` : "";
  emptyState.hidden = ideas.length !== 0;
  for (const idea of ideas) {
    list.appendChild(renderCard(idea));
  }
}

function renderCard(idea) {
  const card = el("div", { class: "idea-card", "data-id": idea.id });

  // --- header: name (editable inline) + delete ---
  const nameEl = el("span", { class: "idea-name", text: idea.name });
  nameEl.addEventListener("click", () => enterEditMode(card, idea));

  const deleteBtn = el("button", {
    class: "icon-btn delete-btn",
    title: "Delete idea",
    text: "×",
    onclick: () => deleteIdea(idea.id),
  });

  card.appendChild(el("div", { class: "idea-header" }, [nameEl, deleteBtn]));

  // --- date row: always-editable date input, per requirement ---
  const dateInput = el("input", {
    type: "date",
    class: "date-input",
    value: toISODate(idea.event_date),
  });
  dateInput.addEventListener("change", async () => {
    const updated = await fetchJSON(`${API_BASE}/${idea.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_date: dateInput.value ? `${dateInput.value}T00:00:00` : null }),
    });
    Object.assign(idea, updated);
  });
  card.appendChild(el("div", { class: "idea-date-row" }, [el("label", { text: "Date" }), dateInput]));

  // --- description ---
  if (idea.description) {
    card.appendChild(el("p", { class: "idea-description", text: idea.description }));
  }

  // --- url + scrape controls ---
  if (idea.url) {
    const urlRow = el("div", { class: "idea-url-row" });
    urlRow.appendChild(el("a", { href: idea.url, target: "_blank", rel: "noopener noreferrer", class: "idea-url", text: idea.url }));
    const scrapeBtn = el("button", {
      class: "scrape-btn",
      text: idea.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
      onclick: async (e) => {
        e.target.disabled = true;
        e.target.textContent = "Fetching...";
        try {
          const updated = await fetchJSON(`${API_BASE}/${idea.id}/scrape`, { method: "POST" });
          Object.assign(idea, updated);
          card.replaceWith(renderCard(idea));
        } catch (err) {
          e.target.disabled = false;
          e.target.textContent = "Fetch preview";
          alert(`Scrape failed: ${err.message}`);
        }
      },
    });
    urlRow.appendChild(scrapeBtn);
    card.appendChild(urlRow);

    card.appendChild(renderScrapeStatus(idea));
  }

  return card;
}

function renderScrapeStatus(idea) {
  if (idea.scrape_status === "success") {
    const preview = el("div", { class: "scrape-preview" });
    if (idea.scraped_image_url) {
      preview.appendChild(el("img", { src: idea.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = el("div", { class: "scrape-text" });
    if (idea.scraped_title) textWrap.appendChild(el("div", { class: "scrape-title", text: idea.scraped_title }));
    if (idea.scraped_description) textWrap.appendChild(el("div", { class: "scrape-description", text: idea.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (idea.scrape_status === "failed") {
    return el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${idea.scrape_error || "unknown error"}` });
  }
  if (idea.scrape_status === "unsupported") {
    return el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return el("div", { class: "scrape-note", text: "" });
}

function enterEditMode(card, idea) {
  card.innerHTML = "";

  const nameInput = el("input", { type: "text", class: "edit-input", value: idea.name, required: "required" });
  const descInput = el("textarea", { class: "edit-input", rows: "2" }, [idea.description || ""]);
  descInput.value = idea.description || "";
  const urlInput = el("input", { type: "url", class: "edit-input", value: idea.url || "" });

  const saveBtn = el("button", {
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      if (!nameInput.value.trim()) {
        alert("Name is required");
        return;
      }
      const updated = await fetchJSON(`${API_BASE}/${idea.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nameInput.value.trim(),
          description: descInput.value.trim() || null,
          url: urlInput.value.trim() || null,
        }),
      });
      Object.assign(idea, updated);
      card.replaceWith(renderCard(idea));
    },
  });
  const cancelBtn = el("button", { class: "cancel-btn", text: "Cancel", onclick: () => card.replaceWith(renderCard(idea)) });

  card.appendChild(el("div", { class: "field" }, [el("label", { text: "Name" }), nameInput]));
  card.appendChild(el("div", { class: "field" }, [el("label", { text: "Description" }), descInput]));
  card.appendChild(el("div", { class: "field" }, [el("label", { text: "URL" }), urlInput]));
  card.appendChild(el("div", { class: "edit-actions" }, [saveBtn, cancelBtn]));
}

async function deleteIdea(id) {
  if (!confirm("Delete this idea?")) return;
  await fetchJSON(`${API_BASE}/${id}`, { method: "DELETE" });
  loadIdeas();
}

document.getElementById("new-idea-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const name = form.name.value.trim();
  if (!name) return;
  const payload = {
    name,
    description: form.description.value.trim() || null,
    url: form.url.value.trim() || null,
    event_date: form.event_date.value ? `${form.event_date.value}T00:00:00` : null,
  };
  await fetchJSON(API_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  form.reset();
  loadIdeas();
});

loadIdeas().catch((err) => console.error("Failed to load ideas", err));
