"""Tests for the pipeline runner's manual override behavior."""

from app.models import Advertiser, Campaign
from app.pipeline import runner as runner_module
from app.pipeline.runner import run_pipeline


def _make_campaign(db, **overrides):
    adv = Advertiser(name="Test Advertiser")
    db.session.add(adv)
    db.session.commit()

    defaults = {
        "name": "Test Campaign",
        "advertiser_id": adv.id,
        # world_cup with no feed_url raises FeedFetchError immediately with no
        # fallback_script configured — if the override doesn't short-circuit
        # the fetch, the run fails instead of completing.
        "feed_type": "world_cup",
    }
    defaults.update(overrides)
    c = Campaign(**defaults)
    db.session.add(c)
    db.session.commit()
    return c


def _stub_audio_pipeline(monkeypatch):
    monkeypatch.setattr(runner_module, "generate_voiceover", lambda script, voice_id, is_custom=False: b"fake-vo")
    monkeypatch.setattr(runner_module, "mix_audio", lambda **kwargs: (b"fake-final", None))
    monkeypatch.setattr(runner_module, "_get_music_bed", lambda campaign: b"fake-music")


class TestManualOverride:
    def test_override_skips_feed_and_uses_staged_script(self, client, db, monkeypatch):
        _stub_audio_pipeline(monkeypatch)
        campaign = _make_campaign(
            db,
            manual_override_script="Huge win last night for the home side.",
            use_manual_override=True,
        )

        ad_run = run_pipeline(campaign.id, triggered_by="cron")

        assert ad_run.status == "complete"
        assert ad_run.script_text == "Huge win last night for the home side."
        assert ad_run.script_source == "manual_override"

    def test_override_is_one_shot(self, client, db, monkeypatch):
        _stub_audio_pipeline(monkeypatch)
        campaign = _make_campaign(
            db,
            manual_override_script="Huge win last night for the home side.",
            use_manual_override=True,
        )

        run_pipeline(campaign.id, triggered_by="cron")
        db.session.refresh(campaign)

        assert campaign.use_manual_override is False
        # Staged text is left in place for reference — only the flag clears.
        assert campaign.manual_override_script == "Huge win last night for the home side."

    def test_failed_run_leaves_override_armed(self, client, db, monkeypatch):
        """A run that fails downstream of the script stage must not consume
        the override — the retry should still use the staged script."""
        _stub_audio_pipeline(monkeypatch)
        monkeypatch.setattr(
            runner_module, "_get_music_bed",
            lambda campaign: (_ for _ in ()).throw(
                runner_module.PipelineError("No music bed configured")
            ),
        )
        campaign = _make_campaign(
            db,
            manual_override_script="Huge win last night for the home side.",
            use_manual_override=True,
        )

        ad_run = run_pipeline(campaign.id, triggered_by="cron")
        db.session.refresh(campaign)

        assert ad_run.status == "failed"
        assert ad_run.script_source == "manual_override"
        assert campaign.use_manual_override is True

    def test_without_override_feed_failure_is_not_swallowed(self, client, db, monkeypatch):
        """Sanity check: without an armed override, a broken feed still fails the run."""
        _stub_audio_pipeline(monkeypatch)
        campaign = _make_campaign(db, use_manual_override=False)

        ad_run = run_pipeline(campaign.id, triggered_by="cron")

        assert ad_run.status == "failed"

    def test_override_ignored_when_script_blank(self, client, db, monkeypatch):
        """An armed flag with no script text falls through to normal feed fetch (and fails, same as above)."""
        _stub_audio_pipeline(monkeypatch)
        campaign = _make_campaign(db, use_manual_override=True, manual_override_script="   ")

        ad_run = run_pipeline(campaign.id, triggered_by="cron")

        assert ad_run.status == "failed"
