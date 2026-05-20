"""Tests for admin blueprint routes."""

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import AdminUser, Advertiser, Campaign, PronunciationEntry
from app.models.admin_user import PASSWORD_HASH_METHOD


class TestAuth:
    def test_login_page_renders(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data

    def test_unauthenticated_redirect(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_login_success(self, client, app):
        resp = client.post(
            "/admin/login",
            data={"email": "admin", "password": "changeme"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_database_user_login_success(self, client):
        user = AdminUser(
            email="person@example.com",
            password_hash=generate_password_hash(
                "supersecure123",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=True,
            must_change_password=False,
        )
        db.session.add(user)
        db.session.commit()

        resp = client.post(
            "/admin/login",
            data={"email": "PERSON@example.com", "password": "supersecure123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_login_bad_password(self, client):
        resp = client.post(
            "/admin/login",
            data={"email": "admin", "password": "wrong"},
            follow_redirects=True,
        )
        assert b"Invalid credentials" in resp.data

    def test_inactive_user_cannot_login(self, client):
        user = AdminUser(
            email="inactive@example.com",
            password_hash=generate_password_hash(
                "supersecure123",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=False,
            must_change_password=False,
        )
        db.session.add(user)
        db.session.commit()

        resp = client.post(
            "/admin/login",
            data={"email": "inactive@example.com", "password": "supersecure123"},
            follow_redirects=True,
        )
        assert b"Invalid credentials" in resp.data

    def test_must_change_password_redirects_after_login(self, client):
        user = AdminUser(
            email="forced@example.com",
            password_hash=generate_password_hash(
                "supersecure123",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=True,
            must_change_password=True,
        )
        db.session.add(user)
        db.session.commit()

        resp = client.post(
            "/admin/login",
            data={"email": "forced@example.com", "password": "supersecure123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/admin/account/password" in resp.headers["Location"]


class TestDashboard:
    def test_dashboard_renders(self, authenticated_client):
        resp = authenticated_client.get("/admin/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_must_change_password_blocks_dashboard(self, client):
        user = AdminUser(
            email="forced@example.com",
            password_hash=generate_password_hash(
                "supersecure123",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=True,
            must_change_password=True,
        )
        db.session.add(user)
        db.session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = f"user:{user.id}"
            sess["_fresh"] = True

        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/account/password" in resp.headers["Location"]


class TestAdvertiserCRUD:
    def test_list_empty(self, authenticated_client):
        resp = authenticated_client.get("/admin/advertisers")
        assert resp.status_code == 200
        assert b"Advertisers" in resp.data

    def test_create_advertiser(self, authenticated_client):
        resp = authenticated_client.post(
            "/admin/advertisers/new",
            data={
                "name": "MRG Live",
                "description": "Concert promoter in Western Canada",
                "tagline": "Positive shareable experiences",
                "website": "mrglive.com",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"MRG Live" in resp.data

        adv = Advertiser.query.filter_by(name="MRG Live").first()
        assert adv is not None
        assert adv.description == "Concert promoter in Western Canada"
        assert adv.website == "mrglive.com"

    def test_edit_advertiser(self, authenticated_client):
        adv = Advertiser(name="Old Name", tagline="Old tagline")
        db.session.add(adv)
        db.session.commit()

        resp = authenticated_client.post(
            f"/admin/advertisers/{adv.id}/edit",
            data={
                "name": "New Name",
                "description": "Updated description",
                "tagline": "New tagline",
                "website": "newsite.com",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        updated = Advertiser.query.get(adv.id)
        assert updated.name == "New Name"
        assert updated.description == "Updated description"


class TestCampaignCRUD:
    def _create_advertiser(self):
        adv = Advertiser(name="Test Advertiser")
        db.session.add(adv)
        db.session.commit()
        return adv

    def test_create_campaign(self, authenticated_client):
        adv = self._create_advertiser()

        resp = authenticated_client.post(
            "/admin/campaigns/new",
            data={
                "name": "Vancouver Concerts",
                "advertiser_id": adv.id,
                "is_active": "y",
                "feed_type": "concerts",
                "feed_url": "https://gateway.admitone.com/embed/live-events?city=Vancouver",
                "target_city": "Vancouver, BC",
                "cta": "Get tickets at mrglive.com",
                "seasonal_hook": "Summer shows are here",
                "voice_preset": "Tyler Cruz",
                "intro_seconds": 3.0,
                "outro_seconds": 2.0,
                "duck_volume": 0.2,
                "duck_fade": 0.5,
                "target_seconds": 30,
                "target_words": 75,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        c = Campaign.query.filter_by(name="Vancouver Concerts").first()
        assert c is not None
        assert c.feed_type == "concerts"
        assert c.cta == "Get tickets at mrglive.com"
        assert c.seasonal_hook == "Summer shows are here"
        assert c.voice_preset == "Tyler Cruz"
        assert c.intro_seconds == 3.0

    def test_create_campaign_custom_feed_type(self, authenticated_client):
        """Feed type accepts arbitrary values, not just presets."""
        adv = self._create_advertiser()

        resp = authenticated_client.post(
            "/admin/campaigns/new",
            data={
                "name": "Real Estate Feed",
                "advertiser_id": adv.id,
                "feed_type": "real_estate",
                "intro_seconds": 2.0,
                "outro_seconds": 2.0,
                "duck_volume": 0.2,
                "duck_fade": 0.5,
                "target_seconds": 30,
                "target_words": 75,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        c = Campaign.query.filter_by(name="Real Estate Feed").first()
        assert c is not None
        assert c.feed_type == "real_estate"

    def test_pronunciation_entries_saved(self, authenticated_client):
        adv = self._create_advertiser()

        resp = authenticated_client.post(
            "/admin/campaigns/new",
            data={
                "name": "Pron Test",
                "advertiser_id": adv.id,
                "feed_type": "concerts",
                "intro_seconds": 2.0,
                "outro_seconds": 2.0,
                "duck_volume": 0.2,
                "duck_fade": 0.5,
                "target_seconds": 30,
                "target_words": 75,
                "pron_written_0": "MRG",
                "pron_spoken_0": "M-R-G",
                "pron_written_1": "mrglive.com",
                "pron_spoken_1": "M-R-G Live dot com",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        c = Campaign.query.filter_by(name="Pron Test").first()
        assert len(c.pronunciation_entries) == 2
        assert c.pronunciation_entries[0].written_form == "MRG"
        assert c.pronunciation_entries[1].spoken_form == "M-R-G Live dot com"

    def test_campaign_detail_page(self, authenticated_client):
        adv = self._create_advertiser()
        c = Campaign(name="Detail Test", advertiser_id=adv.id, feed_type="weather")
        db.session.add(c)
        db.session.commit()

        resp = authenticated_client.get(f"/admin/campaigns/{c.id}")
        assert resp.status_code == 200
        assert b"Detail Test" in resp.data


class TestAdminUsers:
    def test_user_list_excludes_bootstrap_identity(self, authenticated_client):
        resp = authenticated_client.get("/admin/users")
        assert resp.status_code == 200
        assert b"admin@example.com" in resp.data
        assert b"Bootstrap Admin" not in resp.data

    def test_create_user(self, authenticated_client):
        resp = authenticated_client.post(
            "/admin/users/new",
            data={
                "email": "newuser@example.com",
                "full_name": "New User",
                "temporary_password": "temp-password1",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        user = AdminUser.query.filter_by(email="newuser@example.com").first()
        assert user is not None
        assert user.must_change_password is True
        assert check_password_hash(user.password_hash, "temp-password1")

    def test_duplicate_user_email_rejected(self, authenticated_client):
        db.session.add(
            AdminUser(
                email="duplicate@example.com",
                password_hash=generate_password_hash(
                    "temp-password1",
                    method=PASSWORD_HASH_METHOD,
                ),
                is_active=True,
            )
        )
        db.session.commit()

        resp = authenticated_client.post(
            "/admin/users/new",
            data={
                "email": "duplicate@example.com",
                "full_name": "Duplicate",
                "temporary_password": "temp-password2",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        assert b"already exists" in resp.data

    def test_edit_user(self, authenticated_client):
        user = AdminUser(
            email="editme@example.com",
            full_name="Old Name",
            password_hash=generate_password_hash(
                "temp-password1",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

        resp = authenticated_client.post(
            f"/admin/users/{user.id}/edit",
            data={
                "email": "updated@example.com",
                "full_name": "Updated Name",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        updated = AdminUser.query.get(user.id)
        assert updated.email == "updated@example.com"
        assert updated.full_name == "Updated Name"

    def test_reset_password(self, authenticated_client):
        user = AdminUser(
            email="reset@example.com",
            password_hash=generate_password_hash(
                "old-password1",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=True,
            must_change_password=False,
        )
        db.session.add(user)
        db.session.commit()

        resp = authenticated_client.post(
            f"/admin/users/{user.id}/reset-password",
            data={"temporary_password": "new-password1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        updated = AdminUser.query.get(user.id)
        assert updated.must_change_password is True
        assert check_password_hash(updated.password_hash, "new-password1")

    def test_toggle_active_blocks_last_admin(self, authenticated_client):
        user = AdminUser.query.filter_by(email="admin@example.com").first()
        resp = authenticated_client.post(
            f"/admin/users/{user.id}/toggle-active",
            data={"submit": "1"},
            follow_redirects=True,
        )
        assert b"last active admin user" in resp.data
        assert AdminUser.query.get(user.id).is_active is True

    def test_toggle_active_deactivates_user(self, authenticated_client):
        user = AdminUser(
            email="other@example.com",
            password_hash=generate_password_hash(
                "temp-password1",
                method=PASSWORD_HASH_METHOD,
            ),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

        resp = authenticated_client.post(
            f"/admin/users/{user.id}/toggle-active",
            data={"submit": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert AdminUser.query.get(user.id).is_active is False


class TestOwnPassword:
    def test_change_own_password(self, authenticated_client):
        resp = authenticated_client.post(
            "/admin/account/password",
            data={
                "current_password": "changeme12345",
                "new_password": "my-new-password1",
                "confirm_new_password": "my-new-password1",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        user = AdminUser.query.filter_by(email="admin@example.com").first()
        assert user.must_change_password is False
        assert check_password_hash(user.password_hash, "my-new-password1")

    def test_change_own_password_rejects_wrong_current(self, authenticated_client):
        resp = authenticated_client.post(
            "/admin/account/password",
            data={
                "current_password": "wrong-password",
                "new_password": "my-new-password1",
                "confirm_new_password": "my-new-password1",
            },
            follow_redirects=True,
        )
        assert b"Current password is incorrect." in resp.data
