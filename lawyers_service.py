"""Live retrieval of workplace-law profiles from public law-firm pages.

No lawyer names, cities or individual profile URLs are stored in source code. The
service discovers them from approved firm/practice index pages when the user opens
or changes the legal directory. It never scrapes law-society member directories.

Runtime safeguards:
- obey robots.txt for the firm pages;
- use HTTPS only, a descriptive user agent, timeouts and a response-size limit;
- limit parallel requests and profile counts;
- cache successful results briefly to avoid repeatedly hitting third-party sites;
- show profiles as unverified until users check the regulator themselves.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request
from datetime import datetime, timezone
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from lawyers_data import (
    JURISDICTION_TERMS,
    MAX_LAWYERS_PER_JURISDICTION,
    PROFILE_SOURCES,
    SOURCE_CACHE_SECONDS,
    WORKPLACE_TERMS,
)

logger = logging.getLogger(__name__)
USER_AGENT = "kazilaw-public-lawyer-directory/1.0"
FETCH_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 3_000_000
MAX_PROFILE_FETCHES_PER_SOURCE = 36
MAX_WORKERS = 6

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PAGE_CACHE: dict[str, tuple[float, str]] = {}
_ROBOTS_CACHE: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None, bool]] = {}
_CACHE_LOCK = threading.RLock()
PAGE_CACHE_SECONDS = 900
ROBOTS_CACHE_SECONDS = 86400


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().lower()


def _site_origin(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _robots_policy(url: str) -> tuple[urllib.robotparser.RobotFileParser | None, bool]:
    """Return robots parser and whether access can be checked/allowed.

    A missing robots.txt (HTTP 404) is treated as no published crawl restrictions.
    Other errors fail closed so a temporary/network error does not trigger scraping.
    """
    origin = _site_origin(url)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _ROBOTS_CACHE.get(origin)
        if cached and now - cached[0] < ROBOTS_CACHE_SECONDS:
            parser, policy_available = cached[1], cached[2]
            allowed_for_url = bool(policy_available and parser and parser.can_fetch(USER_AGENT, url))
            return parser, allowed_for_url

    robots_url = urllib.parse.urljoin(origin, "/robots.txt")
    parser = urllib.robotparser.RobotFileParser(robots_url)
    policy_available = False
    try:
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain,*/*;q=0.5"},
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as response:
            if response.status == 200:
                body = response.read(512_000).decode("utf-8", errors="replace")
                parser.parse(body.splitlines())
                policy_available = True
            else:
                policy_available = False
    except urllib.error.HTTPError as exc:
        # Robots not found: no explicit robots policy was published.
        if exc.code == 404:
            parser.parse([])
            policy_available = True
        else:
            policy_available = False
    except Exception as exc:
        logger.debug("Could not read robots policy for %s: %s", origin, exc)
        policy_available = False

    with _CACHE_LOCK:
        _ROBOTS_CACHE[origin] = (now, parser, policy_available)
    allowed_for_url = bool(policy_available and parser and parser.can_fetch(USER_AGENT, url))
    return parser, allowed_for_url


def _fetch_html(url: str) -> str | None:
    """Fetch a public firm page if robots permits it; cache successful responses."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None

    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _PAGE_CACHE.get(url)
        if cached and now - cached[0] < PAGE_CACHE_SECONDS:
            return cached[1]

    _parser, allowed = _robots_policy(url)
    if not allowed:
        logger.info("Skipping source because access is disallowed or robots.txt could not be checked: %s", url)
        return None

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            },
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as response:
            final_url = urllib.parse.urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.netloc.lower() != parsed.netloc.lower():
                logger.info("Skipping cross-origin or non-HTTPS redirect from %s", url)
                return None
            content_type = (response.headers.get("Content-Type") or "").lower()
            if response.status != 200 or (content_type and "html" not in content_type):
                return None
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                logger.info("Skipping oversized profile source: %s", url)
                return None
            html = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        with _CACHE_LOCK:
            _PAGE_CACHE[url] = (time.monotonic(), html)
        return html
    except Exception as exc:
        logger.info("Could not fetch current lawyer source %s: %s", url, exc)
        return None


