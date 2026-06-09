"""Tools for the stack_scanner skill — third-party widget fingerprint."""
from __future__ import annotations

import json
import re
import sys
from typing import List

import httpx


# (display_name, regex, evidence_template)
# Order matters — broader patterns first will mask narrower; we order by
# specificity so e.g. an OpenTable iframe is reported as OpenTable not "iframe".
_FINGERPRINTS: list[tuple[str, str, str]] = [
    ("OpenTable",   r"opentable\.com/(restref|r|reserve|widget)",      "OpenTable booking widget"),
    ("Resy",        r"resy\.com/cities|resy_button|resy-widget",        "Resy booking embed"),
    ("Tock",        r"exploretock\.com|tockify\.com",                   "Tock booking"),
    ("Yelp Reservations", r"yelp\.com/biz_reservation|yelp-reservations", "Yelp Reservations"),
    ("Toast",       r"toasttab\.com|toast-tab\.com",                    "Toast online ordering / POS"),
    ("Square",      r"squareup\.com/appointments|square\.site",         "Square (appointments / online store)"),
    ("Clover",      r"clover\.com/online-ordering",                     "Clover online ordering"),
    ("Calendly",    r"calendly\.com",                                   "Calendly booking embed"),
    ("Mindbody",    r"clients\.mindbodyonline\.com|mindbody-iframe",    "Mindbody booking"),
    ("Booksy",      r"booksy\.com",                                     "Booksy booking"),
    ("Vagaro",      r"vagaro\.com",                                     "Vagaro booking"),
    ("Acuity",      r"acuityscheduling\.com",                           "Acuity Scheduling"),
    ("Zocdoc",      r"zocdoc\.com",                                     "Zocdoc booking"),
    ("Healthgrades",r"healthgrades\.com",                               "Healthgrades listing"),
    ("Practo",      r"practo\.com",                                     "Practo (clinic booking)"),
    ("DoorDash",    r"doordash\.com|order\.doordash\.com",              "DoorDash menu link"),
    ("Uber Eats",   r"ubereats\.com",                                   "Uber Eats menu link"),
    ("Grubhub",     r"grubhub\.com",                                    "Grubhub menu link"),
    ("Postmates",   r"postmates\.com",                                  "Postmates menu link"),
    ("Swiggy",      r"swiggy\.com",                                     "Swiggy menu link"),
    ("Zomato",      r"zomato\.com",                                     "Zomato listing or order"),
    ("Shopify",     r"cdn\.shopify\.com|shopify\.com/checkout",         "Shopify storefront"),
    ("WooCommerce", r"woocommerce|wp-content/plugins/woocommerce",      "WooCommerce store"),
    ("Wix Bookings",r"editor\.wix\.com.*bookings|wixapps\.net/bookings","Wix Bookings"),
    ("Squarespace Scheduling", r"squarespace\.com/scheduling",          "Squarespace Scheduling"),
    ("HubSpot Forms",r"js\.hsforms\.net",                               "HubSpot form"),
    ("Intercom",    r"widget\.intercom\.io",                            "Intercom chat widget"),
    ("Drift",       r"js\.driftt\.com|drift\.com/widget",               "Drift chat widget"),
    ("Tawk.to",     r"embed\.tawk\.to",                                 "Tawk.to chat widget"),
    ("LiveChat",    r"cdn\.livechatinc\.com",                           "LiveChat widget"),
    ("Zendesk Chat",r"static\.zdassets\.com",                           "Zendesk widget"),
    ("Mailchimp",   r"mc\.us\d+\.list-manage\.com|mailchimp\.com",      "Mailchimp signup"),
    ("Google Reviews", r"google\.com/maps/embed|maps\.google\.com",     "Google Maps embed"),
]


def _fetch(url: str) -> str:
    with httpx.Client(timeout=15.0, follow_redirects=True,
                      headers={"User-Agent": "ouroboros-stack-scanner/1.0"}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text or ""


def _scan(url: str) -> dict:
    if not url:
        raise ValueError("website_url is empty")
    html = _fetch(url)
    found: List[dict] = []
    seen: set[str] = set()
    for name, pat, ev in _FINGERPRINTS:
        if name in seen:
            continue
        try:
            if re.search(pat, html, re.IGNORECASE):
                found.append({"name": name, "evidence": ev})
                seen.add(name)
        except re.error:
            continue
    return {
        "url":           url,
        "third_parties": found,
        "green_field":   len(found) == 0,
    }


try:
    from langchain_core.tools import tool

    @tool
    def scan_business_stack(website_url: str) -> str:
        """Fingerprint third-party tools embedded on a business website.

        Args:
            website_url: Absolute URL of the homepage.
        """
        try:
            return json.dumps({"ok": True, "data": _scan(website_url)})
        except ValueError as e:
            return json.dumps({"ok": False, "error": str(e), "code": "bad_input"})
        except Exception as e:
            return json.dumps({
                "ok": False, "error": f"stack scan failed: {e}", "code": "upstream",
            })

    TOOLS = [scan_business_stack]
except ImportError:
    TOOLS = []


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "scan_business_stack":
        print(json.dumps({"error": "usage: tools.py scan_business_stack <url>"}),
              file=sys.stderr)
        sys.exit(2)
    print(json.dumps(_scan(sys.argv[2])))
