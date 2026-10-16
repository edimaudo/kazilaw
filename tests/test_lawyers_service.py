from __future__ import annotations

from pathlib import Path

import lawyers_data
import lawyers_service as service


def test_data_configuration_does_not_store_individual_lawyers():
    assert not hasattr(lawyers_data, "LAWYERS_BY_PROVINCE")
    for source in lawyers_data.PROFILE_SOURCES.values():
        assert "listing_url" in source
        assert source["listing_url"].startswith("https://")
        assert "name" not in source  # no lawyer-name records in the source registry


def test_index_candidates_are_limited_to_configured_same_host_profile_paths():
    listing_url = "https://firm.example/people/"
    source = {"profile_prefixes": ("/people/",), "max_candidates": 20}
    html = """
    <main>
      <a href="/people/alex-example/">Alex Example</a>
      <a href="https://other.example/people/fake-person/">External Person</a>
      <a href="/services/employment-law/">Employment Law</a>
      <a href="/people/alex-example/?utm_source=directory">Alex Example</a>
    </main>
    """
    candidates = service._extract_index_candidates(html, listing_url, source)
    assert [item["profile_url"] for item in candidates] == [
        "https://firm.example/people/alex-example/"
    ]


def test_profile_parser_does_not_use_sitewide_footer_to_match_practice_or_province():
    html = """
    <html><body>
      <nav>Employment law team — Toronto, Ontario</nav>
      <main><article>
        <h1>Alex Example</h1>
        <p>Corporate finance and commercial transactions.</p>
      </article></main>
      <footer>Toronto, Ontario. Labour &amp; employment practice.</footer>
    </body></html>
    """
    name, text, city = service._page_text_and_name(
        html, "Alex Example", "https://firm.example/people/alex-example/", "ON"
    )
    assert name == "Alex Example"
    assert "corporate finance" in text.lower()
    assert "labour & employment" not in text.lower()
    assert city == ""
    assert not service._has_workplace_practice(text)
    assert not service._region_present(text, "ON", city or "")


def test_live_retrieval_discovers_name_from_profile_page(monkeypatch):
    source_id = "test_mock_firm"
    listing_url = "https://firm.example/people/"
    profile_url = "https://firm.example/people/alex-example/"
    source = {
        "name_en": "Example Firm – People",
        "name_fr": "Example Firm – équipe",
        "firm_en": "Example Firm LLP",
        "listing_url": listing_url,
        "profile_prefixes": ("/people/",),
        "strategy": "practice_and_region",
        "jurisdictions": ("ON",),
        "max_index_pages": 1,
        "max_candidates": 10,
    }
    index_html = f'<main><a href="{profile_url}">View profile</a></main>'
    profile_html = """
    <html><body>
      <nav>Services and global locations</nav>
      <main><article>
        <h1>Alex Example</h1>
        <p>Practice areas: Labour &amp; Employment Law, Workplace investigations.</p>
        <p>Called to the Ontario Bar. Toronto office.</p>
      </article></main>
      <footer>Other offices in Calgary and Vancouver.</footer>
    </body></html>
    """

    def fake_fetch(url):
        return {listing_url: index_html, profile_url: profile_html}.get(url)

    monkeypatch.setitem(lawyers_data.PROFILE_SOURCES, source_id, source)
    monkeypatch.setitem(lawyers_data.JURISDICTIONS["ON"], "source_ids", (source_id,))
    monkeypatch.setattr(service, "_fetch_html", fake_fetch)
    service._reset_caches_for_tests()

    result = service.get_live_profiles("ON", 15)
    assert len(result["lawyers"]) == 1
    lawyer = result["lawyers"][0]
    assert lawyer["name"] == "Alex Example"
    assert lawyer["firm"] == "Example Firm LLP"
    assert lawyer["profile_url"] == profile_url
    assert lawyer["source_id"] == source_id
    assert lawyer["status"] == "unverified"
    assert result["sources_checked"][0]["result"] == "profiles_found"

    service._reset_caches_for_tests()


def test_robots_cache_checks_each_requested_path(monkeypatch):
    class FakeRobotParser:
        def __init__(self, url=None):
            self.url = url
        def parse(self, _lines):
            pass
        def can_fetch(self, _user_agent, url):
            return "/private/" not in url

    class FakeResponse:
        status = 200
        def read(self, _limit):
            return b"User-agent: *\\nAllow: /\\nDisallow: /private/"
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(service.urllib.robotparser, "RobotFileParser", FakeRobotParser)
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    service._reset_caches_for_tests()
    _parser, allowed_public = service._robots_policy("https://firm.example/people/alex/")
    _parser, allowed_private = service._robots_policy("https://firm.example/private/alex/")
    assert allowed_public is True
    assert allowed_private is False
    service._reset_caches_for_tests()