def _path_is_profile(path: str, source: dict[str, Any], listing_url: str) -> bool:
    path = urllib.parse.urlparse(path).path.rstrip("/") + "/"
    listing_path = urllib.parse.urlparse(listing_url).path.rstrip("/") + "/"
    if path == listing_path:
        return False
    prefixes = source.get("profile_prefixes", ())
    if not any(path.startswith(prefix) for prefix in prefixes):
        return False
    remainder = path
    matching_prefix = max((prefix for prefix in prefixes if path.startswith(prefix)), key=len, default="")
    remainder = path[len(matching_prefix):].strip("/")
    if not remainder:
        return False
    segments = [segment for segment in remainder.split("/") if segment]
    # Support /people/first-last/ and Quebec profile URLs with IDs/slugs, while
    # excluding pagination, taxonomy archives, and generic site sections.
    if len(segments) > 2:
        return False
    ignored = {"page", "search", "category", "tag", "author", "feed", "contact", "practice-areas", "locations", "our-team", "our-people"}
    if any(segment.lower() in ignored or segment.isdigit() for segment in segments):
        return False
    return True


def _is_same_host(href: str, listing_url: str) -> bool:
    parsed = urllib.parse.urlparse(href)
    original = urllib.parse.urlparse(listing_url)
    return parsed.scheme == "https" and parsed.netloc.lower() == original.netloc.lower()


def _extract_index_candidates(html: str, listing_url: str, source: dict[str, Any]) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict[str, str]] = {}
    for anchor in soup.select("a[href]"):
        href = urllib.parse.urljoin(listing_url, anchor.get("href", "").strip())
        parsed = urllib.parse.urlparse(href)
        if not _is_same_host(href, listing_url):
            continue
        if not _path_is_profile(parsed.path, source, listing_url):
            continue
        # Strip common link decoration; the profile page's heading is authoritative.
        link_text = anchor.get_text(" ", strip=True)
        link_text = re.sub(r"\s+(view profile|view more|show .*? page)$", "", link_text, flags=re.I).strip()
        canonical = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        found.setdefault(canonical, {"profile_url": canonical, "link_text": link_text})

    # Some source cards render the name in a heading with a nearby linked profile,
    # so profile URLs are kept even if the link text is a generic action.
    return list(found.values())[: int(source.get("max_candidates", 45))]


def _pagination_urls(html: str, listing_url: str, source: dict[str, Any]) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    options: list[tuple[int, str]] = []
    origin = urllib.parse.urlparse(listing_url).netloc.lower()
    listing_path = urllib.parse.urlparse(listing_url).path.rstrip("/")
    prefix = source.get("pagination_prefix") or listing_path
    for anchor in soup.select("a[href]"):
        href = urllib.parse.urljoin(listing_url, anchor.get("href", "").strip())
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme != "https" or parsed.netloc.lower() != origin:
            continue
        if href.rstrip("/") == listing_url.rstrip("/"):
            continue
        label = anchor.get_text(" ", strip=True).lower()
        path = parsed.path.rstrip("/")
        if not (path.startswith(prefix.rstrip("/")) or parsed.query):
            continue
        page_number = None
        match = re.search(r"(?:/page/|[?&](?:paged|page|paginate|sf_paged)=)(\d+)", path + ("?" + parsed.query if parsed.query else ""))
        if match:
            page_number = int(match.group(1))
        elif label.isdigit():
            page_number = int(label)
        elif any(word in label for word in ("next", "suivant", "older", "load more", "more results", "plus ancien", "plus de résultats")):
            page_number = 99
        if page_number and page_number > 1:
            options.append((page_number, href))
    distinct = []
    seen = {listing_url.rstrip("/")}
    for _num, href in sorted(options, key=lambda item: item[0]):
        key = href.rstrip("/")
        if key not in seen:
            seen.add(key)
            distinct.append(href)
    return distinct[: max(0, int(source.get("max_index_pages", 1)) - 1)]


