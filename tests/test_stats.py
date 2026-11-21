"""The numbers the dashboard's stats pages read: administrators only, counts and dates only, everyone's accounts."""
from app import models
from app.database import SessionLocal
from shared_python import owned


def test_only_an_administrator_can_read_the_stats(client_as, make_user, monkeypatch):
    make_user("bob@example.com")
    monkeypatch.setattr("app.config.ADMIN_EMAILS", {"dev@localhost.test"})
    assert client_as("bob@example.com").get("/api/admin/stats").status_code == 403
    assert client_as("dev@localhost.test").get("/api/admin/stats").status_code == 200


def test_the_stats_count_each_persons_plans_without_showing_any_of_them(client_as, make_user, as_user, monkeypatch):
    monkeypatch.setattr("app.config.ADMIN_EMAILS", {"dev@localhost.test"})
    bob = make_user("bob@example.com")
    with as_user(bob) as db:
        db.add_all([models.Plan(name="SECRET PLAN", description="SECRET NOTE"), models.Plan(name="another", imported=True)])
        db.commit()
    body = client_as("dev@localhost.test").get("/api/admin/stats")
    accounts = {a["email"]: a for a in body.json()["accounts"]}
    assert accounts["bob@example.com"]["counts"]["plans"] == 2 and accounts["bob@example.com"]["counts"]["plans imported in bulk"] == 1
    assert accounts["dev@localhost.test"]["counts"]["plans"] == 0
    assert "SECRET PLAN" not in body.text and "SECRET NOTE" not in body.text


def test_the_gate_notes_when_a_person_was_last_seen(client_as, make_user):
    make_user("bob@example.com")
    assert client_as("bob@example.com").get("/api/me").status_code == 200
    with owned.unscoped(), SessionLocal() as db:
        user = db.query(models.User).filter(models.User.email == "bob@example.com").one()
        assert user.active_days == 1 and user.last_seen_at is not None
