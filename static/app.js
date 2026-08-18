const API_BASE = "/api/ideas";

async function loadIdeas() {
  const ideas = await Global.fetchJSON(API_BASE);
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
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : ""), "data-id": idea.id });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: idea.name }));

  const domain = idea.url ? Global.domainFromUrl(idea.url) : null;
  if (domain) {
    const domainLink = Global.el("a", {
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

  const dateLabel = Global.formatDateBadge(idea.event_date);
  if (dateLabel) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  }

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

  Global.wireAccordionToggle(card, summary, details);

  card.append(summary, details);
  details.appendChild(buildIdeaDetails(card, idea));
  return card;
}

function buildIdeaDetails(card, idea) {
  const wrap = Global.el("div", { class: "item-details-inner" });

  const nameInput = Global.el("input", { type: "text", value: idea.name, required: "required" });
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = idea.description || "";
  const urlInput = Global.el("input", { type: "url", value: idea.url || "" });
  const dateInput = Global.el("input", { type: "date", value: Global.toISODate(idea.event_date) });

  const fields = Global.el("div", { class: "item-fields" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Date" }), dateInput]),
  ]);
  wrap.appendChild(fields);

  if (idea.url) {
    wrap.appendChild(buildScrapeSection(card, idea));
  }

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${idea.name}"?`)) return;
      await Global.fetchJSON(`${API_BASE}/${idea.id}`, { method: "DELETE" });
      card.remove();
      Global.showMessage(`Deleted "${idea.name}".`, "success");
      const count = document.getElementById("idea-count");
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
        const updated = await Global.fetchJSON(`${API_BASE}/${idea.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            event_date: Global.dateInputToISO(dateInput.value),
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        card.replaceWith(ideaCardElement(updated, { expanded: true }));
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildScrapeSection(card, idea) {
  const section = Global.el("div", { class: "scrape-section" });

  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: idea.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await Global.fetchJSON(`${API_BASE}/${idea.id}/scrape`, { method: "POST" });
        card.replaceWith(ideaCardElement(updated, { expanded: true }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapeStatus(idea));
  return section;
}

function renderScrapeStatus(idea) {
  if (idea.scrape_status === "success") {
    const preview = Global.el("div", { class: "scrape-preview" });
    if (idea.scraped_image_url) {
      preview.appendChild(Global.el("img", { src: idea.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Global.el("div", { class: "scrape-text" });
    if (idea.scraped_title) textWrap.appendChild(Global.el("div", { class: "scrape-title", text: idea.scraped_title }));
    if (idea.scraped_description) textWrap.appendChild(Global.el("div", { class: "scrape-description", text: idea.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (idea.scrape_status === "failed") {
    return Global.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${idea.scrape_error || "unknown error"}` });
  }
  if (idea.scrape_status === "unsupported") {
    return Global.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Global.el("div", { class: "scrape-note", text: "" });
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
      event_date: Global.dateInputToISO(form.event_date.value),
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
      loadIdeas();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

initAddIdeaForm();
loadIdeas().catch((err) => console.error("Failed to load ideas", err));
