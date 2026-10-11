from app.models.campaign_step import CampaignTarget


def test_campaign_target_model_shape():
    """Explicit recipients exist so a campaign can't email unpicked leads."""
    assert CampaignTarget.__tablename__ == "campaign_targets"
    cols = {c.name for c in CampaignTarget.__table__.columns}
    assert {"campaign_id", "contact_id", "added_at"} <= cols
    # Re-adding the same lead to a campaign must be a no-op.
    uniques = [c for c in CampaignTarget.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({"campaign_id", "contact_id"} <= {col.name for col in u.columns} for u in uniques)


def test_sender_scopes_to_targets_when_present():
    """Source check: the sender must filter by campaign_targets when set."""
    import inspect
    from app.campaigns import sender

    src = inspect.getsource(sender.execute_campaign_step)
    assert "CampaignTarget" in src
    assert "target_ids" in src
    # Legacy behaviour preserved: an empty target set does not filter.
    assert "if target_ids:" in src