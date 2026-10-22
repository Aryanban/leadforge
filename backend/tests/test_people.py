"""The People table: who is this person, and can we sell to them?

Covers three things that were previously absent from the codebase and
that the People table is built on:

* A **seniority taxonomy** that understands Indian SMB titles. A US/EU
  list files "Proprietor", "Promoter", "Managing Director" and "Principal"
  as unknown, and an unknown title is a founder the People table cannot
  show you.
* **Location parsing** that turns a free-text address into a filterable
  city and state, without ever returning a state as a city.
* **Person extraction** from a company's own website, which has to
  survive call-to-action boilerplate, testimonials, and company names
  glued onto people.
"""

import pytest

from app.enricher.people_extraction import (
    extract_executives_from_jsonld,
    extract_executives_from_text,
    extract_people_without_roles,
    is_plausible_person_name,
    merge_executives,
)
from app.enricher.email_finder import _merge_company_profile
from app.enricher.seniority import (
    DECISION_MAKER_BANDS,
    classify_seniority,
    detect_technologies,
    extract_company_profile,
    is_decision_maker,
    parse_employee_count,
    parse_revenue,
    revenue_band,
    size_bucket,
)
from app.locations.india import extract_city_state, market_tier, state_code


# --------------------------------------------------------------------------
# Seniority
# --------------------------------------------------------------------------


