"""Tests for database models."""

from app.models import Advertiser, Campaign, PronunciationEntry, AdRun


class TestAdvertiser:
    def test_create_advertiser(self, db):
        adv = Advertiser(name="Test Co", tagline="We test things")
        db.session.add(adv)
        db.session.commit()

        assert adv.id is not None
        assert adv.name == "Test Co"
        assert adv.is_active is True

    def test_advertiser_description_and_website(self, db):
        adv = Advertiser(
            name="MRG Live",
            description="Concert promoter operating venues across Western Canada",
            tagline="Positive shareable experiences",
            website="mrglive.com",
        )
        db.session.add(adv)
        db.session.commit()

        fetched = Advertiser.query.get(adv.id)
        assert fetched.description == "Concert promoter operating venues across Western Canada"
        assert fetched.website == "mrglive.com"

    def test_advertiser_has_no_cta(self, db):
        """CTA lives on Campaign, not Advertiser."""
        adv = Advertiser(name="Test Co")
        assert not hasattr(adv, "cta")

    def test_advertiser_campaign_relationship(self, db):
        adv = Advertiser(name="Test Co")
        db.session.add(adv)
        db.session.commit()

        c = Campaign(
            name="Test Campaign",
            advertiser_id=adv.id,
            feed_type="weather",
        )
        db.session.add(c)
        db.session.commit()

        assert adv.campaigns.count() == 1
        assert c.advertiser.name == "Test Co"


class TestCampaign:
    def _make_campaign(self, db, **overrides):
        adv = Advertiser(name="Test Advertiser")
        db.session.add(adv)
        db.session.commit()

        defaults = {
            "name": "Test Campaign",
            "advertiser_id": adv.id,
            "feed_type": "weather",
        }
        defaults.update(overrides)
        c = Campaign(**defaults)
        db.session.add(c)
        db.session.commit()
        return c

    def test_create_campaign(self, db):
        c = self._make_campaign(db)
        assert c.id is not None
        assert c.feed_type == "weather"
        assert c.is_active is True

    def test_cta_on_campaign(self, db):
        c = self._make_campaign(db, cta="Get tickets at mrglive.com")
        assert c.cta == "Get tickets at mrglive.com"

    def test_seasonal_hook_on_campaign(self, db):
        c = self._make_campaign(db, seasonal_hook="Summer concert series")
        assert c.seasonal_hook == "Summer concert series"

    def test_feed_type_is_freetext(self, db):
        """Feed type accepts any string, not just preset values."""
        c = self._make_campaign(db, feed_type="real_estate_listings")
        assert c.feed_type == "real_estate_listings"

    def test_default_mix_settings(self, db):
        c = self._make_campaign(db)
        assert c.intro_seconds == 2.0
        assert c.outro_seconds == 2.0
        assert c.duck_volume == 0.2
        assert c.duck_fade == 0.5

    def test_custom_mix_settings(self, db):
        c = self._make_campaign(
            db,
            intro_seconds=3.0,
            outro_seconds=1.5,
            duck_volume=0.15,
            duck_fade=0.8,
        )
        assert c.intro_seconds == 3.0
        assert c.duck_volume == 0.15

    def test_effective_voice_id_default(self, db):
        """No voice set — falls back to Brian."""
        c = self._make_campaign(db)
        assert c.effective_voice_id == "nPczCjzI2devNBz1zQrb"
        assert c.effective_voice_name == "Brian"

    def test_effective_voice_id_preset(self, db):
        c = self._make_campaign(db, voice_preset="Tyler Cruz")
        assert c.effective_voice_id == "SA7eD52NRr8WAehitVt1"
        assert c.effective_voice_name == "Tyler Cruz"

    def test_effective_voice_id_custom_overrides_preset(self, db):
        """Custom voice ID always wins over preset."""
        c = self._make_campaign(
            db,
            voice_preset="Brian",
            voice_custom_id="custom123abc",
        )
        assert c.effective_voice_id == "custom123abc"
        assert "Custom" in c.effective_voice_name

    def test_prompt_template_nullable(self, db):
        """NULL prompt_template means use the feed type default."""
        c = self._make_campaign(db, prompt_template=None)
        assert c.prompt_template is None

    def test_cron_schedule_nullable(self, db):
        c = self._make_campaign(db, cron_schedule=None)
        assert c.cron_schedule is None

    def test_manual_override_defaults(self, db):
        """Override is off and unset by default — distinct from fallback_script."""
        c = self._make_campaign(db)
        assert c.use_manual_override is False
        assert c.manual_override_script is None

    def test_manual_override_can_be_staged(self, db):
        c = self._make_campaign(
            db,
            manual_override_script="Big win for the home team last night...",
            use_manual_override=True,
        )
        assert c.use_manual_override is True
        assert "home team" in c.manual_override_script