def _primary_profile_content(soup: BeautifulSoup) -> BeautifulSoup:
    """Return the page's main/profile content without global navigation or footer text."""
    selectors = (
        "main", "article", '[role="main"]', "[itemprop=" + '"mainContentOfPage"' + "]",
        ".lawyer-profile", ".people-profile", ".profile-detail", ".profile-content",
        ".entry-content", ".main-content", ".page-content",
    )
    content = next((soup.select_one(selector) for selector in selectors if soup.select_one(selector)), None)
    if content is not None:
        root = BeautifulSoup(str(content), "html.parser")
    else:
        root = BeautifulSoup(str(soup), "html.parser")
        for selector in ("header", "nav", "footer", "aside", ".site-header", ".site-footer", ".main-navigation", ".breadcrumb", '[aria-label="Breadcrumb"]'):
            for node in root.select(selector):
                node.decompose()

    for selector in ("script", "style", "noscript", "nav", "footer", "aside", "form", ".breadcrumb", '[aria-label="Breadcrumb"]'):
        for node in root.select(selector):
            node.decompose()
    return root


def _structured_person_name(soup: BeautifulSoup) -> str:
    """Read a person's name only from Person-shaped JSON-LD, not an organization."""
    def visit(node: Any) -> str:
        if isinstance(node, dict):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(str(kind).lower() == "person" for kind in types):
                name = node.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            for value in node.values():
                found = visit(value)
                if found:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = visit(value)
                if found:
                    return found
        return ""

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            found = visit(json.loads(script.string or script.get_text()))
            if found:
                return found
        except (json.JSONDecodeError, TypeError):
            continue
    return ""


def _page_text_and_name(html: str, link_text: str, url: str, province: str) -> tuple[str, str, str | None]:
    original = BeautifulSoup(html, "html.parser")
    content = _primary_profile_content(original)
    name = ""
    generic_headings = {
        "people", "our people", "our team", "the team", "team", "lawyers", "our lawyers",
        "employment law", "labour and employment", "labor and employment", "meet our team",
        "meet the team", "our professionals", "professionals", "lawyer profile",
    }
    for selector in ("h1", "h2"):
        for heading in content.select(selector):
            candidate = heading.get_text(" ", strip=True)
            if candidate and len(candidate) <= 100 and _normalise(candidate) not in generic_headings:
                if _valid_candidate(candidate, url):
                    name = candidate
                    break
        if name:
            break

    if not name:
        name = _structured_person_name(original)
    if not name:
        for meta_selector in ('meta[property="og:title"]', 'meta[name="author"]'):
            meta = original.select_one(meta_selector)
            candidate = (meta.get("content", "") if meta else "").strip()
            if candidate:
                # OpenGraph titles often append the firm name after a separator.
                candidate = re.split(r"\s+[|–—]\s+", candidate, maxsplit=1)[0].strip()
                if _valid_candidate(candidate, url):
                    name = candidate
                    break
    if not name:
        candidate = _clean_name(link_text, url)
        if _valid_candidate(candidate, url):
            name = candidate

    text = content.get_text(" ", strip=True)
    city = _extract_city(original, text, province)
    return name, text, city

def _clean_name(text: str, url: str) -> str:
    """Clean an actual source label; do not invent a lawyer name from the URL slug."""
    text = unescape(text or "").strip()
    text = re.sub(r"\bview profile\b|\bview more\b|\blearn more\b|\bcontact\b", "", text, flags=re.I).strip(" |:-")
    if "," in text and len(text.split(",", 1)[0].split()) <= 3:
        left, right = [part.strip() for part in text.split(",", 1)]
        if right and left and len(right.split()) <= 3:
            text = f"{right} {left}"
    if len(text.split()) >= 2 and len(text) <= 100 and not text.isdigit():
        return re.sub(r"\s+", " ", text)
    return ""

def _extract_city(soup: BeautifulSoup, text: str, province: str) -> str:
    def walk_person_addresses(item: Any) -> list[str]:
        cities: list[str] = []
        if isinstance(item, dict):
            types = item.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(str(kind).lower() == "person" for kind in types):
                address = item.get("address")
                if isinstance(address, dict) and address.get("addressLocality"):
                    cities.append(str(address["addressLocality"]).strip())
            for value in item.values():
                cities.extend(walk_person_addresses(value))
        elif isinstance(item, list):
            for value in item:
                cities.extend(walk_person_addresses(value))
        return cities

    target_terms = JURISDICTION_TERMS.get(province, ())
    excluded = {
        "alberta", "british columbia", "manitoba", "new brunswick",
        "newfoundland and labrador", "newfoundland", "labrador", "nova scotia",
        "ontario", "prince edward island", "quebec", "québec", "saskatchewan",
        "northwest territories", "nwt", "nunavut", "yukon",
    }
    target_cities = [term for term in target_terms if term not in excluded]

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            for found in walk_person_addresses(json.loads(script.string or script.get_text())):
                if any(_normalise(city) == _normalise(found) for city in target_cities):
                    return found
        except (json.JSONDecodeError, TypeError):
            continue

    normalized = _normalise(text)
    for city in target_cities:
        if re.search(r"(?<![\w])" + re.escape(_normalise(city)) + r"(?![\w])", normalized):
            if city in {"st. john's", "st john's"}:
                return "St. John's"
            return city.title()
    return ""

