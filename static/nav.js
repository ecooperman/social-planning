// The bottom tab bar, built once here and mounted on every page via
// Global.buildNav (shared-assets/theme.js). Only the "which page is active"
// logic is app-specific and lives here.

function currentNavActive() {
  if (window.location.pathname === "/settings.html") return "settings";
  return "plans";
}

const active = currentNavActive();
Global.buildNav([
  { href: "/", icon: "list", label: "Plans", active: active === "plans" },
  { href: "/settings.html", icon: "settings", label: "Settings", active: active === "settings" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);