class TestPronunciationEntry:
    def test_create_entries(self, db):
        adv = Advertiser(name="Test Co")
        db.session.add(adv)
        db.session.commit()

        c = Campaign(name="Test", advertiser_id=adv.id, feed_type="concerts")
        db.session.add(c)
        db.session.commit()

        e1 = PronunciationEntry(
            campaign_id=c.id, written_form="MRG", spoken_form="M-R-G"
        )
        e2 = PronunciationEntry(
            campaign_id=c.id,
            written_form="mrglive.com",
            spoken_form="M-R-G Live dot com",
        )
        db.session.add_all([e1, e2])
        db.session.commit()

        assert len(c.pronunciation_entries) == 2
        assert c.pronunciation_entries[0].written_form == "MRG"

    def test_cascade_delete(self, db):
        """Deleting a campaign deletes its pronunciation entries."""
        adv = Advertiser(name="Test Co")
        db.session.add(adv)
        db.session.commit()

        c = Campaign(name="Test", advertiser_id=adv.id, feed_type="concerts")
        db.session.add(c)
        db.session.commit()

        e = PronunciationEntry(
            campaign_id=c.id, written_form="MRG", spoken_form="M-R-G"
        )
        db.session.add(e)
        db.session.commit()

        db.session.delete(c)
        db.session.commit()

        assert PronunciationEntry.query.count() == 0


class TestAdRun:
    def test_create_run(self, db):
        adv = Advertiser(name="Test Co")
        db.session.add(adv)
        db.session.commit()

        c = Campaign(name="Test", advertiser_id=adv.id, feed_type="weather")
        db.session.add(c)
        db.session.commit()

        run = AdRun(campaign_id=c.id, triggered_by="manual")
        db.session.add(run)
        db.session.commit()

        assert run.status == "pending"
        assert run.is_terminal is False
        assert run.status_label == "Pending"

    def test_terminal_states(self, db):
        adv = Advertiser(name="Test Co")
        db.session.add(adv)
        db.session.commit()

        c = Campaign(name="Test", advertiser_id=adv.id, feed_type="weather")
        db.session.add(c)
        db.session.commit()

        run = AdRun(campaign_id=c.id, triggered_by="manual", status="complete")
        db.session.add(run)
        db.session.commit()
        assert run.is_terminal is True

        run.status = "failed"
        assert run.is_terminal is True

        run.status = "generating_script"
        assert run.is_terminal is False

    def test_status_labels(self, db):
        adv = Advertiser(name="Test Co")
        db.session.add(adv)
        db.session.commit()

        c = Campaign(name="Test", advertiser_id=adv.id, feed_type="weather")
        db.session.add(c)
        db.session.commit()

        run = AdRun(campaign_id=c.id, triggered_by="api")
        db.session.add(run)
        db.session.commit()

        run.status = "generating_voiceover"
        assert run.status_label == "Generating voiceover..."

        run.status = "mixing"
        assert run.status_label == "Mixing audio..."