def _region_present(text: str, code: str, city: str = "") -> bool:
    normalized = _normalise(text)
    terms = JURISDICTION_TERMS.get(code, ())
    # Strong signal: a bar/admission phrase references this jurisdiction.
    admission_markers = ("bar admissions", "bar admission", "called to the", "admission(s)", "law society of", "membership")
    for marker in admission_markers:
        at = normalized.find(marker)
        if at >= 0:
            segment = normalized[max(0, at - 250):at + 950]
            if any(_normalise(term) in segment for term in terms):
                return True
    if city and re.search(r"(?<![\w])" + re.escape(_normalise(city)) + r"(?![\w])", normalized):
        return True
    # Match a visible office location where pages omit a separate admission section.
    cities = [term for term in terms if term not in {
        "alberta", "british columbia", "manitoba", "new brunswick", "newfoundland and labrador",
        "newfoundland", "labrador", "nova scotia", "ontario", "prince edward island", "quebec",
        "québec", "saskatchewan", "northwest territories", "nwt", "nunavut", "yukon",
    }]
    return any(re.search(r"\b" + re.escape(_normalise(term)) + r"\b", normalized) for term in cities)


def _has_workplace_practice(text: str) -> bool:
    normalized = _normalise(text)
    return any(_normalise(term) in normalized for term in WORKPLACE_TERMS)


def _valid_candidate(name: str, url: str) -> bool:
    if not name or len(name) > 100 or len(name.split()) < 2:
        return False
    lower = _normalise(name)
    reject = {
        "view profile", "view more", "learn more", "contact us", "our people",
        "our team", "the team", "people", "team", "lawyers", "employment law",
        "employment lawyers", "labour lawyers", "labor lawyers", "lawyer profile",
    }
    if lower in reject or any(term in lower for term in ("privacy policy", "terms of use", "read more")):
        return False
    if any(term in lower for term in ("employment lawyers", "labour lawyers", "labor lawyers", "meet the team", "meet our team", "our professionals")):
        return False
    return urllib.parse.urlparse(url).scheme == "https"


def _discover_index_pages(source: dict[str, Any]) -> list[tuple[str, str]]:
    """Read just enough index pages to collect a practical candidate pool."""
    start = source["listing_url"]
    html = _fetch_html(start)
    if not html:
        return []
    pages = [(start, html)]
    candidates = {item["profile_url"] for item in _extract_index_candidates(html, start, source)}
    # Usually 20–30 profile links are enough to find up to 15 practice- and region-matched
    # lawyers. Avoid making pagination requests when the first page already has that pool.
    desired_pool = min(int(source.get("max_candidates", 45)), 24)
    if len(candidates) >= desired_pool:
        return pages

    for page_url in _pagination_urls(html, start, source):
        if len(pages) >= int(source.get("max_index_pages", 1)):
            break
        page_html = _fetch_html(page_url)
        if not page_html:
            continue
        pages.append((page_url, page_html))
        candidates.update(item["profile_url"] for item in _extract_index_candidates(page_html, page_url, source))
        if len(candidates) >= desired_pool:
            break
    return pages


