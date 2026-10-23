"""Structured ICP criteria: what the company looks like, not what it is called.

Keywords say *what a business is called*. A salesperson says "11-50 staff,
over 10Cr turnover, tier-2 cities, owners and directors" - which is the
filter they actually need and the one the model could not express.

Two things are tested here: that the sentence is parsed into the right
criteria, and that a criterion the model cannot honour is still reported
rather than silently dropped.
"""

import pytest

from app.qualifier.nl_icp import parse_icp_text


def test_headcount_range_becomes_a_size_filter():
    draft = parse_icp_text("Real estate agencies in Pune with 11-50 employees")
    assert draft["min_employees"] == 11
    assert draft["max_employees"] == 50


def test_headcount_over_becomes_a_minimum():
    draft = parse_icp_text("dentists in Delhi with 50+ staff")
    assert draft["min_employees"] == 50
    assert "max_employees" not in draft


def test_headcount_under_becomes_a_maximum():
    draft = parse_icp_text("shops under 20 people in tier 2 cities")
    assert draft["max_employees"] == 20


def test_turnover_becomes_a_revenue_band():
    draft = parse_icp_text("real estate agencies in Pune with turnover over 10cr")
    assert draft["revenue_bands"] == ["10-50Cr"]


def test_a_tier_becomes_a_market_tier():
    draft = parse_icp_text("shops in tier 2 cities")
    assert draft["market_tiers"] == ["tier_2"]


def test_a_role_becomes_a_seniority_band():
    draft = parse_icp_text("founder led startups in Bangalore")
    assert "owner" in draft["seniorities"]


def test_decision_makers_only_is_recognised():
    draft = parse_icp_text("decision makers only in Maharashtra")
    assert draft["decision_makers_only"] is True


def test_a_supported_term_is_not_reported_as_unsupported():
    """The warning list is a promise: it must only contain what was dropped."""
    draft = parse_icp_text("real estate agencies in Pune with 11-50 employees")
    assert not any("employee" in w for w in draft["unsupported_terms"])
    assert not draft["warnings"]


def test_an_unsupported_term_is_still_reported():
    """GSTIN is not expressible, so it must be said out loud."""
    draft = parse_icp_text("gstin registered businesses in Chennai")
    assert any("gstin" in w for w in draft["unsupported_terms"])
    assert draft["warnings"], "a dropped constraint must be reported"


def test_a_bare_revenue_with_no_figure_is_still_reported():
    """"revenue" alone carries no number, so nothing was set - saying so
    is the honest answer."""
    draft = parse_icp_text("high revenue businesses in Pune")
    assert "revenue_bands" not in draft
    assert any("revenue" in w for w in draft["unsupported_terms"])


def test_a_plain_sentence_has_no_criteria():
    draft = parse_icp_text("real estate agents in Pune")
    assert "min_employees" not in draft
    assert "max_employees" not in draft
    assert "revenue_bands" not in draft
    assert "seniorities" not in draft
    assert "market_tiers" not in draft
    assert draft["niche"].lower().startswith("real estate")


@pytest.mark.asyncio
async def test_the_people_query_honours_the_structured_criteria():
    """The criteria have to narrow the result set, not just be stored."""
    from app.api.people import query_people
    from app.database import async_session_maker
    from app.models.business import Business
    from app.models.contact import Contact
    from app.models.icp_profile import ICPProfile

    async with async_session_maker() as db:
        big = Business(
            name="Big Realty", industry="Real estate", city="Delhi",
            state="Delhi", employee_count=120, size_bucket="51-200",
            revenue=12_00_00_000.0, revenue_band="10-50Cr",
        )
        small = Business(
            name="Small Realty", industry="Real estate", city="Delhi",
            state="Delhi", employee_count=8, size_bucket="2-10",
        )
        db.add_all([big, small])
        await db.flush()
        db.add_all([
            Contact(
                business_id=big.id, first_name="Rakesh", last_name="Gupta",
                title="Proprietor", email="rakesh@big.example.in",
                person_identified=True, seniority="owner",
                is_decision_maker=True,
            ),
            Contact(
                business_id=small.id, first_name="Asha", last_name="Rao",
                title="Owner", email="asha@small.example.in",
                person_identified=True, seniority="owner",
                is_decision_maker=True,
            ),
        ])
        icp = ICPProfile(
            name="Mid-size Delhi agencies", niche="real estate", area="Delhi",
            keywords=["realty"], min_employees=11, max_employees=200,
        )
        db.add(icp)
        await db.commit()
        icp_id = icp.id

        result = await query_people(db, limit=10, icp_profile_id=icp_id)
        assert result["total"] == 1, "only the 120-staff business qualifies"
        assert result["people"][0]["business_name"] == "Big Realty"

        # And the count agrees with the rows.
        assert result["pages"] == 1


@pytest.mark.asyncio
async def test_search_and_company_sort_do_not_join_the_business_twice():
    """Joining `businesses` twice makes every `businesses.*` column ambiguous.

    The error only appears when a search is combined with a company sort,
    so it has to be pinned by a test.
    """
    from app.api.people import query_people
    from app.database import async_session_maker
    from app.models.business import Business
    from app.models.contact import Contact

    async with async_session_maker() as db:
        biz = Business(name="Realty Partners", industry="Real estate")
        db.add(biz)
        await db.flush()
        db.add(Contact(
            business_id=biz.id, first_name="Rakesh", title="Proprietor",
            person_identified=True, seniority="owner",
        ))
        await db.commit()

        for sort in ("company", "score", "employees", "created"):
            result = await query_people(db, limit=5, search="real", sort=sort)
            assert result["total"] >= 0
        result = await query_people(db, limit=5, sort="company")
        assert result["total"] == 1
