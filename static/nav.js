// The bottom tab bar, built once here and mounted on every page via
// Global.buildNav (shared-assets/theme.js). Only the "which page is active"
// logic is app-specific and lives here.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/settings.html") return "settings";
  if (path === "/users.html") return "users";
  return "plans";
}

const active = currentNavActive();

// Built straight away, then rebuilt once we know who is signed in: an administrator also gets Users, where people are
// let in. (Only administrators can invite.)
function buildPlansNav(me) {
  const items = [
    { href: "/", icon: "list", label: "Plans", active: active === "plans" },
    { href: "/settings.html", icon: "settings", label: "Settings", active: active === "settings" },
  ];
  if (me && me.is_admin) items.push({ href: "/users.html", icon: "users", label: "Users", active: active === "users" });
  items.push({ icon: "refresh", label: "Refresh", onclick: () => location.reload() });
  Global.buildNav(items);
}

buildPlansNav(null);
Global.currentUser().then((me) => {
  if (me) buildPlansNav(me);
});

// The signed-in person's email and a Log out link in the page header (this app signs in through the shared
// front door; /api/me says where Log out goes).
Global.mountUserBadge();