def _source_candidates(source: dict[str, Any]) -> list[dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    for page_url, html in _discover_index_pages(source):
        for candidate in _extract_index_candidates(html, page_url, source):
            candidates.setdefault(candidate["profile_url"], candidate)
            if len(candidates) >= int(source.get("max_candidates", 45)):
                return list(candidates.values())
    return list(candidates.values())

def _candidate_to_profile(candidate: dict[str, str], source: dict[str, Any], province: str) -> dict[str, str] | None:
    url = candidate["profile_url"]
    html = _fetch_html(url)
    if not html:
        return None
    name, text, city = _page_text_and_name(html, candidate.get("link_text", ""), url, province)
    if not _valid_candidate(name, url):
        return None

    strategy = source["strategy"]
    # The individual biography itself must indicate a current workplace-law practice;
    # do not pass a lawyer merely because the firm's global navigation mentions it.
    if not _has_workplace_practice(text):
        return None
    if strategy in {"practice_and_region", "national_workplace_firm"}:
        if not _region_present(text, province, city):
            return None
    # focused_workplace_firm and practice_area_listing pages are already specifically
    # about employment/labour practice; we still show status as unverified by this app.
    return {
        "name": name,
        "firm": source["firm_en"],
        "city": city,
        "profile_url": url,
        "profile_source_name": source["name_en"],
        "profile_source_url": source["listing_url"],
        "source_id": next((key for key, value in PROFILE_SOURCES.items() if value is source), ""),
        "status": "unverified",
    }


def get_live_profiles(province: str, max_results: int = MAX_LAWYERS_PER_JURISDICTION) -> dict[str, Any]:
    """Fetch current profiles from permitted public firm sources for one jurisdiction.

    Returns an empty list when source pages cannot be fetched, disallow retrieval, or do
    not expose sufficient evidence. The caller should still show live regulator links.
    """
    province = (province or "ON").upper()
    cache_key = f"{province}:{max_results}"
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < SOURCE_CACHE_SECONDS:
            return cached[1]

    from lawyers_data import JURISDICTIONS
    jurisdiction = JURISDICTIONS.get(province)
    if not jurisdiction:
        province = "ON"
        jurisdiction = JURISDICTIONS[province]

    candidates_out: list[dict[str, str]] = []
    sources_checked: list[dict[str, str]] = []
    seen_names: set[str] = set()
    source_ids = jurisdiction.get("source_ids", ())

    for source_id in source_ids:
        source = PROFILE_SOURCES.get(source_id)
        if not source or province not in source.get("jurisdictions", ()):
            continue
        discovered = _source_candidates(source)
        if not discovered:
            sources_checked.append({"source_id": source_id, "name": source["name_en"], "url": source["listing_url"], "result": "unavailable"})
            continue

        candidates_to_check = discovered[:MAX_PROFILE_FETCHES_PER_SOURCE]
        needed = max(0, min(max_results, MAX_LAWYERS_PER_JURISDICTION) - len(candidates_out))
        matched_by_name: dict[str, dict[str, str]] = {}
        batch_size = MAX_WORKERS * 2
        for offset in range(0, len(candidates_to_check), batch_size):
            batch = candidates_to_check[offset:offset + batch_size]
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(_candidate_to_profile, candidate, source, province): candidate
                    for candidate in batch
                }
                for future in concurrent.futures.as_completed(futures):
                    try:
                        profile = future.result()
                    except Exception as exc:
                        logger.debug("Source profile parsing failed: %s", exc)
                        profile = None
                    if profile:
                        matched_by_name.setdefault(_normalise(profile["name"]), profile)
            if len(matched_by_name) >= needed:
                break
        matched = sorted(matched_by_name.values(), key=lambda p: _normalise(p["name"]))
        for profile in matched:
            key = _normalise(profile["name"])
            if key in seen_names:
                continue
            seen_names.add(key)
            candidates_out.append(profile)
            if len(candidates_out) >= min(max_results, MAX_LAWYERS_PER_JURISDICTION):
                break
        sources_checked.append({
            "source_id": source_id,
            "name": source["name_en"],
            "url": source["listing_url"],
            "result": "profiles_found" if matched else "no_matching_profiles",
        })
        if len(candidates_out) >= min(max_results, MAX_LAWYERS_PER_JURISDICTION):
            break

    result = {
        "lawyers": candidates_out[:min(max_results, MAX_LAWYERS_PER_JURISDICTION)],
        "checked_at": _now_utc(),
        "sources_checked": sources_checked,
        "source_refresh_seconds": SOURCE_CACHE_SECONDS,
    }
    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.monotonic(), result)
    return result


def _reset_caches_for_tests() -> None:
    """Test utility: clear process caches between mocked retrieval tests."""
    with _CACHE_LOCK:
        _CACHE.clear()
        _PAGE_CACHE.clear()
        _ROBOTS_CACHE.clear()
