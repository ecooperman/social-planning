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

function formatDateBadge(isoDateTime) {
  if (!isoDateTime) return null;
  const [y, m, d] = isoDateTime.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function domainFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (e) {
    return null;
  }
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
    list.appendChild(ideaCardElement(idea));
  }
}

// Each idea is a collapsed-by-default accordion: a single-line summary row
// (title, source domain, date) that expands into the full edit form in
// place - no separate "view" vs "edit" mode, and no modal. This mirrors the
// jobs admin page (jobs.html/jobs.js) in time-management, which solves the
// same "lots of rows, only show the full form for the one you're touching"
// problem the same way.
function ideaCardElement(idea, { expanded = false } = {}) {
  const card = Theme.el("div", { class: "item-card" + (expanded ? " expanded" : ""), "data-id": idea.id });

  const summary = Theme.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Theme.el("span", { class: "item-summary-title", text: idea.name }));

  const domain = idea.url ? domainFromUrl(idea.url) : null;
  if (domain) {
    const domainLink = Theme.el("a", {
      class: "item-badge item-badge-domain",
      href: idea.url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: domain,
    });
    // Opening the source link shouldn't also toggle the accordion.
    domainLink.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(domainLink);
  }

  const dateLabel = formatDateBadge(idea.event_date);
  if (dateLabel) {
    summary.appendChild(Theme.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  }

  summary.appendChild(Theme.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Theme.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

  Theme.wireAccordionToggle(card, summary, details);

  card.append(summary, details);
  details.appendChild(buildIdeaDetails(card, idea));
  return card;
}

function buildIdeaDetails(card, idea) {
  const wrap = Theme.el("div", { class: "item-details-inner" });

  const nameInput = Theme.el("input", { type: "text", value: idea.name, required: "required" });
  const descInput = Theme.el("textarea", { rows: "2" });
  descInput.value = idea.description || "";
  const urlInput = Theme.el("input", { type: "url", value: idea.url || "" });
  const dateInput = Theme.el("input", { type: "date", value: toISODate(idea.event_date) });

  const fields = Theme.el("div", { class: "item-fields" }, [
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Name" }), nameInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Description" }), descInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "URL" }), urlInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Date" }), dateInput]),
  ]);
  wrap.appendChild(fields);

  if (idea.url) {
    wrap.appendChild(buildScrapeSection(card, idea));
  }

  const actions = Theme.el("div", { class: "item-actions" });

  const deleteBtn = Theme.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${idea.name}"?`)) return;
      await fetchJSON(`${API_BASE}/${idea.id}`, { method: "DELETE" });
      card.remove();
      Theme.showMessage(`Deleted "${idea.name}".`, "success");
      const count = document.getElementById("idea-count");
      const remaining = document.querySelectorAll(".item-card").length;
      count.textContent = remaining ? `${remaining}` : "";
      document.getElementById("empty-state").hidden = remaining !== 0;
    },
  });

  const saveBtn = Theme.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Theme.showMessage("Name is required.", "error");
        return;
      }
      try {
        const updated = await fetchJSON(`${API_BASE}/${idea.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            event_date: dateInput.value ? `${dateInput.value}T00:00:00` : null,
          }),
        });
        Theme.showMessage(`Saved "${name}".`, "success");
        card.replaceWith(ideaCardElement(updated, { expanded: true }));
      } catch (err) {
        Theme.showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildScrapeSection(card, idea) {
  const section = Theme.el("div", { class: "scrape-section" });

  const scrapeBtn = Theme.el("button", {
    type: "button",
    class: "scrape-btn",
    text: idea.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await fetchJSON(`${API_BASE}/${idea.id}/scrape`, { method: "POST" });
        card.replaceWith(ideaCardElement(updated, { expanded: true }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Theme.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapeStatus(idea));
  return section;
}

function renderScrapeStatus(idea) {
  if (idea.scrape_status === "success") {
    const preview = Theme.el("div", { class: "scrape-preview" });
    if (idea.scraped_image_url) {
      preview.appendChild(Theme.el("img", { src: idea.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Theme.el("div", { class: "scrape-text" });
    if (idea.scraped_title) textWrap.appendChild(Theme.el("div", { class: "scrape-title", text: idea.scraped_title }));
    if (idea.scraped_description) textWrap.appendChild(Theme.el("div", { class: "scrape-description", text: idea.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (idea.scrape_status === "failed") {
    return Theme.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${idea.scrape_error || "unknown error"}` });
  }
  if (idea.scrape_status === "unsupported") {
    return Theme.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Theme.el("div", { class: "scrape-note", text: "" });
}

function initAddIdeaForm() {
  const form = document.getElementById("new-idea-form");
  const showBtn = document.getElementById("show-add-idea");
  const cancelBtn = document.getElementById("cancel-add-idea");

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
      event_date: form.event_date.value ? `${form.event_date.value}T00:00:00` : null,
    };
    try {
      await fetchJSON(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Theme.showMessage(`Added "${name}".`, "success");
      loadIdeas();
    } catch (err) {
      Theme.showMessage(err.message, "error");
    }
  });
}

initAddIdeaForm();
loadIdeas().catch((err) => console.error("Failed to load ideas", err));