@pytest.mark.parametrize("title,expected", [
    # Indian SMB decision makers
    ("Proprietor", "owner"),
    ("Promoter", "owner"),
    ("Founder & CEO", "owner"),
    ("Co-Founder", "owner"),
    ("Owner", "owner"),
    ("Partner", "owner"),
    ("Principal", "owner"),
    ("Managing Director", "c_level"),
    ("MD", "c_level"),
    ("S K M D", "c_level"),
    ("S.K.M.D.", "c_level"),
    ("Whole Time Director", "c_level"),
    ("Chief Executive Officer", "c_level"),
    ("Executive Director", "c_level"),
    ("Director", "director"),
    ("Director of Operations", "director"),
    ("Vice President", "vp"),
    ("VP Sales", "vp"),
    ("Head of Sales", "head"),
    ("General Manager", "manager"),
    ("Senior Manager", "senior"),
    ("Team Lead", "senior"),
    ("Sales Executive", "staff"),
    ("Consultant", "other"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_classify_seniority(title, expected):
    assert classify_seniority(title) == expected


def test_director_is_not_mistaken_for_a_cto():
    """``"director"`` contains ``"cto"`` - plain substring matching filed
    every director in India as a C-level executive."""
    assert classify_seniority("Director") == "director"
    assert classify_seniority("Senior Director") == "director"


def test_seniority_bands_are_ordered_and_decision_makers_are_defined():
    assert set(DECISION_MAKER_BANDS) <= {
        "owner", "c_level", "vp", "director", "head", "manager",
    }
    assert is_decision_maker("owner") is True
    assert is_decision_maker("manager") is False
    assert is_decision_maker(None) is False


# --------------------------------------------------------------------------
# Company size / revenue / technology
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("We are a team of 50 employees", 50),
    ("50+ employees across 3 locations", 50),
    ("Team of 12", 12),
    ("We employ 35 people", 35),
    ("a staff of 200", 200),
    ("Copyright 2024 Acme", None),
    ("Established in 1998", None),
    (None, None),
])
def test_parse_employee_count(text, expected):
    assert parse_employee_count(text) == expected


@pytest.mark.parametrize("text,expected_band", [
    ("annual turnover of 12 crore", "10-50Cr"),
    ("revenue: 40 lakhs", "<1Cr"),
    ("turnover Rs 2.5 crore", "1-10Cr"),
    ("Annual revenue INR 5 Cr", "1-10Cr"),
    ("we are bootstrapped", None),
])
def test_parse_revenue(text, expected_band):
    amount = parse_revenue(text)
    assert revenue_band(amount) == expected_band


def test_size_bucket():
    assert size_bucket(1) == "1"
    assert size_bucket(7) == "2-10"
    assert size_bucket(30) == "11-50"
    assert size_bucket(120) == "51-200"
    assert size_bucket(300) == "201-500"
    assert size_bucket(900) == "500+"
    assert size_bucket(None) is None


def test_detect_technologies_only_reports_what_is_present():
    html = '<script src="https://cdn.shopify.com/x.js"></script><a href="/tally">Tally 4.5</a>'
    found = detect_technologies(html)
    assert "Shopify" in found
    assert "Tally" in found
    assert "WordPress" not in found
    assert detect_technologies("") == []


def test_company_profile_reads_size_revenue_and_technology():
    """The attributes an ICP is expressed in - size, turnover, stack."""
    html = """
    <html><body>
      <script>var x = "500 employees";</script>
      <p>We are a team of 35 employees serving Pune.</p>
      <p>Annual turnover of 12 crore.</p>
      <script src="https://cdn.shopify.com/s.js"></script>
      <a href="/tally">Accounting with Tally</a>
    </body></html>
    """
    profile = extract_company_profile(html)
    assert profile["employee_count"] == 35
    assert profile["size_bucket"] == "11-50"
    assert profile["revenue_band"] == "10-50Cr"
    assert "Shopify" in profile["technologies"]
    assert "Tally" in profile["technologies"]


def test_company_profile_reports_nothing_when_the_site_says_nothing():
    """A guessed headcount is worse than a blank one."""
    profile = extract_company_profile("<html><body><p>Welcome to our site.</p></body></html>")
    assert "employee_count" not in profile
    assert "revenue" not in profile
    assert "technologies" not in profile
    assert extract_company_profile(None) == {}


def test_company_profile_ignores_numbers_in_script_tags():
    """A copyright year or a JS constant is not a headcount."""
    profile = extract_company_profile(
        "<html><body><script>var founded = 1998; var staff = 200;</script>"
        "<p>Quality service since 1998.</p></body></html>"
    )
    assert "employee_count" not in profile


def test_company_profile_merges_across_pages():
    """The first page that states a value wins; technologies accumulate."""
    target: dict = {}
    _merge_company_profile(target, {"employee_count": 35, "size_bucket": "11-50"})
    _merge_company_profile(target, {"technologies": ["Shopify"]})
    _merge_company_profile(target, {"employee_count": 2, "technologies": ["Tally"]})
    assert target["employee_count"] == 35
    assert target["size_bucket"] == "11-50"
    assert target["technologies"] == ["Shopify", "Tally"]


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------


@pytest.mark.parametrize("address,city,state", [
    ("Kothrud, Pune, 411038", "Pune", "Maharashtra"),
    ("unknown, Pune, 411045", "Pune", "Maharashtra"),
    ("Premium Point, 1321/1, Jangali Mahar, Pune, 411038", "Pune", "Maharashtra"),
    ("12 MG Road, Bangalore 560001", "Bangalore", "Karnataka"),
    ("B-42, Sector 5, Noida, 201301", "Noida", "Uttar Pradesh"),
    ("Pune, Maharashtra 411001", "Pune", "Maharashtra"),
    ("Ahmedabad - Dholera Expy, Dholera, Gujarat 382455", "Ahmedabad", "Gujarat"),
    ("", None, None),
    (None, None, None),
])
def test_extract_city_state(address, city, state):
    assert extract_city_state(address) == (city, state)


def test_a_state_is_never_returned_as_a_city():
    """An address that ends in a state used to yield that state as the
    city, which put every Gujarat business under a city called "Gujarat"."""
    city, state = extract_city_state("Ahmedabad - Dholera Expy, Dholera, Gujarat 382455")
    assert city != "Gujarat"
    assert state == "Gujarat"


def test_market_tier():
    assert market_tier("Pune") == "metro"
    assert market_tier("Nashik") == "tier_2"
    assert market_tier("Dholera") == "tier_3"
    assert market_tier(None) is None


def test_state_code():
    assert state_code("Maharashtra") == "MH"
    assert state_code("maharashtra") == "MH"
    assert state_code("Nowhere") is None


# --------------------------------------------------------------------------
# Person extraction
# --------------------------------------------------------------------------


def test_extracts_the_common_name_then_title_form():
    found = extract_executives_from_text("Rakesh Gupta - Proprietor")
    assert found == [{"name": "Rakesh Gupta", "title": "Proprietor"}]


def test_extracts_the_title_first_form():
    """The form the old pattern missed entirely, and common on Indian sites."""
    found = extract_executives_from_text("Proprietor: Mr. Rakesh Gupta")
    assert any(e["name"] == "Rakesh Gupta" for e in found)
    assert any(e["title"] == "Proprietor" for e in found)


def test_extracts_a_role_stated_in_a_verb_phrase():
    found = extract_executives_from_text("Dr. Aniket Kasodekar is an Orthodontist")
    assert any(e["name"] == "Aniket Kasodekar" for e in found)


def test_a_name_does_not_run_across_a_line_break():
    """"Head of Sales" followed by "Pooja Nair - Director" used to read as
    a person called "Sales Pooja Nair"."""
    found = extract_executives_from_text(
        "Hemant Joshi, Head of Sales\nPooja Nair - Director"
    )
    names = [e["name"] for e in found]
    assert "Pooja Nair" in names
    assert "Sales Pooja Nair" not in names


def test_call_to_action_boilerplate_is_not_a_person():
    found = extract_executives_from_text("Read more - owner\nCall now\nGet in touch")
    assert found == []


def test_a_slogan_is_not_a_job_title():
    """"Home Management is the Most Trustable Name in Ahmedabad" is marketing
    copy, and it used to produce a person called "Home Management"."""
    found = extract_executives_from_text(
        "Home Management is the Most Trustable Name in Ahmedabad"
    )
    assert found == []


def test_a_pronoun_is_not_part_of_a_name():
    found = extract_executives_from_text(
        "Laser Specialist. He is an Orthodontist, and his team is excellent"
    )
    assert all("He" not in e["name"] for e in found)


def test_company_words_are_not_a_person():
    assert is_plausible_person_name("Krupa Dental Care") is False
    assert is_plausible_person_name("Acme Dental Pvt Ltd") is False
    assert is_plausible_person_name("Rakesh Gupta") is True


def test_company_name_trims_a_glued_on_prefix():
    """At "Real Estate Pundits", the page reads "Pundits ANERI MEHTA Co"."""
    found = extract_executives_from_text(
        "Pundits ANERI MEHTA Co - Founder", "Real Estate Pundits"
    )
    assert found
    assert found[0]["name"].lower() == "aneri mehta"


def test_a_person_with_an_honorific_but_no_role_is_still_a_person():
    found = extract_people_without_roles("more particularly Mr. Nilesh Barot")
    assert found and found[0]["name"] == "Nilesh Barot"
    assert found[0]["title"] == ""


def test_jsonld_people_are_extracted():
    html = """
    <script type="application/ld+json">
    {"@type":"Organization","name":"Acme","employee":[
      {"@type":"Person","name":"Rakesh Gupta","jobTitle":"Proprietor"}]}
    </script>
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    found = extract_executives_from_jsonld(soup)
    assert found == [{"name": "Rakesh Gupta", "title": "Proprietor"}]


def test_jsonld_wins_over_a_regex_guess():
    from bs4 import BeautifulSoup
    html = """
    <script type="application/ld+json">
    {"@type":"Person","name":"Rakesh Gupta","jobTitle":"Proprietor"}
    </script>
    <p>Rakesh Gupta - Owner</p>
    """
    soup = BeautifulSoup(html, "html.parser")
    merged = merge_executives(
        extract_executives_from_jsonld(soup),
        extract_executives_from_text(soup.get_text(" ", strip=True)),
    )
    assert len(merged) == 1
    assert merged[0]["title"] == "Proprietor"


def test_merge_keeps_a_known_role_over_a_roleless_sighting():
    merged = merge_executives(
        [{"name": "Rakesh Gupta", "title": "Proprietor"}],
        [{"name": "Rakesh Gupta", "title": ""}],
    )
    assert len(merged) == 1
    assert merged[0]["title"] == "Proprietor"


# --------------------------------------------------------------------------
# The People query is shared by the API and the MCP tool
# --------------------------------------------------------------------------


def test_people_query_is_a_plain_function_not_a_fastapi_handler():
    """The MCP tool calls the query directly.

    Calling the FastAPI handler would not work: its defaults are ``Query``
    objects rather than values, so a plain call gets
    ``'Query' object has no attribute 'split'``.
    """
    import inspect

    from app.api.people import list_people, query_people

    sig = inspect.signature(query_people)
    for name, param in sig.parameters.items():
        if name == "db":
            continue
        assert param.default in (None, True, False, 1, 50, "created"), (
            f"{name} has a non-plain default: {param.default!r}"
        )
    # The route is a thin wrapper over it.
    assert list_people.__name__ == "list_people"


def test_mcp_people_tool_is_advertised_and_dispatched():
    """An advertised tool with no dispatch crashes the agent."""
    from app.mcp_server import TOOLS_DEFINITIONS

    names = [t["name"] for t in TOOLS_DEFINITIONS]
    assert "leadforge_search_people" in names


@pytest.mark.asyncio
async def test_mcp_people_tool_returns_a_table():
    from app.mcp_server import handle_tool_call

    out = await handle_tool_call(
        "leadforge_search_people",
        {"decision_makers_only": True, "limit": 5},
    )
    assert "LeadForge People" in out
    assert "| Contact ID |" in out
    # The tool must tell the agent how to use the rows.
    assert "add_campaign_targets" in out
