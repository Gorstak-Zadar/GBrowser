# GBROWSER 2025 - Full-featured Python browser (ported from Ceprkac C#)
# Python 3.13 + PyQt6 + PyQt6-WebEngine
# Logic-matched to Ceprkac: OAuth popups, downloads, custom tab strip, auth callbacks
import sys
import os

# Chromium reads this once, at the first QtWebEngine import.
# Do NOT hide QtWebEngine from the UA / Client Hints. Google rejects a
# Chrome or Firefox disguise from this engine ("browser may not be secure")
# but accepts the honest Qt identity (as in 5.4).
_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
if "AutomationControlled" not in _flags:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        f"{_flags} --disable-features=AutomationControlled,"
        "WebAuthentication,WebAuthenticationCable,WebAuthenticationHybridTransport "
        "--disable-blink-features=AutomationControlled,WebAuthentication "
        "--enable-features=PlatformHEVCDecoderSupport,PlatformHEVCEncoderSupport "
        "--enable-media-stream"
    ).strip()

import json
import csv
import re
import hashlib
import html as html_module
import time
import ctypes
import threading
from urllib.parse import urlparse, quote_plus
from PyQt6.QtWidgets import *
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import *
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import (Qt, QUrl, QTimer, QPoint, QRect, QSize, pyqtSignal,
                          pyqtSlot, QObject)
from PyQt6.QtGui import (QIcon, QPainter, QPixmap, QColor, QFont, QPen, QBrush,
                          QKeySequence, QShortcut, QPainterPath, QAction, QFontMetrics,
                          QCursor)

# === Fernet fallback for non-Windows password encryption ===
try:
    from cryptography.fernet import Fernet as _Fernet
    import base64 as _base64
    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False

# === CONFIG ===
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".gorstak_browser")
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(os.path.join(CONFIG_DIR, "storage"), exist_ok=True)
os.makedirs(os.path.join(CONFIG_DIR, "cache"), exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
BOOKMARKS_FILE = os.path.join(CONFIG_DIR, "bookmarks.txt")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.txt")
PASSWORDS_FILE = os.path.join(CONFIG_DIR, "passwords.dat")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.txt")
MEDIA_PERM_FILE = os.path.join(CONFIG_DIR, "media_permissions.json")
DOWNLOADS_FILE = os.path.join(CONFIG_DIR, "downloads.json")
CARDS_FILE = os.path.join(CONFIG_DIR, "cards.dat")
ADDRESSES_FILE = os.path.join(CONFIG_DIR, "addresses.dat")

# === COLOUR PALETTE (Chrome-dark inspired, matching Ceprkac) ===
class Theme:
    TitleBar    = QColor(32, 33, 36)
    TabBar      = QColor(32, 33, 36)
    ActiveTab   = QColor(53, 54, 58)
    InactiveTab = QColor(40, 41, 45)
    TabHover    = QColor(48, 49, 53)
    Toolbar     = QColor(53, 54, 58)
    AddressBox  = QColor(41, 42, 45)
    BookmarkBar = QColor(53, 54, 58)
    StatusBar   = QColor(32, 33, 36)
    ForeLight   = QColor(255, 255, 255)
    ForeDim     = QColor(180, 184, 190)
    Accent      = QColor(138, 180, 248)
    CloseHover  = QColor(200, 60, 60)
    Border      = QColor(60, 64, 67)


# === DPAPI (Windows credential encryption) ===
try:
    import win32crypt
    from ctypes import windll
    DPAPI = True
except ImportError:
    DPAPI = False


if _HAS_FERNET:
    def _get_fernet_key() -> bytes:
        """Derive a Fernet key from machine hostname + username for non-DPAPI fallback."""
        import socket, getpass
        seed = f"{socket.gethostname()}|{getpass.getuser()}".encode("utf-8")
        key_bytes = hashlib.sha256(seed).digest()
        return _base64.urlsafe_b64encode(key_bytes)


# === SEARCH ENGINES ===
SEARCH_ENGINES = [
    ("Google",       "https://www.google.com",    "https://www.google.com/search?q={}"),
    ("Bing",         "https://www.bing.com",      "https://www.bing.com/search?q={}"),
    ("DuckDuckGo",   "https://duckduckgo.com",    "https://duckduckgo.com/?q={}"),
    ("Yahoo",        "https://search.yahoo.com",  "https://search.yahoo.com/search?p={}"),
    ("Brave Search", "https://search.brave.com",  "https://search.brave.com/search?q={}"),
    ("Startpage",    "https://www.startpage.com", "https://www.startpage.com/do/search?q={}"),
]

# === AD BLOCKER DOMAIN LISTS (Same as Ceprkac) ===
BLOCKED_AD_DOMAINS: set[str] = {
    # Google Ads & Analytics
    "doubleclick.net","googleadservices.com","googlesyndication.com","adservice.google.com",
    "ads.google.com","google-analytics.com","googletagmanager.com","googletagservices.com",
    "pagead2.googlesyndication.com","pagead2.googleadservices.com",
    "adtrafficquality.google","ep1.adtrafficquality.google","ep2.adtrafficquality.google",
    "fundingchoicesmessages.google.com","imasdk.googleapis.com",
    "gemius.pl","gemius.com","hit.gemius.pl",
    "stroeer.com","stroeerdigitalgroup.de",
    # Major ad networks
    "adnxs.com","taboola.com","outbrain.com","criteo.com","scorecardresearch.com","pubmatic.com",
    "rubiconproject.com","quantserve.com","quantcast.com","omniture.com","comscore.com",
    "krux.com","bluekai.com","exelate.com","adform.com","adroll.com","vungle.com","inmobi.com",
    "flurry.com","mixpanel.com","heap.io","amplitude.com","optimizely.com","bizible.com",
    "pardot.com","hubspot.com","marketo.com","eloqua.com","media.net","appnexus.com","adbrite.com",
    "admob.com","adsonar.com","zergnet.com","revcontent.com","mgid.com","adblade.com","adcolony.com",
    "chartbeat.com","newrelic.com","pingdom.net","kissmetrics.com","tradedesk.com","turn.com",
    "adscale.com","bannerflow.com","nativeads.com","contentad.com","displayads.com",
    "smartadserver.com","openx.net","casalemedia.com","indexww.com","sharethrough.com",
    "33across.com","triplelift.com","sovrn.com","lijit.com","bidswitch.net","yieldmo.com",
    "teads.tv","spotxchange.com","springserve.com","contextweb.com","liveintent.com",
    "adtech.de","adform.net","serving-sys.com","adsafeprotected.com","moatads.com",
    # Facebook / Meta
    "connect.facebook.net","pixel.facebook.com","analytics.facebook.com","ads.facebook.com","an.facebook.com",
    # Twitter / X
    "ads-twitter.com","static.ads-twitter.com","analytics.twitter.com","ads-api.twitter.com","advertising.twitter.com",
    # Reddit
    "pixel.reddit.com","rereddit.com","ads.reddit.com","events.reddit.com","events.redditmedia.com","d.reddit.com",
    # LinkedIn
    "ads.linkedin.com","analytics.pointdrive.linkedin.com",
    # TikTok
    "analytics.tiktok.com","ads.tiktok.com","ads-sg.tiktok.com","analytics-sg.tiktok.com",
    # Pinterest
    "ads.pinterest.com","log.pinterest.com","ads-dev.pinterest.com","analytics.pinterest.com",
    "trk.pinterest.com","trk2.pinterest.com","widgets.pinterest.com",
    # Amazon
    "amazon-adsystem.com","advertising-api-eu.amazon.com","amazonaax.com","amazonclix.com","assoc-amazon.com",
    # YouTube
    "youtubeads.googleapis.com","ads.youtube.com","analytics.youtube.com","video-stats.video.google.com",
    "youtube.cleverads.vn",
    # Yahoo
    "advertising.yahoo.com","ads.yahoo.com","adserver.yahoo.com","global.adserver.yahoo.com",
    "adspecs.yahoo.com","analytics.yahoo.com","analytics.query.yahoo.com","comet.yahoo.com",
    "log.fc.yahoo.com","ganon.yahoo.com","gemini.yahoo.com","beap.gemini.yahoo.com",
    "geo.yahoo.com","marketingsolutions.yahoo.com","pclick.yahoo.com",
    "ads.yap.yahoo.com","m.yap.yahoo.com","partnerads.ysm.yahoo.com",
    # Yandex
    "appmetrica.yandex.com","yandexadexchange.net","adfox.yandex.ru","adsdk.yandex.ru",
    "an.yandex.ru","awaps.yandex.ru","awsync.yandex.ru","bs.yandex.ru","bs-meta.yandex.ru",
    "clck.yandex.ru","informer.yandex.ru","kiks.yandex.ru","mc.yandex.ru","metrika.yandex.ru",
    "share.yandex.ru","offerwall.yandex.net",
    # Hotjar / Session recording
    "hotjar.com","api-hotjar.com","hotjar-analytics.com","fullstory.com","mouseflow.com",
    "luckyorange.com","luckyorange.net","freshmarketer.com",
    # Segment / Analytics
    "segment.io","segment.com","stats.wp.com",
    # Error trackers
    "notify.bugsnag.com","sessions.bugsnag.com","api.bugsnag.com","app.bugsnag.com",
    "browser.sentry-cdn.com","app.getsentry.com",
    # FastClick
    "fastclick.com","fastclick.net",
    # Samsung
    "samsungadhub.com","samsungads.com","smetrics.samsung.com","nmetrics.samsung.com",
    "analytics.samsungknox.com","bigdata.ssp.samsung.com","config.samsungads.com",
    # Apple metrics
    "metrics.apple.com","securemetrics.apple.com","supportmetrics.apple.com",
    "metrics.icloud.com","metrics.mzstatic.com","books-analytics-events.apple.com",
    "stocks-analytics-events.apple.com",
    # Xiaomi
    "api.ad.xiaomi.com","data.mistat.xiaomi.com","sdkconfig.ad.xiaomi.com",
    "globalapi.ad.xiaomi.com","tracking.miui.com","tracking.intl.miui.com",
    # Huawei
    "metrics.data.hicloud.com","logservice.hicloud.com","logbak.hicloud.com",
    # OPPO / Realme / OnePlus
    "adsfs.oppomobile.com","bdapi-in-ads.realmemobile.com",
    "analytics.oneplus.cn","click.oneplus.cn","click.oneplus.com","open.oneplus.net",
    # Additional
    "events.hotjar.io","extmaps-api.yandex.net","metrics2.data.hicloud.com",
    "logservice1.hicloud.com","iot-eu-logser.realme.com","click.googleanalytics.com",
    "grs.hicloud.com","udcm.yahoo.com","auction.unityads.unity3d.com",
    "config.unityads.unity3d.com","adserver.unityads.unity3d.com","webview.unityads.unity3d.com",
    "adfstat.yandex.ru","iadsdk.apple.com","appmetrica.yandex.ru",
    "business-api.tiktok.com","log.byteoversea.com","ads-api.tiktok.com",
    "iot-logser.realme.com","tracking.rus.miui.com","adtech.yahooinc.com",
    "bdapi-ads.realmemobile.com","ck.ads.oppomobile.com","data.ads.oppomobile.com",
    "adx.ads.oppomobile.com","data.mistat.india.xiaomi.com","data.mistat.rus.xiaomi.com",
    "notes-analytics-events.apple.com","weather-analytics-events.apple.com",
    "api-adservices.apple.com","samsung-com.112.2o7.net","analytics-api.samsunghealthcn.com",
    "unityads.unity3d.com","byteoversea.com","yahooinc.com",
    # S3-hosted ad/analytics buckets
    "adtago.s3.amazonaws.com","analyticsengine.s3.amazonaws.com",
    "analytics.s3.amazonaws.com","advice-ads.s3.amazonaws.com",
    # Adult site ad networks
    "trafficjunky.com","trafficjunky.net","trafficstars.com","tsyndicate.com",
    "exoclick.com","exosrv.com","exoticads.com","juicyads.com","realsrv.com",
    "adsrv.org","padsdel.com","syndication.exoclick.com",
    "main.exoclick.com","static.exoclick.com","ads.trafficjunky.net",
    "cdn.trafficjunky.net","a.realsrv.com",
    "syndication.realsrv.com","s.magsrv.com","magsrv.com",
    # Additional missing
    "sdkconfig.ad.intl.xiaomi.com",
    "2mdn.net","2o7.net","adnxs.net","adsrvr.org","demdex.net","doubleverify.com",
    "eyeota.net","mathtag.com","nexac.com","nr-data.net","onesignal.com",
    "pushwoosh.com","rfihub.com","rlcdn.com","rubiconproject.net","sascdn.com",
    "simpli.fi","sitescout.com","tapad.com","tealiumiq.com","tidaltv.com",
    "treasuredata.com","tynt.com","undertone.com","visualwebsiteoptimizer.com",
    "w55c.net","weborama.com","webtrends.com","zqtk.net","crazyegg.com",
    "inspectlet.com","loggly.com",
}

AD_BLOCK_WHITELIST: set[str] = {
    "discord.com","discordapp.com","discord.gg","discord.media",
    "apple.com","icloud.com","ebay.com","paypal.com","mediafire.com",
    # Auth/OAuth providers
    # Do NOT whitelist google.com itself - that also allows ads.google.com /
    # adservice.google.com (parent-domain walk) and lets GPT ads through on
    # news sites. First-party requests on google.com are already allowed.
    "accounts.google.com","accounts.youtube.com","myaccount.google.com",
    "signin.google.com","accounts.gstatic.com",
    "youtube.com","www.youtube.com",
    "login.microsoftonline.com","login.live.com","login.microsoft.com",
    "appleid.apple.com","idmsa.apple.com",
    "github.com","auth0.com","okta.com",
    "apis.google.com","ssl.gstatic.com","oauth2.googleapis.com",
    "pay.google.com","payments.google.com",
    "redditstatic.com",
    "gog.com","auth.gog.com","login.gog.com",
    "suno.com","suno.ai","clerk.suno.com",
    # AI services
    "openai.com","chat.openai.com","chatgpt.com",
    "claude.ai","anthropic.com",
    "gemini.google.com","bard.google.com",
    "perplexity.ai","you.com",
    "midjourney.com","stability.ai",
    "huggingface.co","replicate.com",
    "udio.com","poe.com","character.ai",
    "copilot.microsoft.com",
    # Banking & financial
    "chase.com","bankofamerica.com","wellsfargo.com","citibank.com",
    "usbank.com","capitalone.com","discover.com","americanexpress.com",
    "hsbc.com","barclays.com","natwest.com","lloydsbank.com",
    "revolut.com","wise.com","transferwise.com","stripe.com",
    "squareup.com","venmo.com","zelle.com","cash.app",
    "ing.com","raiffeisen.hr","pbz.hr","zaba.hr","erstebank.hr",
    "n26.com","monzo.com","starlingbank.com",
    # Gaming clients & stores
    "steampowered.com","store.steampowered.com","steamcommunity.com",
    "epicgames.com","unrealengine.com",
    "gogalaxy.com","ea.com","origin.com",
    "ubisoft.com","ubi.com",
    "blizzard.com","battle.net","battlenet.com.cn",
    "riotgames.com","leagueoflegends.com",
    "xbox.com","xboxlive.com",
    "playstation.com","sonyentertainmentnetwork.com",
    "nintendo.com","nintendo.net",
    "humblebundle.com","itch.io","indiegala.com",
    "twitch.tv",
}


# === OAuth/AUTH DOMAINS (Same as Ceprkac) ===
AUTH_DOMAINS = [
    "accounts.google.com", "signin.google.com", "accounts.gstatic.com",
    "/gsi/", "appleid.apple.com", "login.microsoftonline.com",
    "api.twitter.com", "twitter.com/i/oauth", "x.com/i/oauth", "/oauth", "/auth/",
    "/authorize", "/signin", "/sso", "pay.google.com", "payments.google.com",
    "oauth2.googleapis.com", "clerk.", "suno.com", "suno.ai"
]

def _is_auth_url(url: str) -> bool:
    """Check if URL is an auth/OAuth flow that should open in popup."""
    url_lower = url.lower()
    return any(auth in url_lower for auth in AUTH_DOMAINS)


def _to_qurl(url: str) -> QUrl:
    """Turn a bookmark, address-bar, or popup string into a navigable QUrl."""
    text = (url or "").strip()
    if not text:
        return QUrl("about:blank")
    lowered = text.lower()
    if lowered in ("about:blank", "about:srcdoc"):
        return QUrl(text)
    q = QUrl.fromUserInput(text)
    # fromUserInput adds http:// for bare hosts; prefer https unless the user typed http
    if q.isValid() and q.scheme() == "http" and not lowered.startswith("http:"):
        q.setScheme("https")
    if q.isValid() and q.scheme():
        return q
    return QUrl("about:blank")


def _is_idp_challenge_url(url: str) -> bool:
    """True on 2FA / OAuth-consent pages where autofill must not run."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()
    except Exception:
        return False
    idp_hosts = (
        "accounts.google.com", "accounts.youtube.com",
        "myaccount.google.com", "signin.google.com",
        "login.microsoftonline.com", "login.live.com", "login.microsoft.com",
        "appleid.apple.com", "idmsa.apple.com",
    )
    if not any(host == h or host.endswith("." + h) for h in idp_hosts):
        return False
    if "/pwd" in path or "/password" in path or "/identifier" in path:
        return False
    return any(p in path for p in (
        "/challenge", "/signin/oauth", "/oauth", "/consent",
        "/speedbump", "/rejected", "/signin/continue", "/unknownerror",
    ))


# Lookup caches to avoid repeated subdomain walks on hot paths (e.g. Discord)
_whitelist_cache: dict[str, bool] = {}
_ad_domain_cache: dict[str, bool] = {}


def _is_whitelisted(host: str) -> bool:
    """Check if host or any parent domain is whitelisted.

    A known ad host (or a child of one) is never allowed just because a
    parent like google.com is on the allow list.
    """
    h = host.lower()
    if h in _whitelist_cache:
        return _whitelist_cache[h]
    orig = h
    if orig not in AD_BLOCK_WHITELIST and _is_ad_domain(orig):
        _whitelist_cache[orig] = False
        return False
    while "." in h:
        if h in AD_BLOCK_WHITELIST:
            _whitelist_cache[orig] = True
            return True
        h = h[h.index(".") + 1:]
    _whitelist_cache[orig] = False
    return False


def _is_ad_domain(host: str) -> bool:
    """Check if host or any parent domain is in the blocked set."""
    h = host.lower()
    if h in _ad_domain_cache:
        return _ad_domain_cache[h]
    orig = h
    while "." in h:
        if h in BLOCKED_AD_DOMAINS:
            _ad_domain_cache[orig] = True
            return True
        h = h[h.index(".") + 1:]
    _ad_domain_cache[orig] = False
    return False


def _same_site(host1: str, host2: str) -> bool:
    """Check if two hosts share the same registrable domain (e.g. sub.reddit.com and reddit.com)."""
    def _base_domain(h: str) -> str:
        parts = h.split(".")
        # Handle common multi-part TLDs
        if len(parts) >= 3 and parts[-1] in ("uk", "au", "jp", "br", "za", "nz", "kr", "in"):
            return ".".join(parts[-3:])
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return h
    return _base_domain(host1) == _base_domain(host2)


def _is_ad_url(url: str) -> bool:
    """Check if a URL points to a known ad/tracking domain."""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = parsed.hostname or ""
        host = host.lower()
        if _is_whitelisted(host):
            return False
        if _is_ad_domain(host):
            return True
    except Exception:
        pass
    return False


def _load_blocklist_file(path: str):
    """Load domains from a blocklist file into BLOCKED_AD_DOMAINS."""
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            domain = line.strip().lstrip("\ufeff")
            if domain and not domain.startswith("#") and "." in domain:
                BLOCKED_AD_DOMAINS.add(domain.lower())
                count += 1
    _ad_domain_cache.clear()
    return count


# Path snippets from GSecurity rules.json (e.g. /pagead.js, adsbygoogle.js)
AD_PATH_FILTERS: list[str] = []


def _find_gsecurity_dir() -> str:
    """Locate the GSecurity-Ad-Shield tree (dev checkout or next to the exe)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join("E:\\", "Gorstak", "GSecurity-Ad-Shield"),
        os.path.join(here, "GSecurity-Ad-Shield"),
        os.path.join(here, "..", "GSecurity-Ad-Shield"),
        os.path.join(os.path.dirname(sys.executable), "GSecurity-Ad-Shield"),
        os.path.join(os.path.dirname(sys.executable), "..", "GSecurity-Ad-Shield"),
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.insert(0, os.path.join(meipass, "GSecurity-Ad-Shield"))
    for raw in candidates:
        path = os.path.normpath(raw)
        if os.path.isfile(os.path.join(path, "blocklist.txt")) or os.path.isfile(os.path.join(path, "main-world.js")):
            return path
    return ""


def _host_from_url_filter(url_filter: str) -> str:
    text = (url_filter or "").strip()
    if text.startswith("||"):
        host = text[2:].split("/")[0].split("^")[0].split("*")[0].lower()
        if "." in host:
            return host
    return ""


def _import_gsecurity(shield_dir: str) -> tuple[int, int]:
    """Import GSecurity-Ad-Shield blocklist + declarativeNetRequest rules."""
    if not shield_dir:
        return 0, 0
    domains = _load_blocklist_file(os.path.join(shield_dir, "blocklist.txt"))
    rules_path = os.path.join(shield_dir, "rules.json")
    rules = 0
    if os.path.isfile(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, list):
                for rule in data:
                    action = ((rule.get("action") or {}).get("type") or "").lower()
                    url_filter = (rule.get("condition") or {}).get("urlFilter") or ""
                    host = _host_from_url_filter(url_filter)
                    if action == "allow" and host:
                        AD_BLOCK_WHITELIST.add(host)
                    elif action == "block" and host:
                        BLOCKED_AD_DOMAINS.add(host)
                        rules += 1
                    elif action == "block" and url_filter and not url_filter.startswith("||"):
                        snippet = url_filter.lower().lstrip("|")
                        if len(snippet) >= 6 and snippet not in AD_PATH_FILTERS:
                            AD_PATH_FILTERS.append(snippet)
                            rules += 1
        except Exception:
            pass
    _whitelist_cache.clear()
    _ad_domain_cache.clear()
    return domains, rules


def _find_pac_dir() -> str:
    """Locate the original Pac tree (BlockAds.pac + GSecurity.user.js)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join("E:\\", "Gorstak", "Pac"),
        os.path.join(here, "Pac"),
        os.path.join(here, "..", "Pac"),
        os.path.join(os.path.dirname(sys.executable), "Pac"),
        os.path.join(os.path.dirname(sys.executable), "..", "Pac"),
    ]
    for raw in candidates:
        path = os.path.normpath(raw)
        if os.path.isfile(os.path.join(path, "BlockAds.pac")):
            return path
    return ""


def _import_pac(pac_dir: str) -> int:
    """Import BlockAds.pac whitelist + blacklist into the interceptor sets.

    GSecurity-Ad-Shield already carries the PAC regexes in main-world.js.
    This adds the explicit PAC host lists. Skip a few PAC entries that are
    whole consumer sites (amazon.co.uk) or would parent-match all of S3.
    """
    if not pac_dir:
        return 0
    pac_path = os.path.join(pac_dir, "BlockAds.pac")
    if not os.path.isfile(pac_path):
        return 0
    try:
        text = open(pac_path, "r", encoding="utf-8-sig", errors="ignore").read()
    except Exception:
        return 0
    skip_hosts = {
        "amazonaws.com", "amazon.ae", "amazon.cn", "amazon.co.uk",
        "creative.ak.fbcdn.net",  # Facebook CDN, not an ad host
    }
    added = 0

    def _js_string_list(src: str, var_name: str) -> list[str]:
        m = re.search(rf"var\s+{re.escape(var_name)}\s*=\s*\[(.*?)\];", src, re.S)
        if not m:
            return []
        return [s.lower() for s in re.findall(r'"([^"]+)"', m.group(1))]

    for host in _js_string_list(text, "whitelist"):
        if "." in host:
            AD_BLOCK_WHITELIST.add(host)
    for host in _js_string_list(text, "blacklist"):
        if "." not in host or host in skip_hosts:
            continue
        if host.startswith("amazon.") and "advertising" not in host and "adsystem" not in host:
            continue
        BLOCKED_AD_DOMAINS.add(host)
        added += 1
    _whitelist_cache.clear()
    _ad_domain_cache.clear()
    return added


# === PASSWORD MANAGER (Same logic as Ceprkac, with Fernet fallback) ===
class SavedCredential:
    def __init__(self, url="", username="", password=""):
        self.url = url
        self.username = username
        self.password = password


class PasswordManager:
    def __init__(self):
        self.passwords: list[SavedCredential] = []
        self.load()

    def load(self):
        if not os.path.exists(PASSWORDS_FILE):
            return
        try:
            with open(PASSWORDS_FILE, "rb") as f:
                encrypted = f.read()
            if DPAPI:
                import win32crypt
                decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
            elif _HAS_FERNET:
                fernet = _Fernet(_get_fernet_key())
                decrypted = fernet.decrypt(encrypted)
            else:
                decrypted = encrypted
            data = json.loads(decrypted.decode("utf-8"))
            self.passwords = [SavedCredential(e.get("u", ""), e.get("n", ""), e.get("p", "")) for e in data]
        except Exception:
            pass

    def save(self):
        try:
            data = [{"u": c.url, "n": c.username, "p": c.password} for c in self.passwords]
            raw = json.dumps(data).encode("utf-8")
            if DPAPI:
                import win32crypt
                encrypted = win32crypt.CryptProtectData(raw, None, None, None, None, 0)
            elif _HAS_FERNET:
                fernet = _Fernet(_get_fernet_key())
                encrypted = fernet.encrypt(raw)
            else:
                encrypted = raw
            with open(PASSWORDS_FILE, "wb") as f:
                f.write(encrypted)
        except Exception:
            pass

    def get_matches(self, domain: str) -> list[SavedCredential]:
        """Match on exact host OR registrable-domain suffix (Ceprkac 0.8.0), so
        accounts.google.com credentials fill on the google.com password step and
        vice versa."""
        matches = []
        domain = (domain or "").lower()
        for p in self.passwords:
            try:
                saved = (urlparse(p.url).hostname or "").lower()
                if not saved:
                    continue
                # Exact host, or a suffix relationship that still shares the same
                # registrable domain (so accounts.google.com <-> google.com matches
                # but a broad saved host cannot leak onto an unrelated site).
                if saved == domain:
                    matches.append(p)
                elif ((domain.endswith("." + saved) or saved.endswith("." + domain))
                      and _same_site(saved, domain)):
                    matches.append(p)
            except Exception:
                pass
        return matches

    def import_csv(self, filepath: str) -> int:
        """Import Chrome/Edge CSV format: name,url,username,password
        With sanitization: length limits and control character filtering."""
        _MAX_FIELD_LEN = 2048
        _CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
        count = 0
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) < 4:
                    continue
                url, username, password = row[1].strip(), row[2].strip(), row[3].strip()
                # Length limits
                if len(url) > _MAX_FIELD_LEN or len(username) > _MAX_FIELD_LEN or len(password) > _MAX_FIELD_LEN:
                    continue
                # Skip rows with control characters
                if _CONTROL_RE.search(url) or _CONTROL_RE.search(username) or _CONTROL_RE.search(password):
                    continue
                if not url or not username:
                    continue
                if not any(p.url.lower() == url.lower() and p.username.lower() == username.lower()
                           for p in self.passwords):
                    self.passwords.append(SavedCredential(url, username, password))
                    count += 1
        self.save()
        return count

    def clear(self):
        self.passwords.clear()
        self.save()

    def find_exact(self, host: str, username: str):
        """Return the saved credential for host+username, or None."""
        host = (host or "").lower()
        for c in self.passwords:
            try:
                if ((urlparse(c.url).hostname or "").lower() == host
                        and c.username == (username or "")):
                    return c
            except Exception:
                pass
        return None

    def add_or_update(self, url: str, username: str, password: str):
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        existing = self.find_exact(host, username) if host else None
        if existing is not None:
            existing.password = password
            if url:
                existing.url = url
        else:
            self.passwords.append(SavedCredential(url, username or "", password))
        self.save()


# === DPAPI / Fernet blob helpers (shared by cards & addresses) ===
def _encrypt_blob(raw: bytes) -> bytes:
    if DPAPI:
        import win32crypt
        return win32crypt.CryptProtectData(raw, None, None, None, None, 0)
    if _HAS_FERNET:
        return _Fernet(_get_fernet_key()).encrypt(raw)
    return raw


def _decrypt_blob(data: bytes) -> bytes:
    if DPAPI:
        import win32crypt
        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    if _HAS_FERNET:
        return _Fernet(_get_fernet_key()).decrypt(data)
    return data


# === PAYMENT METHODS (cards) - DPAPI at rest, same scheme as passwords ===
class SavedCard:
    def __init__(self, label="", name="", number="", exp_month="", exp_year="", cvc=""):
        self.label = label
        self.name = name
        self.number = number
        self.exp_month = exp_month
        self.exp_year = exp_year
        self.cvc = cvc

    @property
    def last4(self) -> str:
        digits = re.sub(r"\D", "", self.number or "")
        return digits[-4:] if len(digits) >= 4 else digits

    @property
    def display(self) -> str:
        base = self.label or self.name or "Card"
        return f"{base}  ---- {self.last4}" if self.last4 else base


class CardManager:
    def __init__(self):
        self.cards: list[SavedCard] = []
        self.load()

    def load(self):
        if not os.path.exists(CARDS_FILE):
            return
        try:
            data = json.loads(_decrypt_blob(open(CARDS_FILE, "rb").read()).decode("utf-8"))
            self.cards = [SavedCard(d.get("label", ""), d.get("name", ""), d.get("num", ""),
                                    d.get("em", ""), d.get("ey", ""), d.get("cvc", ""))
                          for d in data if d.get("num")]
        except Exception:
            pass

    def save(self):
        try:
            data = [{"label": c.label, "name": c.name, "num": c.number,
                     "em": c.exp_month, "ey": c.exp_year, "cvc": c.cvc} for c in self.cards]
            raw = json.dumps(data).encode("utf-8")
            with open(CARDS_FILE, "wb") as f:
                f.write(_encrypt_blob(raw))
        except Exception:
            pass


# === ADDRESSES / contact profiles - DPAPI at rest ===
class SavedAddress:
    def __init__(self, label="", full_name="", email="", phone="", line1="", line2="",
                 city="", state="", postal_code="", country=""):
        self.label = label
        self.full_name = full_name
        self.email = email
        self.phone = phone
        self.line1 = line1
        self.line2 = line2
        self.city = city
        self.state = state
        self.postal_code = postal_code
        self.country = country

    @property
    def display(self) -> str:
        base = self.label or self.full_name or self.email or "Address"
        loc = ", ".join(x for x in (self.city, self.country) if x)
        return f"{base}  ({loc})" if loc else base


class AddressManager:
    def __init__(self):
        self.addresses: list[SavedAddress] = []
        self.load()

    def load(self):
        if not os.path.exists(ADDRESSES_FILE):
            return
        try:
            data = json.loads(_decrypt_blob(open(ADDRESSES_FILE, "rb").read()).decode("utf-8"))
            for d in data:
                a = SavedAddress(d.get("label", ""), d.get("name", ""), d.get("email", ""),
                                 d.get("phone", ""), d.get("l1", ""), d.get("l2", ""),
                                 d.get("city", ""), d.get("state", ""), d.get("zip", ""),
                                 d.get("country", ""))
                if a.full_name or a.line1:
                    self.addresses.append(a)
        except Exception:
            pass

    def save(self):
        try:
            data = [{"label": a.label, "name": a.full_name, "email": a.email, "phone": a.phone,
                     "l1": a.line1, "l2": a.line2, "city": a.city, "state": a.state,
                     "zip": a.postal_code, "country": a.country} for a in self.addresses]
            raw = json.dumps(data).encode("utf-8")
            with open(ADDRESSES_FILE, "wb") as f:
                f.write(_encrypt_blob(raw))
        except Exception:
            pass


# Detect card / address fields on the current page (Ceprkac detectJs).
CHECKOUT_DETECT_JS = r"""(function(){
    function has(sel){ try { return !!document.querySelector(sel); } catch(e){ return false; } }
    var card = has('input[autocomplete="cc-number"]') || has('input[name*="cardnumber" i]') ||
               has('input[autocomplete="cc-csc"]') || has('input[name*="card" i][name*="num" i]');
    var addr = has('input[autocomplete="address-line1"]') || has('input[autocomplete="street-address"]') ||
               has('input[autocomplete="postal-code"]') || has('input[name*="address1" i]') ||
               has('input[name*="street" i]');
    return (card ? 'card' : '') + (addr ? 'addr' : '');
})()"""


def _make_fill_card_js(card: "SavedCard") -> str:
    def j(s): return json.dumps(s or "")
    exp2 = card.exp_year[-2:] if len(card.exp_year) >= 2 else card.exp_year
    return f"""(function(){{
    function setVal(el,val){{ if(!el||!val)return;
        var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
        s.call(el,val); el.dispatchEvent(new Event('input',{{bubbles:true}}));
        el.dispatchEvent(new Event('change',{{bubbles:true}})); }}
    function pick(){{ for(var i=0;i<arguments.length;i++){{ try{{var e=document.querySelector(arguments[i]); if(e)return e;}}catch(x){{}} }} return null; }}
    setVal(pick('input[autocomplete="cc-number"]','input[name*="cardnumber" i]','input[name*="card" i][name*="num" i]','input[id*="card" i][id*="num" i]'), {j(card.number)});
    setVal(pick('input[autocomplete="cc-name"]','input[name*="cardholder" i]','input[name*="ccname" i]','input[id*="cardname" i]'), {j(card.name)});
    setVal(pick('input[autocomplete="cc-csc"]','input[name*="cvc" i]','input[name*="cvv" i]','input[id*="cvc" i]','input[id*="cvv" i]'), {j(card.cvc)});
    var exp=pick('input[autocomplete="cc-exp"]','input[name*="exp" i]','input[id*="exp" i]');
    if(exp) setVal(exp, {j(card.exp_month + "/" + exp2)});
    setVal(pick('input[autocomplete="cc-exp-month"]','select[autocomplete="cc-exp-month"]','input[name*="expmonth" i]','[id*="expmonth" i]'), {j(card.exp_month)});
    setVal(pick('input[autocomplete="cc-exp-year"]','select[autocomplete="cc-exp-year"]','input[name*="expyear" i]','[id*="expyear" i]'), {j(card.exp_year)});
}})()"""


def _make_fill_address_js(a: "SavedAddress") -> str:
    def j(s): return json.dumps(s or "")
    return f"""(function(){{
    function setVal(el,val){{ if(!el||!val)return;
        var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set
            ||Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
        s.call(el,val); el.dispatchEvent(new Event('input',{{bubbles:true}}));
        el.dispatchEvent(new Event('change',{{bubbles:true}})); }}
    function pick(){{ for(var i=0;i<arguments.length;i++){{ try{{var e=document.querySelector(arguments[i]); if(e)return e;}}catch(x){{}} }} return null; }}
    setVal(pick('input[autocomplete="name"]','input[name*="fullname" i]','input[name="name"]','input[id*="fullname" i]'), {j(a.full_name)});
    setVal(pick('input[autocomplete="email"]','input[type="email"]','input[name*="email" i]'), {j(a.email)});
    setVal(pick('input[autocomplete="tel"]','input[type="tel"]','input[name*="phone" i]'), {j(a.phone)});
    setVal(pick('input[autocomplete="address-line1"]','input[autocomplete="street-address"]','input[name*="address1" i]','input[name*="street" i]','input[id*="address1" i]'), {j(a.line1)});
    setVal(pick('input[autocomplete="address-line2"]','input[name*="address2" i]','input[id*="address2" i]'), {j(a.line2)});
    setVal(pick('input[autocomplete="address-level2"]','input[name*="city" i]','input[id*="city" i]'), {j(a.city)});
    setVal(pick('input[autocomplete="address-level1"]','input[name*="state" i]','input[name*="region" i]','input[id*="state" i]'), {j(a.state)});
    setVal(pick('input[autocomplete="postal-code"]','input[name*="zip" i]','input[name*="postal" i]','input[id*="zip" i]','input[id*="postal" i]'), {j(a.postal_code)});
    setVal(pick('input[autocomplete="country"]','input[name*="country" i]','select[name*="country" i]','[id*="country" i]'), {j(a.country)});
}})()"""


# === BOOKMARK DATA MODEL (Same as Ceprkac) ===
class BookmarkNode:
    def __init__(self, type_="link", title="", href="", children=None):
        self.type = type_
        self.title = title
        self.href = href
        self.children: list[BookmarkNode] = children or []


def _load_bookmarks() -> list[BookmarkNode]:
    if not os.path.exists(BOOKMARKS_FILE):
        return []
    nodes: list[BookmarkNode] = []
    stack: list[list[BookmarkNode]] = [nodes]
    with open(BOOKMARKS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) < 2:
                parts = line.split("|", 2)
            current = stack[-1]
            if parts[0] == "FOLDER" and len(parts) >= 2:
                folder = BookmarkNode("folder", parts[1])
                current.append(folder)
                stack.append(folder.children)
            elif parts[0] == "ENDFOLDER":
                if len(stack) > 1:
                    stack.pop()
            elif parts[0] == "LINK" and len(parts) >= 3:
                current.append(BookmarkNode("link", parts[1], parts[2]))
            else:
                legacy = line.split("|", 1)
                if len(legacy) == 2:
                    current.append(BookmarkNode("link", legacy[0], legacy[1]))
                else:
                    current.append(BookmarkNode("link", _display_title(line), line))
    return nodes


def _save_bookmarks(nodes: list[BookmarkNode]):
    lines: list[str] = []
    _write_bookmark_nodes(lines, nodes)
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_bookmark_nodes(lines: list[str], nodes: list[BookmarkNode]):
    for node in nodes:
        if node.type == "folder":
            lines.append(f"FOLDER\t{node.title}")
            _write_bookmark_nodes(lines, node.children)
            lines.append("ENDFOLDER")
        else:
            lines.append(f"LINK\t{node.title}\t{node.href}")


def _bookmark_exists(nodes: list[BookmarkNode], url: str) -> bool:
    for n in nodes:
        if n.type == "link" and n.href.lower() == url.lower():
            return True
        if n.type == "folder" and _bookmark_exists(n.children, url):
            return True
    return False


def _remove_bookmark(nodes: list[BookmarkNode], url: str) -> bool:
    for i, n in enumerate(nodes):
        if n.type == "link" and n.href.lower() == url.lower():
            nodes.pop(i)
            return True
        if n.type == "folder" and _remove_bookmark(n.children, url):
            return True
    return False


def _count_links(nodes: list[BookmarkNode]) -> int:
    count = 0
    for n in nodes:
        if n.type == "link":
            count += 1
        elif n.type == "folder":
            count += _count_links(n.children)
    return count


def _display_title(url: str) -> str:
    try:
        return urlparse(url).hostname or url[:30]
    except Exception:
        return url[:30] if len(url) > 30 else url


def _collect_bookmark_urls(nodes: list[BookmarkNode]) -> list[str]:
    """Collect all bookmark URLs for autocomplete."""
    urls = []
    for n in nodes:
        if n.type == "link":
            urls.append(n.href)
        elif n.type == "folder":
            urls.extend(_collect_bookmark_urls(n.children))
    return urls


# === BOOKMARK HTML IMPORT/EXPORT (Same as Ceprkac) ===
def _parse_bookmarks_html(html_text: str) -> list[BookmarkNode]:
    """Parse Netscape bookmark HTML format with nested folders."""
    dl_start = html_text.lower().find("<dl")
    if dl_start >= 0:
        result, _ = _parse_dl(html_text, dl_start)
        while len(result) == 1 and result[0].type == "folder":
            result = result[0].children
        return result
    result = []
    for m in re.finditer(r'<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html_text, re.IGNORECASE | re.DOTALL):
        href, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if href:
            result.append(BookmarkNode("link", title or _display_title(href), href))
    return result


def _parse_dl(html_text: str, pos: int) -> tuple[list[BookmarkNode], int]:
    nodes: list[BookmarkNode] = []
    tag_end = html_text.find(">", pos)
    if tag_end < 0:
        return nodes, pos
    pos = tag_end + 1
    length = len(html_text)

    while pos < length:
        next_tag = html_text.find("<", pos)
        if next_tag < 0:
            break
        pos = next_tag
        close_angle = html_text.find(">", pos)
        if close_angle < 0:
            break
        tag = html_text[pos:close_angle + 1]
        tag_upper = tag.upper()

        if tag_upper.startswith("</DL"):
            pos = close_angle + 1
            return nodes, pos

        if tag_upper.startswith("<DT") or tag_upper.startswith("<P") or tag_upper.startswith("<DD"):
            pos = close_angle + 1
            continue

        if tag_upper.startswith("<H3") or tag_upper.startswith("<H1") or tag_upper.startswith("<H2"):
            pos = close_angle + 1
            close_tag = "</" + tag[1:3] + ">"
            h_end = html_text.lower().find(close_tag.lower(), pos)
            folder_title = "Folder"
            if h_end > pos:
                folder_title = re.sub(r'<[^>]+>', '', html_text[pos:h_end]).strip()
                pos = h_end + len(close_tag)
            search_limit = min(pos + 200, length)
            child_dl = html_text.lower().find("<dl", pos, search_limit)
            children = []
            if child_dl >= 0:
                children, pos = _parse_dl(html_text, child_dl)
            nodes.append(BookmarkNode("folder", folder_title, children=children))
            continue

        if tag_upper.startswith("<A ") and "HREF" in tag_upper:
            href_match = re.search(r'href="([^"]*)"', tag, re.IGNORECASE)
            href = href_match.group(1) if href_match else ""
            pos = close_angle + 1
            a_end = html_text.lower().find("</a>", pos)
            title = ""
            if a_end > pos:
                title = re.sub(r'<[^>]+>', '', html_text[pos:a_end]).strip()
                pos = a_end + 4
            if href:
                nodes.append(BookmarkNode("link", title or _display_title(href), href))
            continue

        pos = close_angle + 1

    return nodes, pos


def _export_bookmarks_html(nodes: list[BookmarkNode], filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write('<!DOCTYPE NETSCAPE-Bookmark-file-1>\n')
        f.write('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n')
        f.write('<TITLE>Bookmarks</TITLE>\n')
        f.write('<H1>Bookmarks</H1>\n')
        f.write('<DL><p>\n')
        _write_bookmarks_html(f, nodes, "    ")
        f.write('</DL><p>\n')


def _write_bookmarks_html(f, nodes: list[BookmarkNode], indent: str):
    for node in nodes:
        if node.type == "folder":
            safe_title = html_module.escape(node.title)
            f.write(f'{indent}<DT><H3>{safe_title}</H3>\n')
            f.write(f'{indent}<DL><p>\n')
            _write_bookmarks_html(f, node.children, indent + "    ")
            f.write(f'{indent}</DL><p>\n')
        else:
            safe_title = html_module.escape(node.title)
            safe_url = html_module.escape(node.href)
            f.write(f'{indent}<DT><A HREF="{safe_url}">{safe_title}</A>\n')


# === SETTINGS (Same as Ceprkac) ===
def _load_settings() -> dict:
    settings = {"homepage": "https://www.google.com", "searchurl": "https://www.google.com/search?q={}"}
    if not os.path.exists(SETTINGS_FILE):
        return settings
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower()
                    if key == "homepage":
                        settings["homepage"] = parts[1].strip()
                    elif key == "searchurl":
                        settings["searchurl"] = parts[1].strip()
    except Exception:
        pass
    return settings


def _save_settings(homepage: str, searchurl: str):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write(f"homepage={homepage}\n")
            f.write(f"searchurl={searchurl}\n")
    except Exception:
        pass


# === HISTORY (Same as Ceprkac, with case-insensitive dedup) ===
def _load_history() -> list[str]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        seen = set()
        unique = []
        for l in lines:
            key = l.lower()
            if key not in seen:
                seen.add(key)
                unique.append(l)
        return unique[-100:]
    except Exception:
        return []


def _save_history(history: list[str]):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(history) + "\n")
    except Exception:
        pass


# === CUSTOM CHROME TAB STRIP (Like Ceprkac) ===
class ChromeTab:
    def __init__(self):
        self.title: str = "New Tab"
        self.url: str = ""
        self.web_view: QWebEngineView | None = None
        self.is_loading: bool = False
        self.load_progress: int = 0
        self.last_autofill_attempt: float = 0
        self.zoom_factor: float = 1.0
        self.is_popup: bool = False
        self.focus_omnibox: bool = False
        # Per-URL monotonic autofill keying (Ceprkac parity): a genuinely new page
        # always re-attempts; a stale retry loop self-cancels when the URL moves on.
        self.autofill_token: int = 0
        self.last_autofill_url: str = ""
        self.autofill_in_progress: bool = False
        self.last_checkout_attempt: float = 0
        self.last_checkout_url: str = ""
        self.checkout_token: int = 0
        self.checkout_in_progress: bool = False


class ChromeTabStrip(QWidget):
    """Custom-drawn Chrome-style tab strip matching Ceprkac."""
    tab_clicked = pyqtSignal(int)
    tab_close_clicked = pyqtSignal(int)
    new_tab_clicked = pyqtSignal()

    CLOSE_SIZE = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabs: list[ChromeTab] = []
        self.selected_index: int = -1
        self.hover_index: int = -1
        self.hover_close_index: int = -1
        self._drag_start_pos: QPoint | None = None
        self._drag_tab_index: int = -1
        self.setFixedHeight(42)
        self.setMouseTracking(True)
        self.font = QFont("Segoe UI", 9)

    def add_tab(self, tab: ChromeTab, title: str = "New Tab") -> int:
        tab.title = title
        self.tabs.append(tab)
        self.update()
        return len(self.tabs) - 1

    def insert_tab(self, index: int, tab: ChromeTab, title: str = "New Tab"):
        tab.title = title
        self.tabs.insert(index, tab)
        if self.selected_index >= index:
            self.selected_index += 1
        self.update()

    def remove_tab(self, index: int):
        if 0 <= index < len(self.tabs):
            self.tabs.pop(index)
            if self.selected_index >= len(self.tabs):
                self.selected_index = len(self.tabs) - 1
            self.update()

    def set_tab_text(self, index: int, text: str):
        if 0 <= index < len(self.tabs):
            self.tabs[index].title = text
            self.update()

    def set_current_index(self, index: int):
        if 0 <= index < len(self.tabs):
            self.selected_index = index
            self.update()

    def _get_tab_width(self) -> int:
        if not self.tabs:
            return 200
        available = self.width() - 40 - 16
        w = available // max(len(self.tabs), 1)
        return max(60, min(240, w))

    def _get_tab_rect(self, index: int) -> QRect:
        w = self._get_tab_width()
        x = 8 + index * (w + 1)
        return QRect(x, 6, w, 34)

    def _get_close_rect(self, tab_rect: QRect) -> QRect:
        return QRect(tab_rect.right() - 20, tab_rect.y() + 9, self.CLOSE_SIZE, self.CLOSE_SIZE)

    def _get_new_tab_rect(self) -> QRect:
        w = self._get_tab_width()
        x = 8 + len(self.tabs) * (w + 1) + 4
        return QRect(x, 10, 28, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), Theme.TabBar)

        # New tab button (+)
        new_rect = self._get_new_tab_rect()
        painter.fillRect(new_rect, Theme.InactiveTab)
        pen = QPen(Theme.ForeLight, 1)
        painter.setPen(pen)
        cx = new_rect.center().x()
        cy = new_rect.center().y()
        painter.drawLine(cx - 4, cy, cx + 4, cy)
        painter.drawLine(cx, cy - 4, cx, cy + 4)

        # Bottom line under inactive area
        if 0 <= self.selected_index < len(self.tabs):
            sel_rect = self._get_tab_rect(self.selected_index)
            painter.setPen(QPen(Theme.ActiveTab, 2))
            painter.drawLine(0, self.height() - 1, sel_rect.left(), self.height() - 1)
            painter.drawLine(sel_rect.right(), self.height() - 1, self.width(), self.height() - 1)

        # Draw tabs
        for i in range(len(self.tabs)):
            if i == self.selected_index:
                continue
            self._draw_tab(painter, i)
        if 0 <= self.selected_index < len(self.tabs):
            self._draw_tab(painter, self.selected_index)

        painter.end()

    def _draw_tab(self, painter: QPainter, index: int):
        rect = self._get_tab_rect(index)
        tab = self.tabs[index]
        active = index == self.selected_index
        hover = index == self.hover_index and not active

        bg = Theme.ActiveTab if active else (Theme.TabHover if hover else Theme.InactiveTab)

        # Draw tab background
        painter.fillRect(QRect(rect.x(), rect.y() + 4, rect.width(), rect.height() - 6), bg)

        # Text
        text_rect = QRect(rect.x() + 12, rect.y() + 4, rect.width() - 36, rect.height() - 8)
        painter.setPen(Theme.ForeLight if active else Theme.ForeDim)
        painter.setFont(self.font)
        elided = QFontMetrics(self.font).elidedText(tab.title[:25], Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # Close button X (like Ceprkac's closePen)
        if len(self.tabs) > 1 or active:
            close_rect = self._get_close_rect(rect)
            close_hover = index == self.hover_close_index
            if close_hover:
                painter.setBrush(QBrush(Theme.CloseHover))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(close_rect)
            close_pen = QPen(QColor(255, 255, 255) if close_hover else Theme.ForeDim, 1.2)
            painter.setPen(close_pen)
            m = 4
            painter.drawLine(close_rect.x() + m, close_rect.y() + m,
                             close_rect.right() - m, close_rect.bottom() - m)
            painter.drawLine(close_rect.right() - m, close_rect.y() + m,
                             close_rect.x() + m, close_rect.bottom() - m)

        # Loading indicator line at bottom (like Ceprkac's loadPen)
        if tab.is_loading:
            load_pen = QPen(Theme.Accent, 2)
            painter.setPen(load_pen)
            progress_width = max(1, (rect.width() - 8) * tab.load_progress // 100) if tab.load_progress > 0 else (rect.width() - 8) // 3
            painter.drawLine(rect.x() + 4, rect.bottom() - 2,
                             rect.x() + 4 + progress_width, rect.bottom() - 2)

    def mouseMoveEvent(self, event):
        # Tab drag-to-reorder
        if self._drag_start_pos is not None and self._drag_tab_index >= 0:
            delta = event.pos().x() - self._drag_start_pos.x()
            tab_w = self._get_tab_width() + 1
            if abs(delta) > tab_w // 2:
                direction = 1 if delta > 0 else -1
                new_idx = self._drag_tab_index + direction
                if 0 <= new_idx < len(self.tabs):
                    # Swap tabs
                    self.tabs[self._drag_tab_index], self.tabs[new_idx] = self.tabs[new_idx], self.tabs[self._drag_tab_index]
                    if self.selected_index == self._drag_tab_index:
                        self.selected_index = new_idx
                    elif self.selected_index == new_idx:
                        self.selected_index = self._drag_tab_index
                    self._drag_tab_index = new_idx
                    self._drag_start_pos = event.pos()
                    self.update()
                    self.tab_clicked.emit(self.selected_index)
            return

        old_hover = self.hover_index
        old_close = self.hover_close_index
        self.hover_index = -1
        self.hover_close_index = -1

        for i in range(len(self.tabs)):
            rect = self._get_tab_rect(i)
            if rect.contains(event.pos()):
                self.hover_index = i
                if self._get_close_rect(rect).contains(event.pos()):
                    self.hover_close_index = i
                break

        if old_hover != self.hover_index or old_close != self.hover_close_index:
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Middle-click to close tab (like Ceprkac)
            for i in range(len(self.tabs)):
                if self._get_tab_rect(i).contains(event.pos()):
                    self.tab_close_clicked.emit(i)
                    return
            return

        new_rect = self._get_new_tab_rect()
        if new_rect.contains(event.pos()):
            self.new_tab_clicked.emit()
            return

        for i in range(len(self.tabs)):
            rect = self._get_tab_rect(i)
            if rect.contains(event.pos()):
                if self._get_close_rect(rect).contains(event.pos()):
                    self.tab_close_clicked.emit(i)
                else:
                    self.selected_index = i
                    self.tab_clicked.emit(i)
                    # Start drag tracking
                    self._drag_start_pos = event.pos()
                    self._drag_tab_index = i
                self.update()
                break

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_tab_index = -1


# === AD BLOCKER INTERCEPTOR (Same logic as Ceprkac) ===
class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self):
        super().__init__()
        self.blocked_count = 0

    def interceptRequest(self, info):
        try:
            first_party_host = ""
            first_party_url = info.firstPartyUrl()
            if first_party_url and not first_party_url.isEmpty():
                first_party_host = first_party_url.host().lower()

            host = info.requestUrl().host().lower()

            # Never cancel a top-level navigation. Blocking the main document
            # leaves the user on the previous page (usually the homepage).
            if info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.MainFrame:
                return

            # Fast path: if the request target is whitelisted, always allow
            if _is_whitelisted(host):
                return

            # Determine if this is a same-site (first-party) request
            is_first_party = first_party_host and _same_site(host, first_party_host)

            # Same-site requests are NEVER blocked - sites need their own
            # subdomains for auth, APIs, telemetry, content delivery, etc.
            if is_first_party:
                return

            # Third-party: block known ad domains
            if _is_ad_domain(host):
                info.block(True)
                self.blocked_count += 1
                return

            # GSecurity path rules (/pagead.js, adsbygoogle.js, ...) - third-party only
            if AD_PATH_FILTERS:
                full = info.requestUrl().toString().lower()
                for snippet in AD_PATH_FILTERS:
                    if snippet in full:
                        info.block(True)
                        self.blocked_count += 1
                        return
        except Exception:
            pass


def _load_media_permissions() -> dict:
    try:
        with open(MEDIA_PERM_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_media_permissions(data: dict) -> None:
    try:
        with open(MEDIA_PERM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _list_media_devices() -> tuple[list[str], list[str]]:
    cams, mics = [], []
    try:
        from PyQt6.QtMultimedia import QMediaDevices
        cams = [d.description() for d in QMediaDevices.videoInputs() if d.description()]
        mics = [d.description() for d in QMediaDevices.audioInputs() if d.description()]
    except Exception:
        pass
    return cams, mics


def _permission_kinds(type_name: str) -> list[str]:
    n = (type_name or "").lower()
    kinds = []
    if "desktop" in n:
        kinds.append("screen")
    if "video" in n or "mediaaudiovideo" in n:
        kinds.append("camera")
    if "audio" in n and "desktop" not in n:
        kinds.append("microphone")
    if "mediaaudio" in n and "video" not in n:
        if "microphone" not in kinds:
            kinds.append("microphone")
    if not kinds and any(x in n for x in ("media", "video", "audio")):
        kinds = ["camera", "microphone"]
    return kinds


class MediaPermissionDialog(QDialog):
    """Chrome-style camera/mic prompt: which device, and how long to allow."""

    def __init__(self, origin: str, kinds: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("GBrowser")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._choice = "deny"
        bg = f"rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()})"
        box = f"rgb({Theme.AddressBox.red()},{Theme.AddressBox.green()},{Theme.AddressBox.blue()})"
        self.setStyleSheet(
            f"QDialog {{ background: {bg}; color: white; }}"
            f"QLabel {{ color: white; }}"
            f"QComboBox {{ background: {box}; color: white; border: 1px solid rgb(60,64,67);"
            f" border-radius: 4px; padding: 4px 8px; min-height: 24px; }}"
            f"QComboBox QAbstractItemView {{ background: {box}; color: white; }}"
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        host = origin
        try:
            host = urlparse(origin).hostname or origin
        except Exception:
            pass
        what = " and ".join(kinds) if kinds else "your camera"
        title = QLabel(f"{host} wants to use your {what}")
        title.setWordWrap(True)
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        hint = QLabel("Choose a device and how long this site may use it.")
        hint.setStyleSheet("color: rgb(180,184,190);")
        layout.addWidget(hint)

        cams, mics = _list_media_devices()
        self._cam_combo = None
        self._mic_combo = None
        if "camera" in kinds:
            layout.addWidget(QLabel("Camera"))
            self._cam_combo = QComboBox()
            if cams:
                self._cam_combo.addItems(cams)
            else:
                self._cam_combo.addItem("Default camera")
            layout.addWidget(self._cam_combo)
        if "microphone" in kinds:
            layout.addWidget(QLabel("Microphone"))
            self._mic_combo = QComboBox()
            if mics:
                self._mic_combo.addItems(mics)
            else:
                self._mic_combo.addItem("Default microphone")
            layout.addWidget(self._mic_combo)

        layout.addWidget(QLabel("Allow access"))
        self._duration = QComboBox()
        self._duration.addItem("This time only", "once")
        self._duration.addItem("While visiting this site", "session")
        self._duration.addItem("Always on this site", "always")
        self._duration.setCurrentIndex(1)
        layout.addWidget(self._duration)

        btns = QHBoxLayout()
        btns.addStretch(1)
        block = QPushButton("Block")
        block.setStyleSheet(
            "QPushButton { background: rgb(60,64,67); color: white; border: none;"
            " border-radius: 4px; padding: 8px 16px; }"
            "QPushButton:hover { background: rgb(80,84,87); }")
        block.clicked.connect(self._on_block)
        allow = QPushButton("Allow")
        allow.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
            f" color: black; border: none; border-radius: 4px; padding: 8px 16px; font-weight: 600; }}")
        allow.clicked.connect(self._on_allow)
        btns.addWidget(block)
        btns.addWidget(allow)
        layout.addLayout(btns)

    def _on_allow(self):
        self._choice = self._duration.currentData() or "session"
        self.accept()

    def _on_block(self):
        dur = self._duration.currentData() or "once"
        self._choice = "block-always" if dur == "always" else "deny"
        self.reject()

    def choice(self) -> str:
        return self._choice


# === CUSTOM WEB PAGE FOR POPUP HANDLING (Ceprkac-style) ===
class BrowserPage(QWebEnginePage):
    def __init__(self, profile, parent=None, browser_window=None):
        super().__init__(profile, parent)
        self.browser_window = browser_window
        self._last_url = ""
        # Qt 6.8+ uses permissionRequested; older builds use featurePermissionRequested.
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(self._on_permission_requested)
        if hasattr(self, "featurePermissionRequested"):
            self.featurePermissionRequested.connect(self._on_feature_permission_requested)

    def _on_permission_requested(self, permission):
        try:
            ptype = permission.permissionType()
            name = getattr(ptype, "name", str(ptype))
            origin = ""
            try:
                origin = permission.origin().toString() if permission.origin() else ""
            except Exception:
                origin = self.url().toString()
            kinds = _permission_kinds(name)
            if kinds and self.browser_window:
                self.browser_window._handle_media_permission(origin, kinds, permission, None)
                return
            quiet = {"Notifications", "Geolocation", "MouseLock", "ClipboardReadWrite"}
            if name in quiet:
                permission.grant()
            else:
                permission.deny()
        except Exception:
            try:
                permission.deny()
            except Exception:
                pass

    def _on_feature_permission_requested(self, origin, feature):
        try:
            name = getattr(feature, "name", str(feature))
            kinds = _permission_kinds(name)
            origin_s = origin.toString() if hasattr(origin, "toString") else str(origin)
            if kinds and self.browser_window:
                self.browser_window._handle_media_permission(
                    origin_s, kinds, None, (self, origin, feature))
                return
            grant = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            self.setFeaturePermission(origin, feature, grant)
        except Exception:
            pass

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame):
        url_str = url.toString()
        url_lower = url_str.lower()

        # Never block main-frame navigations - the user or the page itself is navigating.
        # Only block ad URLs in sub-frames (iframes loading ad content).
        if is_main_frame:
            self._last_url = url_str
            return True

        # Reject ad iframes only. Do NOT goBack() - a news site like index.hr
        # loads many ad frames, and going back would bounce to the previous
        # page (usually the Google homepage).
        if _is_ad_url(url_lower):
            return False

        self._last_url = url_str
        return True

    def createWindow(self, window_type):
        """Load window.open() into a real tab so window.opener stays intact.

        Do not use a separate QDialog WebEngine view - that renders black
        and breaks Google/Reddit OAuth.
        """
        if not self.browser_window:
            return None
        tab = self.browser_window._add_new_tab(url="", load_url=False)
        if not tab or not tab.web_view:
            return None
        tab.is_popup = True
        return tab.web_view.page()


# === WEB VIEW WITH CEPRKAC-STYLE CONTEXT MENU ===
class BrowserWebView(QWebEngineView):
    """QWebEngineView that adds Google Lens / reverse-image / media search entries
    to the right-click menu, using the JS-captured target (Ceprkac ContextCaptureJs)."""

    def __init__(self, browser_window=None, parent=None):
        super().__init__(parent)
        self._browser_window = browser_window

    def contextMenuEvent(self, event):
        bw = self._browser_window
        page = self.page()
        if not bw or not page:
            super().contextMenuEvent(event)
            return
        # Read the JS-captured target; native contextMenuData is often empty on
        # Discord/CDN images. runJavaScript is async, so build the menu in the callback.
        # Capture the view (self) so _build_context_menu can verify it is still live
        # before touching its page - the tab may be closed during the async gap.
        view = self
        page.runJavaScript(
            "window.__gbrowserLastCtx ? JSON.stringify(window.__gbrowserLastCtx) : 'null'",
            0,
            lambda raw: bw._build_context_menu(view, raw),
        )


# === AD ELEMENT HIDER JS (Same as Ceprkac) ===
AD_ELEMENT_HIDER_JS = r"""(function() {
    if (window.__gbrowserAdHider) return;
    window.__gbrowserAdHider = true;
    var css = document.createElement('style');
    css.textContent = [
        'ins.adsbygoogle','[id*="google_ads"]','[class*="ad-slot"]','[class*="advert"]',
        '[class*="ad-banner"]','[class*="ad-container"]','[class*="ad-wrapper"]',
        '[class*="sponsor"]','[class*="ad-placement"]','[class*="ad_"]',
        '[data-ad]','[data-adunit]','[data-ad-slot]','[data-google-query-id]',
        '.sponsored-content','.promoted','.ad-banner','.ad-container','.ad-wrapper',
        '.native-ad','.ad-unit','.ad-zone','.ad-area','.ad-block','.ad-box','.ad-frame',
        '.ad-header','.ad-footer','.ad-leaderboard','.ad-sidebar','.ad-skyscraper',
        '.ad-rectangle','.ad-interstitial','.ad-overlay','.ad-popup','.ad-modal',
        'div[id*="taboola"]','div[id*="outbrain"]','div[class*="taboola"]',
        'div[class*="outbrain"]','div[id*="zergnet"]','div[id*="revcontent"]',
        'div[id*="mgid"]','div[class*="mgid"]',
        'iframe[src*="doubleclick"]','iframe[src*="googlesyndication"]',
        'iframe[src*="googletagmanager"]','iframe[id*="google_ads"]','iframe[id*="aswift"]',
        'iframe[src*="ad"][width]','iframe[data-ad]',
        '.video-ad-overlay','.preroll-ad','.midroll-ad',
        'a[href*="doubleclick.net"]','a[href*="googleadservices"]',
        'div[aria-label="Advertisement"]','div[aria-label="advertisement"]',
        'section[aria-label="Sponsored"]',
        /* Pornhub / adult site ads */
        '.adBanner','.ad-banner','#hd-rightColAd','#pb_ad','.advertisement',
        '.mgbox','[class*="mgbox"]','div[id*="snigelAdStack"]',
        '.trafficStars','[class*="trafficStars"]','[id*="trafficStars"]',
        '[class*="exoclick"]','[id*="exoclick"]',
        'iframe[src*="trafficstars"]','iframe[src*="exoclick"]',
        'iframe[src*="trafficjunky"]','iframe[src*="adsrv"]',
        'iframe[src*="juicyads"]','iframe[src*="exosrv"]',
        'iframe[src*="tsyndicate"]','iframe[src*="realsrv"]',
        'div[class*="abovePlayer"]','div[id*="adblock"]',
        '.removeAdMessage','#removeAdblockContainer',
        /* DuckDuckGo sponsored results and self-promo */
        '.result--ad','.is-ad','[data-testid="ad"]','[data-testid="result--ad"]',
        '.badge--ad','.result__extras__url--ad',
        '.ddg-extension-hide','.js-sidebar-ads','.sidebar-modules--ads',
        '.header-aside',
        /* Google sponsored results */
        '#tads','#tadsb','#bottomads','.commercial-unit-desktop-top',
        '.commercial-unit-desktop-rhs','.cu-container',
        'div[data-text-ad]','div[data-hveid] .uEierd',
        /* Bing sponsored results */
        '.b_ad','.b_adSlug','li.b_ad','#b_results > .b_ad',
        /* Yahoo sponsored results */
        '.searchCenterTopAds','.searchCenterBottomAds','.compDlink',
        /* Reddit promoted posts (GSecurity Ad Shield) */
        'shreddit-ad-post','[data-testid="ad-post"]','[data-testid="promoted-post"]',
        'div[data-promoted="true"]','.promotedlink','.sponsorshipbox','.sponsor-logo',
        'faceplate-tracker[source="ad"]','faceplate-tracker[noun="ad"]',
        '[data-testid="sidebar-ad"]','[data-testid="subreddit-sidebar-ad"]',
        '.sidebar-ad','div[class*="promotedlink"]','.premium-banner-outer',
        '[data-testid="premium-upsell"]',
        'shreddit-experience-tree[bundlename*="ad"]','shreddit-experience-tree[bundlename*="Ad"]',
        '.thing.promoted','.thing.stickied.promotedlink',
        /* LinkedIn ads */
        '[data-ad-banner-id]','[data-is-sponsored="true"]',
        '.ad-banner-container','.ads-container',
        /* Twitch ads */
        '[data-a-target="video-ad-label"]','.video-ad','.advertisement-banner',
        '[data-test-selector="ad-banner-default-id"]','.stream-display-ad',
        /* TikTok ads */
        '[class*="DivAdBanner"]','[data-e2e="ad"]',
        /* Croatian news portals (24sata, index.hr, ...) */
        'div[id^="div-gpt-ad"]','div[id^="google_ads_"]','div[id*="gpt-ad"]',
        '.dfp-ad','.dfp_ad','.gpt-ad','.adSlot','.ad-slot','.AdSlot',
        '.reklama','.oglas','[class*="Reklama"]','[id*="reklama"]',
        '.js-ad','.js-ads','.js-gpt-ad','[data-ad-unit]','[data-google-query-id]',
        '#billboard','.billboard-ad','.banner-holder','.bannerHolder',
        'iframe[id^="google_ads"]','iframe[src*="adform"]','iframe[src*="gemius"]',
        'iframe[src*="adtrafficquality"]'
    ].join(',') + '{display:none!important;height:0!important;min-height:0!important;overflow:hidden!important}';
    (document.head || document.documentElement).appendChild(css);
    var sels = [
        'ins.adsbygoogle','iframe[src*="doubleclick"]','iframe[src*="googlesyndication"]',
        'iframe[src*="googletagmanager"]','iframe[id*="google_ads"]','iframe[id*="aswift"]',
        '[id*="google_ads"]','[class*="ad-slot"]','[class*="advert"]','[class*="ad-banner"]',
        '[class*="ad-container"]','[class*="ad-wrapper"]','[class*="sponsor"]',
        '[data-ad]','[data-adunit]','[data-ad-slot]','[data-google-query-id]',
        '.sponsored-content','.promoted','.ad-banner','.ad-container','.ad-wrapper',
        '.native-ad','.ad-unit','.ad-zone','.ad-area','.ad-block','.ad-box','.ad-frame',
        'div[id*="taboola"]','div[id*="outbrain"]','div[class*="taboola"]',
        'div[class*="outbrain"]','div[id*="zergnet"]','div[id*="revcontent"]',
        'div[id*="mgid"]','div[class*="mgid"]',
        '.video-ad-overlay','.preroll-ad','.midroll-ad',
        'div[aria-label="Advertisement"]','div[aria-label="advertisement"]',
        /* Search engine sponsored results */
        '.result--ad','.is-ad','[data-testid="ad"]','[data-testid="result--ad"]',
        '.badge--ad','.ddg-extension-hide','.js-sidebar-ads','.header-aside',
        '#tads','#tadsb','#bottomads','.commercial-unit-desktop-top',
        '.commercial-unit-desktop-rhs','div[data-text-ad]',
        '.b_ad','.b_adSlug','li.b_ad',
        '.searchCenterTopAds','.searchCenterBottomAds',
        /* Reddit (GSecurity Ad Shield) */
        'shreddit-ad-post','[data-testid="ad-post"]','[data-testid="promoted-post"]',
        'div[data-promoted="true"]','.promotedlink','.sponsorshipbox','.sponsor-logo',
        '#ad-frame','#ad_main',
        'faceplate-tracker[source="ad"]','faceplate-tracker[noun="ad"]',
        '[data-testid="sidebar-ad"]','[data-testid="subreddit-sidebar-ad"]',
        'shreddit-experience-tree[bundlename*="ad"]','shreddit-experience-tree[bundlename*="Ad"]',
        '.premium-banner-outer','[data-testid="premium-upsell"]',
        /* LinkedIn */
        '[data-ad-banner-id]','[data-is-sponsored="true"]',
        '.ad-banner-container','.ads-container',
        /* Twitch */
        '[data-a-target="video-ad-label"]','.video-ad','.advertisement-banner',
        '[data-test-selector="ad-banner-default-id"]','.stream-display-ad',
        /* TikTok */
        '[class*="DivAdBanner"]','[data-e2e="ad"]',
        /* Croatian news portals */
        'div[id^="div-gpt-ad"]','div[id^="google_ads_"]','div[id*="gpt-ad"]',
        '.dfp-ad','.dfp_ad','.gpt-ad','.adSlot','.AdSlot',
        '.reklama','.oglas','[class*="Reklama"]','[id*="reklama"]',
        '.js-ad','.js-ads','.js-gpt-ad','[data-ad-unit]',
        '#billboard','.billboard-ad','.banner-holder','.bannerHolder',
        'iframe[src*="adform"]','iframe[src*="gemius"]','iframe[src*="adtrafficquality"]'
    ];
    function scrub() {
        for (var i = 0; i < sels.length; i++) {
            try {
                var els = document.querySelectorAll(sels[i]);
                for (var j = 0; j < els.length; j++) {
                    if (els[j] && els[j].parentElement) els[j].remove();
                }
            } catch(e) {}
        }
        try {
            document.querySelectorAll('article, [data-testid="post-container"], .thing').forEach(function(post) {
                var badges = post.querySelectorAll('span, faceplate-tracker, [slot="credit-bar"], .tagline');
                for (var k = 0; k < badges.length; k++) {
                    var text = (badges[k].textContent || '').trim().toLowerCase();
                    if (text === 'promoted' || text === 'sponsored') { post.remove(); break; }
                }
            });
            document.querySelectorAll('shreddit-post').forEach(function(post) {
                if (post.hasAttribute('is-promoted') || post.getAttribute('post-type') === 'promoted') post.remove();
            });
        } catch(e) {}
        try {
            document.querySelectorAll('div[role="article"], div[role="feed"] > div').forEach(function(article) {
                var spans = article.querySelectorAll('span');
                for (var k = 0; k < spans.length; k++) {
                    if ((spans[k].textContent || '').trim().toLowerCase() === 'sponsored') {
                        article.style.display = 'none'; break;
                    }
                }
            });
        } catch(e) {}
        try {
            document.querySelectorAll('article, [data-testid="placementTracking"]').forEach(function(el) {
                var text = (el.textContent || '').toLowerCase();
                if (/\bpromoted\b/.test(text) || /\bad\s*-/.test(text) || el.matches('[data-testid="placementTracking"]')) {
                    el.style.display = 'none';
                }
            });
        } catch(e) {}
        try {
            document.querySelectorAll('article').forEach(function(a) {
                if (/\bsponsored\b/i.test(a.textContent || '')) a.style.display = 'none';
            });
        } catch(e) {}
    }
    scrub();
    setInterval(scrub, 1500);
    new MutationObserver(scrub).observe(document.documentElement, {childList:true, subtree:true});
})()"""

YOUTUBE_AD_BLOCKER_JS = r"""(function() {
    if (window.__gbrowserYtAdBlock) return;
    window.__gbrowserYtAdBlock = true;
    var s = document.createElement('style');
    s.textContent = 'ytd-display-ad-renderer,ytd-ad-slot-renderer,ytd-promoted-video-renderer,ytd-promoted-sparkles-web-renderer,ytd-promoted-sparkles-text-search-renderer,ytd-banner-promo-renderer,ytd-statement-banner-renderer,ytd-in-feed-ad-layout-renderer,ytd-masthead-ad-renderer,ytd-primetime-promo-renderer,ytd-compact-promoted-video-renderer,ytd-action-companion-ad-renderer,ytd-mealbar-promo-renderer,ytd-enforcement-message-view-model,ytd-engagement-panel-section-list-renderer[target-id=engagement-panel-ads],#masthead-ad,#player-ads,.video-ads,.ytp-ad-module,.ytp-ad-overlay-container,.ytp-ad-player-overlay,.ytp-ad-action-interstitial,.ytp-ad-image-overlay,.ytp-ad-text-overlay,.ytp-ad-skip-ad-slot,.ad-showing .ytp-ad-module,ytd-search-pyv-renderer,ytd-movie-offer-module-renderer,tp-yt-paper-dialog:has(#dismiss-button),ytd-popup-container:has(a[href*="/premium"]),ytd-rich-item-renderer:has(ytd-ad-slot-renderer),ytd-rich-item-renderer:has(ytd-display-ad-renderer),ytd-rich-item-renderer:has(ytd-promoted-video-renderer),ytd-rich-item-renderer:has(ytd-promoted-sparkles-web-renderer),ytd-rich-section-renderer:has(ytd-ad-slot-renderer){display:none!important}';
    (document.head||document.documentElement).appendChild(s);
    var adKeys=['adPlacements','adSlots','playerAds','adBreakHeartbeatParams','ad3Module','adSafetyReason','adLoggingData','showAdSlots','adBreakParams','adBreakStatus','adVideoId','adLayoutLoggingData','instreamAdPlayerOverlayRenderer','adPlacementConfig','adVideoStitcherConfig','promotedSparklesWebRenderer','promotedSparklesTextSearchRenderer','promotedVideoRenderer','sponsoredCardRenderer','adSlotRenderer','displayAdRenderer','inFeedAdLayoutRenderer','mastheadAdRenderer','compactPromotedVideoRenderer','actionCompanionAdRenderer','bannerPromoRenderer','statementBannerRenderer','primeTimePromoRenderer','searchPyvRenderer','movieOfferModuleRenderer','adPlacementRenderer','sparklesAdRenderer'];
    function stripAds(o,d){if(!o||typeof o!=='object'||d>12)return;for(var i=0;i<adKeys.length;i++)if(o.hasOwnProperty(adKeys[i]))delete o[adKeys[i]];var k=Object.keys(o);for(var j=0;j<k.length;j++){var key=k[j],val=o[key];if(Array.isArray(val)){for(var m=val.length-1;m>=0;m--){var item=val[m];if(item&&typeof item==='object'){var ik=Object.keys(item);for(var n=0;n<ik.length;n++){if(/^(ad|promoted|sponsor)/i.test(ik[n])){val.splice(m,1);break;}}}}}else if(val&&typeof val==='object')stripAds(val,d+1);}}
    var op=JSON.parse;JSON.parse=function(){var r=op.apply(this,arguments);try{if(r&&typeof r==='object')stripAds(r,0);}catch(e){}return r;};
    ['ytInitialPlayerResponse','ytInitialData','ytcfg'].forEach(function(p){var v=window[p];try{Object.defineProperty(window,p,{configurable:true,get:function(){return v;},set:function(n){if(n&&typeof n==='object')stripAds(n,0);v=n;}});if(v)window[p]=v;}catch(e){}});
    var adS=['.video-ads','.ytp-ad-module','.ytp-ad-overlay-container','.ytp-ad-player-overlay','.ytp-ad-action-interstitial','.ytp-ad-image-overlay','.ytp-ad-text-overlay','#player-ads','#masthead-ad','ytd-display-ad-renderer','ytd-ad-slot-renderer','ytd-promoted-video-renderer','ytd-promoted-sparkles-web-renderer','ytd-banner-promo-renderer','ytd-in-feed-ad-layout-renderer','ytd-mealbar-promo-renderer','ytd-enforcement-message-view-model','ytd-search-pyv-renderer','ytd-movie-offer-module-renderer','ytd-compact-promoted-video-renderer','ytd-action-companion-ad-renderer','ytd-primetime-promo-renderer','ytd-masthead-ad-renderer'];
    var skS=['.ytp-ad-skip-button','.ytp-skip-ad-button','.ytp-ad-skip-button-modern','.ytp-skip-ad-button__text','button[class*="skip"]','.ytp-ad-overlay-close-button','.ytp-ad-skip-button-slot'];
    var sponsorWords=['sponsored','sponzorirano','gesponsert','sponsoris','patrocinado','sponsorizzato','gesponsord','\u0441\u043f\u043e\u043d\u0441\u0438\u0440\u0443\u0435\u043c\u0430\u044f','\u30b9\u30dd\u30f3\u30b5\u30fc','\u8d5e\u52a9','\uad11\uace0','reklam','promowane','sponzorovan','szponzorlt','annonce','reklama','hirdets','\u0440\u0435\u043a\u043b\u0430\u043c\u0430','commandit','gesponsord','publicidad','pubblicit','anncio','reklame','sponzorovno','sponzorirane','\u0441\u043f\u043e\u043d\u0437\u043e\u0440\u0438\u0440\u0430\u043d\u043e'];
    function isSponsoredText(t){t=t.trim().toLowerCase();for(var i=0;i<sponsorWords.length;i++){if(t===sponsorWords[i])return true;}return false;}
    function scrub(){for(var i=0;i<adS.length;i++)document.querySelectorAll(adS[i]).forEach(function(e){var p=e.closest('ytd-rich-item-renderer,ytd-rich-section-renderer,ytd-reel-shelf-renderer');if(p)p.remove();else e.remove();});for(var j=0;j<skS.length;j++)document.querySelectorAll(skS[j]).forEach(function(b){if(b.click)b.click();});try{document.querySelectorAll('ytd-rich-item-renderer,ytd-rich-section-renderer').forEach(function(item){if(item.querySelector('ytd-ad-slot-renderer,ytd-display-ad-renderer,ytd-promoted-video-renderer,ytd-promoted-sparkles-web-renderer,ytd-in-feed-ad-layout-renderer')){item.remove();return;}var badges=item.querySelectorAll('span.ytd-badge-supported-renderer,ytd-badge-supported-renderer span,div.ytd-badge-supported-renderer,ytd-badge-supported-renderer,[class*="badge"],.badge,.badge-style-type-ad,span[aria-label]');for(var k=0;k<badges.length;k++){if(isSponsoredText(badges[k].textContent||'')){item.remove();return;}}var metas=item.querySelectorAll('#metadata-line span,#byline-container span,yt-formatted-string.ytd-channel-name');for(var m=0;m<metas.length;m++){if(isSponsoredText(metas[m].textContent||'')){item.remove();return;}}});}catch(e){}try{document.querySelectorAll('ytd-video-renderer,ytd-compact-video-renderer').forEach(function(item){var badges=item.querySelectorAll('span.ytd-badge-supported-renderer,ytd-badge-supported-renderer span,[class*="badge"]');for(var k=0;k<badges.length;k++){if(isSponsoredText(badges[k].textContent||'')){item.remove();return;}}});}catch(e){}var p=document.querySelector('.html5-video-player'),v=document.querySelector('video');if(p&&v&&(p.classList.contains('ad-showing')||p.classList.contains('ad-interrupting'))){if(Number.isFinite(v.duration)&&v.duration>0){v.currentTime=Math.max(0,v.duration-0.1);}v.muted=true;v.playbackRate=16;try{v.play();}catch(e){}p.classList.remove('ad-showing');p.classList.remove('ad-interrupting');p.classList.remove('ad-created');document.querySelectorAll('.ytp-ad-skip-button,.ytp-skip-ad-button,.ytp-ad-skip-button-modern').forEach(function(b){b.click();});setTimeout(function(){v.muted=false;v.playbackRate=1;},500);}document.querySelectorAll('ytd-rich-item-renderer').forEach(function(el){var hasAd=!!el.querySelector('ytd-ad-slot-renderer,ytd-display-ad-renderer,ytd-promoted-video-renderer,ytd-promoted-sparkles-web-renderer');if(hasAd){el.remove();return;}});document.querySelectorAll('tp-yt-paper-dialog').forEach(function(d){var t=(d.textContent||'').toLowerCase();if(t.includes('ad blocker')||t.includes('allow ads')){var b=d.querySelector('#dismiss-button,.dismiss-button,button');if(b&&b.click)b.click();d.remove();}});}
    scrub();setInterval(scrub,200);new MutationObserver(scrub).observe(document.documentElement,{childList:true,subtree:true});
})()"""

# YouTube main-world ad blocker - injected via <script> tag to run in main world
# before any page scripts. Intercepts JSON.parse, ytInitialData, fetch responses.
# Ported from Ceprkac's BuildYouTubeMainWorldCode().
YOUTUBE_MAIN_WORLD_JS = (
    "(function(){"
    "var h=location.hostname.toLowerCase();"
    "if(h!=='youtube.com'&&h!=='www.youtube.com'&&h!=='m.youtube.com'&&h!=='music.youtube.com'&&!h.endsWith('.youtube.com'))return;"
    "if(/accounts\\.google|login\\.microsoft|appleid\\.apple|auth0\\.com|clerk\\.|oauth/.test(h))return;"
    "if(window.__gbrowserYtMain)return;window.__gbrowserYtMain=true;"
    "var adKeys=['adPlacements','adSlots','playerAds','adBreakHeartbeatParams','ad3Module',"
    "'adSafetyReason','adLoggingData','showAdSlots','adBreakParams','adBreakStatus',"
    "'adVideoId','adLayoutLoggingData','instreamAdPlayerOverlayRenderer',"
    "'adPlacementConfig','adVideoStitcherConfig',"
    "'promotedSparklesWebRenderer','promotedSparklesTextSearchRenderer',"
    "'promotedVideoRenderer','sponsoredCardRenderer','adSlotRenderer',"
    "'displayAdRenderer','inFeedAdLayoutRenderer','mastheadAdRenderer',"
    "'compactPromotedVideoRenderer','actionCompanionAdRenderer',"
    "'bannerPromoRenderer','statementBannerRenderer','primeTimePromoRenderer',"
    "'searchPyvRenderer','movieOfferModuleRenderer','adPlacementRenderer','sparklesAdRenderer'];"
    "function strip(o,d){if(!o||typeof o!=='object'||d>15)return;"
    "for(var i=0;i<adKeys.length;i++)if(o.hasOwnProperty(adKeys[i]))delete o[adKeys[i]];"
    "var k=Object.keys(o);for(var j=0;j<k.length;j++){"
    "var key=k[j],val=o[key];"
    "if(Array.isArray(val)){for(var m=val.length-1;m>=0;m--){"
    "var item=val[m];if(item&&typeof item==='object'){"
    "var ik=Object.keys(item);var isAd=false;"
    "for(var n=0;n<ik.length;n++){"
    "if(/^(ad|promoted|sponsor)/i.test(ik[n])){isAd=true;break;}}"
    "if(!isAd&&item.richItemRenderer&&item.richItemRenderer.content){"
    "var ck=Object.keys(item.richItemRenderer.content);"
    "for(var c=0;c<ck.length;c++){if(/^(ad|promoted|sponsor)/i.test(ck[c])){isAd=true;break;}}}"
    "if(!isAd){try{var js=JSON.stringify(item);"
    "if(/\"style\":\"BADGE_STYLE_TYPE_AD\"/.test(js)||"
    "/\"label\":\"(?:Sponsored|Sponzorirano|Gesponsert|Sponsoris\\u00e9|Patrocinado|Sponsorizzato|Gesponsord|\\u0420\\u0435\\u043a\\u043b\\u0430\\u043c\\u0430|\\u30b9\\u30dd\\u30f3\\u30b5\\u30fc|\\u8d5e\\u52a9|\\uad11\\uace0|Reklam|Promowane|Sponzorovan\\u00e9|Szponzor\\u00e1lt|Annonce|Reklama|Hirdet\\u00e9s|Commandit\\u00e9|Publicidad|Pubblicit\\u00e0|An\\u00fancio|Reklame|Sponzorirane|\\u0421\\u043f\\u043e\\u043d\\u0437\\u043e\\u0440\\u0438\\u0440\\u0430\\u043d\\u043e)\"/.test(js))"
    "{isAd=true;}}catch(e){}}"
    "if(isAd){val.splice(m,1);}"
    "else{strip(item,d+1);}"
    "}}"
    "}else if(val&&typeof val==='object')strip(val,d+1);}}"
    "var op=JSON.parse;JSON.parse=function(){var r=op.apply(this,arguments);"
    "try{if(r&&typeof r==='object')strip(r,0);}catch(e){}return r;};"
    "['ytInitialPlayerResponse','ytInitialData'].forEach(function(p){var v=window[p];"
    "try{Object.defineProperty(window,p,{configurable:true,"
    "get:function(){return v;},set:function(n){if(n&&typeof n==='object')strip(n,0);v=n;}});"
    "if(v)window[p]=v;}catch(e){}});"
    "var oFetch=window.fetch;window.fetch=function(){var args=arguments;"
    "var url=typeof args[0]==='string'?args[0]:(args[0]&&args[0].url?args[0].url:'');"
    "if(!/youtubei\\/v1\\/(browse|search|next|player|reel)/.test(url))return oFetch.apply(this,args);"
    "return oFetch.apply(this,args).then(function(resp){"
    "if(!resp||!resp.ok)return resp;"
    "return resp.clone().text().then(function(txt){"
    "try{var data=op.call(JSON,txt);strip(data,0);"
    "return new Response(JSON.stringify(data),{status:resp.status,statusText:resp.statusText,headers:resp.headers});"
    "}catch(e){return resp;}});});};"
    "})()"
)

# Wrapper that injects YOUTUBE_MAIN_WORLD_JS via <script> tag into the main world
YOUTUBE_MAIN_WORLD_INJECTOR_JS = (
    "(function(){if(location.hostname.indexOf('youtube')===-1)return;"
    "var sc=document.createElement('script');"
    "sc.textContent='" + YOUTUBE_MAIN_WORLD_JS.replace("\\", "\\\\").replace("'", "\\'") + "';"
    "(document.head||document.documentElement).appendChild(sc);sc.remove();})()"
)

CHECK_LOGIN_FIELDS_JS = r"""(function() {
    var pw = document.querySelector('input[type="password"]');
    var emailOrUser = document.querySelector(
        'input[type="email"], input[type="tel"], input[name="email"], input[name="username"], ' +
        'input[name="login"], input[name="user"], input[autocomplete="username"], ' +
        'input[autocomplete="email"], input[aria-label*="mail" i], input[aria-label*="user" i], ' +
        'input[aria-label*="phone" i], input[aria-label*="login" i], input[aria-label*="Email"], ' +
        'input[aria-label*="Phone"]'
    );
    if (!emailOrUser) {
        var all = document.querySelectorAll('input[type="text"], input:not([type])');
        for (var i = 0; i < all.length; i++) {
            if (all[i].offsetParent !== null && all[i].offsetWidth > 0) { emailOrUser = all[i]; break; }
        }
    }
    if (pw && emailOrUser) return 'both';
    if (pw) return 'pwonly';
    if (emailOrUser) return 'useronly';
    return 'none';
})()"""


def _make_fill_js(username: str, password: str) -> str:
    esc_u = json.dumps(username)
    esc_p = json.dumps(password)
    return f"""(function(){{
    var u={esc_u}, p={esc_p};
    var pw = document.querySelector('input[type="password"]');
    if (!pw) return;
    var form = pw.closest('form') || document.body;
    var user = form.querySelector([
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[name="login"]',
        'input[name="user"]',
        'input[autocomplete="username"]',
        'input[autocomplete="email"]',
        'input[type="text"][name*="user"]',
        'input[type="text"][name*="login"]',
        'input[type="text"][name*="email"]',
        'input[type="text"][autocomplete*="user"]',
        'input[aria-label*="mail"]',
        'input[aria-label*="user"]',
        'input[aria-label*="login"]',
        'input[aria-label*="phone"]'
    ].join(', '));
    if (!user) {{
        var inputs = form.querySelectorAll('input[type="text"], input[type="email"], input:not([type])');
        for (var i = 0; i < inputs.length; i++) {{
            var inp = inputs[i];
            if (inp !== pw && inp.offsetParent !== null) {{ user = inp; break; }}
        }}
    }}
    if (user) {{
        var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSet.call(user, u);
        user.dispatchEvent(new Event('input', {{bubbles:true}}));
        user.dispatchEvent(new Event('change', {{bubbles:true}}));
    }}
    var nativeSet2 = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeSet2.call(pw, p);
    pw.dispatchEvent(new Event('input', {{bubbles:true}}));
    pw.dispatchEvent(new Event('change', {{bubbles:true}}));
}})()"""


def _make_fill_password_js(password: str) -> str:
    """Fill ONLY the visible password field (Ceprkac FillPasswordOnly). Password-only
    steps (Google's /signin/.../pwd, re-auth prompts) carry a hidden username input the
    site populates itself; writing to it can break the flow."""
    esc_p = json.dumps(password)
    return f"""(function(){{
    var p={esc_p};
    var pws = document.querySelectorAll('input[type="password"]');
    var pw = null;
    for (var i = 0; i < pws.length; i++) {{
        if (pws[i].offsetParent !== null && pws[i].offsetWidth > 0) {{ pw = pws[i]; break; }}
    }}
    if (!pw && pws.length) pw = pws[0];
    if (!pw) return;
    var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeSet.call(pw, p);
    pw.dispatchEvent(new Event('input', {{bubbles:true}}));
    pw.dispatchEvent(new Event('change', {{bubbles:true}}));
    pw.dispatchEvent(new Event('blur', {{bubbles:true}}));
}})()"""


def _make_fill_username_js(username: str) -> str:
    esc_u = json.dumps(username)
    return f"""(function(){{
    var u={esc_u};
    var user = document.querySelector(
        'input[type="email"], input[type="tel"], input[name="email"], input[name="username"], ' +
        'input[name="login"], input[name="user"], input[autocomplete="username"], ' +
        'input[autocomplete="email"], input[aria-label*="mail" i], input[aria-label*="user" i], ' +
        'input[aria-label*="phone" i], input[aria-label*="login" i], input[aria-label*="Email"], ' +
        'input[aria-label*="Phone"]'
    );
    if (!user) {{
        var all = document.querySelectorAll('input[type="text"], input:not([type])');
        for (var i = 0; i < all.length; i++) {{
            if (all[i].offsetParent !== null && all[i].offsetWidth > 0) {{ user = all[i]; break; }}
        }}
    }}
    if (user) {{
        var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSet.call(user, u);
        user.dispatchEvent(new Event('input', {{bubbles:true}}));
        user.dispatchEvent(new Event('change', {{bubbles:true}}));
        user.dispatchEvent(new Event('blur', {{bubbles:true}}));
    }}
}})()"""


# === DOWNLOAD ITEM TRACKER ===
class DownloadItem:
    def __init__(self, filename: str, path: str = "", url: str = ""):
        self.filename = filename
        self.path = path
        self.url = url
        self.received = 0
        self.total = 0
        self.status = "Downloading"
        self._request = None  # keep QWebEngineDownloadRequest alive
        self._finalized = False

    def to_dict(self) -> dict:
        return {
            "filename": self.filename, "path": self.path, "url": self.url,
            "received": self.received, "total": self.total, "status": self.status,
        }

    @staticmethod
    def from_dict(d: dict) -> "DownloadItem":
        item = DownloadItem(d.get("filename", ""), d.get("path", ""), d.get("url", ""))
        item.received = int(d.get("received") or 0)
        item.total = int(d.get("total") or 0)
        item.status = d.get("status") or "Complete"
        return item


def _format_bytes(n: int) -> str:
    n = max(0, int(n or 0))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f" {n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _open_local_path(path: str, select: bool = False) -> None:
    if not path:
        return
    try:
        if select and os.path.exists(path):
            os.startfile(os.path.dirname(path))
        elif os.path.isdir(path):
            os.startfile(path)
        elif os.path.exists(path):
            os.startfile(path)
        elif os.path.dirname(path):
            os.startfile(os.path.dirname(path))
    except Exception:
        pass


def _load_downloads() -> list[DownloadItem]:
    try:
        with open(DOWNLOADS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [DownloadItem.from_dict(d) for d in data if isinstance(d, dict)][-40:]
    except Exception:
        return []


def _save_downloads(items: list[DownloadItem]) -> None:
    try:
        done = [i for i in items if i.status != "Downloading"][-40:]
        with open(DOWNLOADS_FILE, "w", encoding="utf-8") as f:
            json.dump([i.to_dict() for i in done], f, indent=2)
    except Exception:
        pass


# === HISTORY DIALOG ===
class HistoryDialog(QDialog):
    """Simple dialog showing last 100 history URLs."""
    def __init__(self, history: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browsing History")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(
            f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}")
        self._selected_url: str = ""
        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: rgb({Theme.TitleBar.red()},{Theme.TitleBar.green()},{Theme.TitleBar.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); }}"
            f"QListWidget::item:selected {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()}); color: black; }}")
        for url in reversed(history[-100:]):
            self._list.addItem(url)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.CloseHover.red()},{Theme.CloseHover.green()},{Theme.CloseHover.blue()});"
            f"color: white; border: none; border-radius: 4px; padding: 6px 16px; }}")
        clear_btn.clicked.connect(lambda: self.done(2))  # code 2 = clear
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
            f"color: black; border: none; border-radius: 4px; padding: 6px 16px; }}")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_item_double_clicked(self, item):
        self._selected_url = item.text()
        self.accept()

    def selected_url(self) -> str:
        return self._selected_url


# === DOWNLOAD MANAGER DIALOG ===
class DownloadManagerDialog(QDialog):
    """Dialog showing recent downloads with progress."""
    def __init__(self, downloads: list[DownloadItem], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloads")
        self.setMinimumSize(500, 350)
        self.setStyleSheet(
            f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}")
        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: rgb({Theme.TitleBar.red()},{Theme.TitleBar.green()},{Theme.TitleBar.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); }}")
        for dl in reversed(downloads):
            if dl.total > 0:
                pct = int(dl.received * 100 / dl.total)
                text = f"{dl.filename}  -  {pct}%  ({dl.status})"
            else:
                text = f"{dl.filename}  -  {dl.received} bytes  ({dl.status})"
            self._list.addItem(text)
        layout.addWidget(self._list, 1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
            f"color: black; border: none; border-radius: 4px; padding: 6px 16px; }}")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class CredentialEditDialog(QDialog):
    """Add / edit a single saved credential (URL, username, password)."""

    def __init__(self, cred: SavedCredential | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Password" if cred else "Add Password")
        self.setMinimumWidth(380)
        self.setStyleSheet(
            f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}"
            f"QLabel {{ color: white; }}"
            f"QLineEdit {{ background: rgb({Theme.AddressBox.red()},{Theme.AddressBox.green()},{Theme.AddressBox.blue()});"
            f" color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()});"
            f" border-radius: 4px; padding: 4px 8px; }}")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Site URL"))
        self._url = QLineEdit(cred.url if cred else "")
        layout.addWidget(self._url)
        layout.addWidget(QLabel("Username / Email"))
        self._user = QLineEdit(cred.username if cred else "")
        layout.addWidget(self._user)
        layout.addWidget(QLabel("Password"))
        self._pwd = QLineEdit(cred.password if cred else "")
        self._pwd.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._pwd)
        show = QCheckBox("Show password")
        show.setStyleSheet("color: white;")
        show.toggled.connect(lambda on: self._pwd.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        layout.addWidget(show)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Save")
        ok.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
            f" color: black; border: none; border-radius: 4px; padding: 6px 16px; }}")
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def result_credential(self) -> SavedCredential:
        return SavedCredential(self._url.text().strip(),
                               self._user.text().strip(),
                               self._pwd.text())


class CredentialManagerDialog(QDialog):
    """Manage Passwords: list / add / edit / delete saved credentials."""

    def __init__(self, manager: "PasswordManager", parent=None):
        super().__init__(parent)
        self._manager = manager
        self.setWindowTitle("Manage Passwords")
        self.setMinimumSize(560, 400)
        self.setStyleSheet(
            f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}")
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: rgb({Theme.TitleBar.red()},{Theme.TitleBar.green()},{Theme.TitleBar.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); }}"
            f"QListWidget::item:selected {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()}); color: black; }}")
        self._list.itemDoubleClicked.connect(lambda _i: self._edit())
        layout.addWidget(self._list, 1)
        row = QHBoxLayout()
        btn_style = (f"QPushButton {{ background: rgb({Theme.Toolbar.red()},{Theme.Toolbar.green()},{Theme.Toolbar.blue()});"
                     f"color: white; border: none; border-radius: 4px; padding: 6px 14px; }}"
                     f"QPushButton:hover {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
        for label, slot in (("Add", self._add), ("Edit", self._edit), ("Delete", self._delete)):
            b = QPushButton(label)
            b.setStyleSheet(btn_style)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
            f" color: black; border: none; border-radius: 4px; padding: 6px 16px; }}")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self._reload()

    def _reload(self):
        self._list.clear()
        for c in self._manager.passwords:
            host = c.url
            try:
                host = urlparse(c.url).hostname or c.url
            except Exception:
                pass
            self._list.addItem(f"{host}  -  {c.username}")

    def _add(self):
        dlg = CredentialEditDialog(None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            c = dlg.result_credential()
            if c.url and c.username:
                self._manager.passwords.append(c)
                self._manager.save()
                self._reload()

    def _edit(self):
        idx = self._list.currentRow()
        if not (0 <= idx < len(self._manager.passwords)):
            return
        cred = self._manager.passwords[idx]
        dlg = CredentialEditDialog(cred, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.result_credential()
            cred.url, cred.username, cred.password = new.url, new.username, new.password
            self._manager.save()
            self._reload()

    def _delete(self):
        idx = self._list.currentRow()
        if not (0 <= idx < len(self._manager.passwords)):
            return
        del self._manager.passwords[idx]
        self._manager.save()
        self._reload()


def _dialog_style() -> str:
    return (
        f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}"
        f"QLabel {{ color: white; }}"
        f"QLineEdit {{ background: rgb({Theme.AddressBox.red()},{Theme.AddressBox.green()},{Theme.AddressBox.blue()});"
        f" color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()});"
        f" border-radius: 4px; padding: 4px 8px; }}"
    )


def _accent_button(label: str) -> QPushButton:
    b = QPushButton(label)
    b.setStyleSheet(
        f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
        f" color: black; border: none; border-radius: 4px; padding: 6px 16px; }}")
    return b


class CardEditDialog(QDialog):
    def __init__(self, card: SavedCard | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Card" if card else "Add Card")
        self.setMinimumWidth(380)
        self.setStyleSheet(_dialog_style())
        layout = QVBoxLayout(self)
        self._fields = {}
        for key, lbl, val in (
            ("label", "Nickname", card.label if card else ""),
            ("name", "Cardholder name", card.name if card else ""),
            ("number", "Card number", card.number if card else ""),
            ("exp_month", "Expiry month (MM)", card.exp_month if card else ""),
            ("exp_year", "Expiry year (YYYY)", card.exp_year if card else ""),
            ("cvc", "CVC", card.cvc if card else ""),
        ):
            layout.addWidget(QLabel(lbl))
            edit = QLineEdit(val)
            self._fields[key] = edit
            layout.addWidget(edit)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = _accent_button("Save")
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _on_ok(self):
        num = re.sub(r"\D", "", self._fields["number"].text())
        if len(num) < 12:
            QMessageBox.warning(self, "GBrowser", "Enter a valid card number (12+ digits).")
            return
        self.accept()

    def result_card(self) -> SavedCard:
        f = self._fields
        return SavedCard(f["label"].text().strip(), f["name"].text().strip(),
                         f["number"].text().strip(), f["exp_month"].text().strip(),
                         f["exp_year"].text().strip(), f["cvc"].text().strip())


class AddressEditDialog(QDialog):
    def __init__(self, addr: SavedAddress | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Address" if addr else "Add Address")
        self.setMinimumWidth(400)
        self.setStyleSheet(_dialog_style())
        layout = QVBoxLayout(self)
        self._fields = {}
        for key, lbl in (
            ("label", "Nickname"), ("full_name", "Full name"), ("email", "Email"),
            ("phone", "Phone"), ("line1", "Address line 1"), ("line2", "Address line 2"),
            ("city", "City"), ("state", "State / Region"), ("postal_code", "Postal code"),
            ("country", "Country"),
        ):
            layout.addWidget(QLabel(lbl))
            edit = QLineEdit(getattr(addr, key) if addr else "")
            self._fields[key] = edit
            layout.addWidget(edit)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = _accent_button("Save")
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def result_address(self) -> SavedAddress:
        f = self._fields
        return SavedAddress(f["label"].text().strip(), f["full_name"].text().strip(),
                            f["email"].text().strip(), f["phone"].text().strip(),
                            f["line1"].text().strip(), f["line2"].text().strip(),
                            f["city"].text().strip(), f["state"].text().strip(),
                            f["postal_code"].text().strip(), f["country"].text().strip())


class _ListManagerDialog(QDialog):
    """Shared list + Add/Edit/Delete UI for cards and addresses."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 400)
        self.setStyleSheet(
            f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}")
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: rgb({Theme.TitleBar.red()},{Theme.TitleBar.green()},{Theme.TitleBar.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); }}"
            f"QListWidget::item:selected {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()}); color: black; }}")
        self._list.itemDoubleClicked.connect(lambda _i: self._edit())
        layout.addWidget(self._list, 1)
        row = QHBoxLayout()
        btn_style = (f"QPushButton {{ background: rgb({Theme.Toolbar.red()},{Theme.Toolbar.green()},{Theme.Toolbar.blue()});"
                     f"color: white; border: none; border-radius: 4px; padding: 6px 14px; }}"
                     f"QPushButton:hover {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
        for label, slot in (("Add", self._add), ("Edit", self._edit), ("Delete", self._delete)):
            b = QPushButton(label)
            b.setStyleSheet(btn_style)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        close = _accent_button("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    # Subclasses implement these.
    def _items(self) -> list: raise NotImplementedError
    def _display(self, item) -> str: raise NotImplementedError
    def _add(self): raise NotImplementedError
    def _edit(self): raise NotImplementedError
    def _delete(self): raise NotImplementedError

    def _reload(self):
        self._list.clear()
        for it in self._items():
            self._list.addItem(self._display(it))


class CardManagerDialog(_ListManagerDialog):
    def __init__(self, manager: "CardManager", parent=None):
        self._manager = manager
        super().__init__("Payment Methods", parent)
        self._reload()

    def _items(self): return self._manager.cards
    def _display(self, item): return item.display

    def _add(self):
        dlg = CardEditDialog(None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._manager.cards.append(dlg.result_card())
            self._manager.save()
            self._reload()

    def _edit(self):
        idx = self._list.currentRow()
        if not (0 <= idx < len(self._manager.cards)):
            return
        dlg = CardEditDialog(self._manager.cards[idx], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._manager.cards[idx] = dlg.result_card()
            self._manager.save()
            self._reload()

    def _delete(self):
        idx = self._list.currentRow()
        if not (0 <= idx < len(self._manager.cards)):
            return
        del self._manager.cards[idx]
        self._manager.save()
        self._reload()


class AddressManagerDialog(_ListManagerDialog):
    def __init__(self, manager: "AddressManager", parent=None):
        self._manager = manager
        super().__init__("Addresses", parent)
        self._reload()

    def _items(self): return self._manager.addresses
    def _display(self, item): return item.display

    def _add(self):
        dlg = AddressEditDialog(None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._manager.addresses.append(dlg.result_address())
            self._manager.save()
            self._reload()

    def _edit(self):
        idx = self._list.currentRow()
        if not (0 <= idx < len(self._manager.addresses)):
            return
        dlg = AddressEditDialog(self._manager.addresses[idx], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._manager.addresses[idx] = dlg.result_address()
            self._manager.save()
            self._reload()

    def _delete(self):
        idx = self._list.currentRow()
        if not (0 <= idx < len(self._manager.addresses)):
            return
        del self._manager.addresses[idx]
        self._manager.save()
        self._reload()


class DownloadsPopup(QFrame):
    """Dropdown list of downloads with live progress bars."""

    def __init__(self, browser: "Browser"):
        super().__init__(None)
        self._browser = browser
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setFixedWidth(380)
        self.setMaximumHeight(440)
        self.setStyleSheet(
            f"QFrame {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
            f" color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); }}"
            f"QLabel {{ color: white; border: none; }}"
            f"QProgressBar {{ border: none; background: rgb(40,41,45); height: 6px; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()}); border-radius: 3px; }}"
            f"QPushButton {{ background: transparent; color: rgb(180,184,190); border: none; padding: 4px 8px; }}"
            f"QPushButton:hover {{ color: white; }}")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._rows_host)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(self._open_folder)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        footer.addWidget(open_folder)
        footer.addStretch(1)
        footer.addWidget(clear_btn)
        self._layout.addLayout(footer)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self._empty = QLabel("No downloads yet.")
        self._empty.setStyleSheet("color: rgb(180,184,190); padding: 12px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def popup_at(self, global_pos: QPoint):
        self.refresh()
        self.resize(380, min(440, 80 + 72 * max(1, min(6, len(self._browser._downloads)))))
        self.move(global_pos)
        self.show()
        self.raise_()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def refresh(self):
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        items = list(reversed(self._browser._downloads[-15:]))
        if not items:
            self._rows.addWidget(self._empty)
            return
        for dl in items:
            self._rows.addWidget(self._make_row(dl))

    def _make_row(self, dl: DownloadItem) -> QWidget:
        row = QWidget()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        col = QVBoxLayout(row)
        col.setContentsMargins(4, 2, 4, 2)
        col.setSpacing(3)
        if dl.status == "Downloading" and dl.total > 0:
            pct = min(100, int(dl.received * 100 / dl.total))
            detail = f"{_format_bytes(dl.received)} / {_format_bytes(dl.total)}  ({pct}%)"
        elif dl.status == "Downloading":
            pct = 0
            detail = f"{_format_bytes(dl.received)}  -  downloading"
        else:
            pct = 100 if dl.status == "Complete" else 0
            detail = f"{dl.status}  -  {_format_bytes(dl.received or dl.total)}"
        name = QLabel(dl.filename)
        name.setStyleSheet("font-size: 12px;")
        info = QLabel(detail)
        info.setStyleSheet("color: rgb(180,184,190); font-size: 11px;")
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setMaximum(100)
        bar.setValue(pct)
        col.addWidget(name)
        col.addWidget(bar)
        col.addWidget(info)
        row.mousePressEvent = lambda e, item=dl: self._clicked(item, e)
        return row

    def _clicked(self, dl: DownloadItem, event):
        if event.button() == Qt.MouseButton.RightButton:
            _open_local_path(dl.path, select=True)
        else:
            _open_local_path(dl.path, select=False)
        self.hide()

    def _open_folder(self):
        for dl in reversed(self._browser._downloads):
            if dl.path:
                _open_local_path(dl.path, select=True)
                break
        self.hide()

    def _clear(self):
        self._browser._downloads = [d for d in self._browser._downloads if d.status == "Downloading"]
        _save_downloads(self._browser._downloads)
        self.refresh()


# Kill passkey / WebAuthn prompts on every site (Google, Microsoft, GitHub, ...).
DISABLE_PASSKEY_JS = r"""
(function(){
  if (window.__gNoPasskey) return;
  window.__gNoPasskey = 1;
  try {
    if (window.PublicKeyCredential) {
      PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable = function(){ return Promise.resolve(false); };
      PublicKeyCredential.isConditionalMediationAvailable = function(){ return Promise.resolve(false); };
      if (PublicKeyCredential.isExternalCTAP2SecurityKeySupported)
        PublicKeyCredential.isExternalCTAP2SecurityKeySupported = function(){ return Promise.resolve(false); };
    }
  } catch(e) {}
  try {
    if (navigator.credentials) {
      var origGet = navigator.credentials.get.bind(navigator.credentials);
      var origCreate = navigator.credentials.create.bind(navigator.credentials);
      navigator.credentials.get = function(opts){
        if (opts && opts.publicKey)
          return Promise.reject(new DOMException('The user attempted to use an authenticator that is not available.', 'NotAllowedError'));
        return origGet(opts);
      };
      navigator.credentials.create = function(opts){
        if (opts && opts.publicKey)
          return Promise.reject(new DOMException('The user attempted to use an authenticator that is not available.', 'NotAllowedError'));
        return origCreate(opts);
      };
    }
  } catch(e) {}
  function clickSkip(){
    try {
      var texts = ['not now','no thanks','skip','maybe later','use password','try another way',
                   'use your password','cancel','dismiss','not now, thanks'];
      var nodes = document.querySelectorAll('button, [role="button"], a, span, div[jsname]');
      for (var i = 0; i < nodes.length; i++) {
        var t = (nodes[i].innerText || nodes[i].textContent || '').replace(/\s+/g,' ').trim().toLowerCase();
        if (!t || t.length > 40) continue;
        if (texts.indexOf(t) < 0) continue;
        var box = (nodes[i].closest('div,section,form,dialog') || document.body).innerText || '';
        if (!/passkey|pass key|fingerprint|face id|windows hello|security key|skripta|pristupni klju/i.test(box))
          continue;
        nodes[i].click();
        return;
      }
    } catch(e) {}
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', function(){ clickSkip(); setTimeout(clickSkip, 400); });
  else { clickSkip(); setTimeout(clickSkip, 400); }
  setInterval(clickSkip, 1500);
})();
"""


# Suppress Google One Tap / FedCM prompts (ported from Ceprkac 0.8.8 FedCmSuppressJs).
# The FedCM credential UI ("Continue to <site> with google.com") fights the omnibox
# for focus and, on some pages, drives an address-bar blink storm. GBrowser has its
# own password manager, so the redundant Google prompt is neutralised. ONLY the FedCM
# ({identity:...}) path is intercepted - passkeys ({publicKey:...}) and classic
# Credential Management ({password:...}/{federated:...}) pass straight through, so the
# passkey handling above is unaffected. Runs in the main world before page scripts.
FEDCM_SUPPRESS_JS = r"""
(function(){
  if (window.__gNoFedCm) return;
  window.__gNoFedCm = true;
  try {
    var creds = navigator.credentials;
    if (creds && typeof creds.get === 'function') {
      var origGet = creds.get.bind(creds);
      creds.get = function(options){
        try {
          if (options && options.identity) {
            return Promise.reject(new DOMException('FedCM disabled', 'NotAllowedError'));
          }
        } catch(e) {}
        return origGet(options);
      };
    }
  } catch(e) {}
  try {
    function neuter(){
      try {
        if (window.google && google.accounts && google.accounts.id) {
          google.accounts.id.prompt = function(){};
          google.accounts.id.renderButton = google.accounts.id.renderButton || function(){};
        }
      } catch(e) {}
    }
    var n = 0, iv = setInterval(function(){ neuter(); if (++n > 40) clearInterval(iv); }, 250);
    neuter();
  } catch(e) {}
})();
"""


# Capture the real right-click target (ported from Ceprkac ContextCaptureJs).
# QtWebEngine's contextMenuData() reports empty media URLs on Discord/CDN images,
# CSS backgrounds, and in-page viewers, so Lens/reverse-image search never appears.
# This runs in the main world at document creation and records the last right-click
# target (image / video / link / selection) into window.__gbrowserLastCtx, which the
# native contextMenuEvent reads before building its menu.
CONTEXT_CAPTURE_JS = r"""
(function(){
  if (window.__gbrowserCtxCap) return;
  window.__gbrowserCtxCap = true;
  window.__gbrowserLastCtx = null;
  function absUrl(u){
    if(!u) return '';
    try { return new URL(u, location.href).href; } catch(e){ return u; }
  }
  function mediaFrom(el){
    if (!el || el===document || el===window) return null;
    var tag = (el.tagName||'').toUpperCase();
    if (tag==='IMG' || tag==='IMAGE' || tag==='PICTURE') {
      var s = el.currentSrc || el.src || el.getAttribute('src') || '';
      if (!s && tag==='PICTURE') {
        var im = el.querySelector('img');
        if (im) s = im.currentSrc || im.src || '';
      }
      if (s) return {kind:'image', src:absUrl(s)};
    }
    if (tag==='VIDEO' || tag==='AUDIO') {
      var s2 = el.currentSrc || el.src || '';
      if (!s2 && el.querySelector) {
        var srcEl = el.querySelector('source');
        if (srcEl) s2 = srcEl.src || srcEl.getAttribute('src') || '';
      }
      if (s2) return {kind:'video', src:absUrl(s2)};
    }
    if (tag==='A') {
      var href = el.href || '';
      var img = el.querySelector && el.querySelector('img,video');
      if (img) {
        var is = img.currentSrc || img.src || '';
        if (is) return {kind: (img.tagName||'').toUpperCase()==='VIDEO' ? 'video' : 'image', src:absUrl(is), href:href};
      }
      if (href) return {kind:'link', href:href};
    }
    if (tag==='SOURCE' && el.parentElement) return mediaFrom(el.parentElement);
    try {
      var bg = (window.getComputedStyle(el).backgroundImage || '');
      var m = /url\(\s*['"]?([^'")]+)['"]?\s*\)/i.exec(bg);
      if (m && m[1] && m[1].indexOf('data:')!==0) return {kind:'image', src:absUrl(m[1])};
    } catch(e){}
    return null;
  }
  document.addEventListener('contextmenu', function(e){
    var t = e.target;
    var info = null;
    for (var i=0; i<8 && t; i++) {
      info = mediaFrom(t);
      if (info) break;
      t = t.parentElement;
    }
    var sel = '';
    try { sel = (window.getSelection() && window.getSelection().toString()) || ''; } catch(x){}
    window.__gbrowserLastCtx = {
      kind: info ? info.kind : 'page',
      src: info && info.src ? info.src : '',
      href: info && info.href ? info.href : '',
      sel: sel
    };
  }, true);
})();
"""

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
                     ".avif", ".ico", ".tiff", ".jfif", ".heic")
_VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".ogv",
                     ".mpeg", ".mpg", ".m3u8")
_IMAGE_HOST_HINTS = (
    "googleusercontent.com", "ggpht.com", "gstatic.com", "ytimg.com",
    "twimg.com", "fbcdn.net", "cdninstagram.com", "pinimg.com",
    "imgur.com", "wikimedia.org", "cloudinary.com", "imgix.net",
    "akamaihd.net", "discordapp.net", "discordcdn.com", "discordapp.com",
    "media.tenor.com", "giphy.com",
)


def _url_has_extension(url: str, exts: tuple) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = url.lower()
    at = path.find("@")
    if at > 0:
        path = path[:at]
    return any(path.endswith(e) for e in exts)


def _looks_like_image_url(url: str) -> bool:
    return _url_has_extension(url, _IMAGE_EXTENSIONS)


def _looks_like_video_url(url: str) -> bool:
    return _url_has_extension(url, _VIDEO_EXTENSIONS)


def _looks_like_image_host(url: str) -> bool:
    if not url:
        return False
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower()
        for h in _IMAGE_HOST_HINTS:
            if host == h or host.endswith("." + h):
                return True
        path = (u.path or "").lower()
        if any(p in path for p in ("/image", "/img/", "/thumb", "/photo",
                                   "/media/", "/avatar", "/attachments/", "/icons/")):
            return True
    except Exception:
        pass
    return False


# Autofill-assist (ported from Ceprkac AutofillAssistJs). Watches login form submits
# and posts the entered username/password back to the app over the QWebChannel bridge
# so GBrowser can offer to save/update the credential (DPAPI store). Only fires on
# submit - it does NOT re-offer on every focus (that had blocked typing in Ceprkac).
AUTOFILL_ASSIST_JS = r"""
(function(){
  if (window.__gAutofillAssist) return;
  window.__gAutofillAssist = true;
  function send(msg){
    try {
      if (window.__gbridge && window.__gbridge.onPasswordSubmit) {
        window.__gbridge.onPasswordSubmit(JSON.stringify(msg));
      }
    } catch(e) {}
  }
  function capture(form){
    try {
      var pw = form.querySelector('input[type="password"]');
      if (!pw || !pw.value) return;
      var user = form.querySelector(
        'input[type="email"], input[name="email"], input[name="username"], ' +
        'input[name="login"], input[name="user"], input[autocomplete="username"], ' +
        'input[autocomplete="email"], input[type="text"]');
      send({type:'password-submit', url: location.href,
            username: user ? (user.value || '') : '', password: pw.value});
    } catch(e) {}
  }
  document.addEventListener('submit', function(e){
    if (e.target && e.target.tagName === 'FORM') capture(e.target);
  }, true);
  // SPA logins often don't fire a real submit - also catch Enter in a password field
  // and clicks on likely submit buttons.
  document.addEventListener('keydown', function(e){
    try {
      if (e.key === 'Enter' && e.target && e.target.type === 'password') {
        var f = e.target.closest('form');
        if (f) capture(f); else {
          send({type:'password-submit', url: location.href, username:'', password: e.target.value});
        }
      }
    } catch(x){}
  }, true);
})();
"""


class _AutofillBridge(QObject):
    """QWebChannel bridge object exposed to pages as window.__gbridge."""

    def __init__(self, browser):
        super().__init__()
        self._browser = browser

    @pyqtSlot(str)
    def onPasswordSubmit(self, raw: str):
        try:
            data = json.loads(raw)
        except Exception:
            return
        if data.get("type") != "password-submit":
            return
        password = data.get("password", "")
        if not password:
            return
        self._browser._offer_save_password(
            data.get("url", ""), data.get("username", ""), password)


# Collapse reserved-height GPT/DFP slots (index.hr billboards etc.) after the
# iframe is blocked - otherwise the page keeps a huge empty white band.
GSEC_SLOT_COLLAPSE_JS = r"""
(function(){
  var h=(location.hostname||'').toLowerCase();
  if(/accounts\.google|accounts\.youtube|myaccount\.google|signin\.google|accounts\.gstatic|appleid\.apple|login\.microsoft|login\.live/.test(h))return;
  if(window.__gsecSlotCollapse)return;window.__gsecSlotCollapse=1;
  var css=document.createElement('style');
  css.textContent=[
    'div[id^="div-gpt-ad"]','div[id*="gpt-ad"]','div[id^="google_ads_"]',
    'iframe[id^="google_ads"]','iframe[id^="aswift"]','ins.adsbygoogle',
    '[data-google-query-id]','.dfp-ad','.gpt-ad','.AdSlot','.adSlot',
    '[id*="reklama"]','[class*="Reklama"]'
  ].map(function(s){return s+'{display:none!important;height:0!important;min-height:0!important;max-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important;border:0!important}';}).join('');
  (document.head||document.documentElement).appendChild(css);
  function collapse(){
    try{
      document.querySelectorAll('iframe[id^="google_ads"],iframe[id^="aswift"],ins.adsbygoogle,div[id^="div-gpt-ad"],[data-gsec-hidden]').forEach(function(el){
        var p=el.parentElement,n=0;
        while(p&&p!==document.body&&n<4){
          var text=(p.innerText||'').replace(/\s+/g,' ').trim();
          var mh=parseInt(getComputedStyle(p).minHeight,10)||0;
          if(text.length<24&&(mh>=80||p.offsetHeight>=80)){
            p.style.setProperty('display','none','important');
            p.style.setProperty('min-height','0','important');
            p.style.setProperty('height','0','important');
            p.style.setProperty('margin','0','important');
            p.style.setProperty('padding','0','important');
          }
          p=p.parentElement;n++;
        }
      });
    }catch(e){}
  }
  collapse();
  setTimeout(collapse,300);
  setTimeout(collapse,1200);
  setInterval(collapse,2500);
})();
"""


# === INJECTED MODULE CLEANER ===
# Scope: this process and its descendant processes only. Never other apps.
# Policy: a module belongs to GBrowser only if its file lives under GBrowser's
# own tree. There is no vendor / Windows / overlay allowlist. Modules already
# mapped when watching starts are the process image (not an injection).
# Anything mapped after that, unless it is under our tree, is unloaded at once.

def _win_norm(path: str) -> str:
    p = (path or "").strip()
    if p.startswith("\\\\?\\"):
        p = p[4:]
    if not p:
        return ""
    try:
        return os.path.normcase(os.path.abspath(p)).rstrip("\\/")
    except Exception:
        return os.path.normcase(p).rstrip("\\/")


class InjectedModuleCleaner:
    """Unload foreign DLLs from GBrowser.exe and every child it spawns."""

    POLL_S = 0.05
    CHILD_ACCESS = 0x0400 | 0x0010 | 0x0002 | 0x0008 | 0x0020 | 0x1000

    # Grace window after start() during which NOTHING is unloaded. Everything the
    # browser maps while starting up (Qt, the WebEngine render/GPU/network child
    # processes and every Windows system DLL they pull in on demand - dnsapi, mswsock,
    # mfcore, ...) must be captured as legitimate. Unloading those mid-init is what
    # broke DNS ("server IP address could not be found"). At the end of the window the
    # main-process baseline is re-snapshotted, so only modules mapped AFTER init are
    # ever unloaded.
    INIT_GRACE_S = 12.0
    # A newly-seen child process is left alone for this long so its own init-time
    # modules land in its baseline before we start enforcing against it.
    CHILD_GRACE_S = 8.0

    def __init__(self, owner):
        self._owner = owner
        self._prefixes: list[str] = []
        self._baseline: set[int] = set()
        self._child_baseline: dict[int, set[int]] = {}
        self._child_seen_at: dict[int, float] = {}
        self._armed: bool = False
        self._init_deadline: float = 0.0
        self._queue: list[tuple[object, str]] = []
        self._qlock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._k32 = None
        self._psapi = None
        self._ntdll = None
        self._free_library = None
        self._ldr_cookie = ctypes.c_void_p()
        self._ldr_cb = None
        self._HMODULE = ctypes.c_void_p

    def start(self) -> None:
        if sys.platform != "win32":
            return
        try:
            self._init_winapi()
            self._prefixes = self._build_prefixes()
            self._baseline = {self._hmod_int(h) for h, _ in self._modules(self._k32.GetCurrentProcess())}
        except Exception:
            return
        # Stay disarmed until the init grace window elapses; the baseline is refreshed
        # when we arm, so the full startup module set (incl. on-demand Windows DLLs) is
        # treated as legitimate and only later injections are unloaded.
        self._armed = False
        self._init_deadline = time.time() + self.INIT_GRACE_S
        self._thread = threading.Thread(target=self._run, name="GBrowser-ModuleCleaner", daemon=True)
        self._thread.start()
        self._register_ldr()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._unregister_ldr()
        t = self._thread
        if t is not None:
            t.join(1.0)

    def _hmod_int(self, hmod) -> int:
        try:
            return int(ctypes.cast(hmod, ctypes.c_void_p).value or 0)
        except Exception:
            return int(hmod or 0)

    def _init_winapi(self) -> None:
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcessId.restype = wintypes.DWORD
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.FreeLibrary.argtypes = [wintypes.HMODULE]
        k32.FreeLibrary.restype = wintypes.BOOL
        k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        k32.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
        k32.GetProcAddress.restype = ctypes.c_void_p
        k32.CreateRemoteThread.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD)]
        k32.CreateRemoteThread.restype = wintypes.HANDLE
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k32.Process32FirstW.restype = wintypes.BOOL
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k32.Process32NextW.restype = wintypes.BOOL
        HMODULE = ctypes.c_void_p
        psapi.EnumProcessModulesEx.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(HMODULE), wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        psapi.EnumProcessModulesEx.restype = wintypes.BOOL
        psapi.GetModuleFileNameExW.argtypes = [
            wintypes.HANDLE, HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        psapi.GetModuleFileNameExW.restype = wintypes.DWORD
        self._k32 = k32
        self._psapi = psapi
        self._ntdll = ntdll
        self._HMODULE = HMODULE
        hk = k32.GetModuleHandleW("kernel32.dll")
        self._free_library = k32.GetProcAddress(hk, b"FreeLibrary") if hk else None

    def _register_ldr(self) -> None:
        from ctypes import wintypes

        class UNICODE_STRING(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("MaximumLength", wintypes.USHORT),
                ("Buffer", ctypes.c_void_p),
            ]

        class LDR_DLL_NOTIFICATION_DATA(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.ULONG),
                ("FullDllName", ctypes.POINTER(UNICODE_STRING)),
                ("BaseDllName", ctypes.POINTER(UNICODE_STRING)),
                ("DllBase", ctypes.c_void_p),
                ("SizeOfImage", wintypes.ULONG),
            ]

        Fn = ctypes.WINFUNCTYPE(
            None, wintypes.ULONG, ctypes.POINTER(LDR_DLL_NOTIFICATION_DATA), ctypes.c_void_p)

        def _cb(reason, data, _ctx):
            if reason != 1 or not data:
                return
            try:
                info = data.contents
                path = ""
                if info.FullDllName:
                    us = info.FullDllName.contents
                    if us.Buffer and us.Length:
                        path = ctypes.wstring_at(us.Buffer, us.Length // 2)
                hmod = info.DllBase
                # While still in the init grace window, treat every load as legitimate.
                if not self._armed:
                    return
                if self._is_ours(hmod, path, self._baseline):
                    return
                with self._qlock:
                    self._queue.append((hmod, path))
                self._wake.set()
            except Exception:
                pass

        self._ldr_cb = Fn(_cb)
        self._ntdll.LdrRegisterDllNotification.argtypes = [
            wintypes.ULONG, Fn, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self._ntdll.LdrRegisterDllNotification.restype = wintypes.ULONG
        self._ntdll.LdrUnregisterDllNotification.argtypes = [ctypes.c_void_p]
        self._ntdll.LdrUnregisterDllNotification.restype = wintypes.ULONG
        cookie = ctypes.c_void_p()
        st = self._ntdll.LdrRegisterDllNotification(0, self._ldr_cb, None, ctypes.byref(cookie))
        if st == 0:
            self._ldr_cookie = cookie

    def _unregister_ldr(self) -> None:
        try:
            if self._ntdll and self._ldr_cookie and self._ldr_cookie.value:
                self._ntdll.LdrUnregisterDllNotification(self._ldr_cookie)
        except Exception:
            pass
        self._ldr_cookie = ctypes.c_void_p()

    def _build_prefixes(self) -> list[str]:
        raw = [os.path.dirname(os.path.abspath(sys.executable))]
        if getattr(sys, "frozen", False):
            raw.append(getattr(sys, "_MEIPASS", "") or "")
            raw.append(os.path.join(os.path.dirname(sys.executable), "_internal"))
        else:
            raw.append(os.path.dirname(os.path.abspath(__file__)))
            raw.append(getattr(sys, "prefix", "") or "")
            raw.append(getattr(sys, "base_prefix", "") or "")
            raw.append(getattr(sys, "exec_prefix", "") or "")
        out: list[str] = []
        seen: set[str] = set()
        for p in raw:
            n = _win_norm(p)
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _belongs_path(self, path: str) -> bool:
        n = _win_norm(path)
        if not n:
            return False
        for pre in self._prefixes:
            if n == pre or n.startswith(pre + "\\"):
                return True
        return False

    def _is_ours(self, hmod, path: str, baseline: set[int]) -> bool:
        if self._belongs_path(path):
            return True
        return self._hmod_int(hmod) in baseline

    def _modules(self, handle) -> list[tuple[object, str]]:
        from ctypes import wintypes
        HMODULE = self._HMODULE
        arr = (HMODULE * 1024)()
        needed = wintypes.DWORD(0)
        ok = self._psapi.EnumProcessModulesEx(
            handle, arr, ctypes.sizeof(arr), ctypes.byref(needed), 0x03)
        if not ok:
            return []
        count = min(int(needed.value // ctypes.sizeof(HMODULE) or 0), 1024)
        buf = ctypes.create_unicode_buffer(32768)
        out: list[tuple[object, str]] = []
        for i in range(count):
            hmod = arr[i]
            if not hmod:
                continue
            n = self._psapi.GetModuleFileNameExW(handle, hmod, buf, len(buf))
            out.append((hmod, buf.value if n else ""))
        return out

    def _descendant_pids(self) -> set[int]:
        from ctypes import wintypes
        TH32CS_SNAPPROCESS = 0x00000002
        INVALID = ctypes.c_void_p(-1).value

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        me = int(self._k32.GetCurrentProcessId())
        snap = self._k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap or snap == INVALID:
            return set()
        rows: list[tuple[int, int]] = []
        try:
            pe = PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not self._k32.Process32FirstW(snap, ctypes.byref(pe)):
                return set()
            while True:
                rows.append((int(pe.th32ProcessID), int(pe.th32ParentProcessID)))
                if not self._k32.Process32NextW(snap, ctypes.byref(pe)):
                    break
        finally:
            self._k32.CloseHandle(snap)
        tree = {me}
        changed = True
        while changed:
            changed = False
            for pid, ppid in rows:
                if pid not in tree and ppid in tree:
                    tree.add(pid)
                    changed = True
        tree.discard(me)
        return tree

    def _unload_local(self, hmod, path: str) -> None:
        for _ in range(32):
            if not self._k32.FreeLibrary(hmod):
                break
        self._notify(path)

    def _unload_remote(self, proc, hmod, path: str) -> None:
        from ctypes import wintypes
        if not self._free_library:
            return
        tid = wintypes.DWORD(0)
        ht = self._k32.CreateRemoteThread(
            proc, None, 0, self._free_library, hmod, 0, ctypes.byref(tid))
        if not ht:
            return
        self._k32.WaitForSingleObject(ht, 1000)
        self._k32.CloseHandle(ht)
        self._notify(path)

    def _notify(self, path: str) -> None:
        name = os.path.basename(path) or path or "module"
        try:
            lab = getattr(self._owner, "_status_label", None)
            if lab is not None:
                lab.setText(f"Unloaded injected module: {name}")
        except Exception:
            pass

    def _drain_queue(self) -> None:
        with self._qlock:
            batch, self._queue = self._queue, []
        for hmod, path in batch:
            if self._is_ours(hmod, path, self._baseline):
                continue
            try:
                self._unload_local(hmod, path)
            except Exception:
                pass

    def _sweep_self(self) -> None:
        handle = self._k32.GetCurrentProcess()
        for hmod, path in self._modules(handle):
            if self._is_ours(hmod, path, self._baseline):
                continue
            self._unload_local(hmod, path)

    def _sweep_children(self) -> None:
        live = self._descendant_pids()
        for dead in [p for p in self._child_baseline if p not in live]:
            self._child_baseline.pop(dead, None)
        for dead in [p for p in self._child_seen_at if p not in live]:
            self._child_seen_at.pop(dead, None)
        now = time.time()
        for pid in live:
            proc = self._k32.OpenProcess(self.CHILD_ACCESS, False, pid)
            if not proc:
                continue
            try:
                # First sighting: start the child's grace timer and don't enforce yet.
                if pid not in self._child_seen_at:
                    self._child_seen_at[pid] = now
                    continue
                # During the child's grace window keep refreshing its baseline so all
                # of its init-time modules (Windows network/media DLLs, etc.) are kept.
                if now - self._child_seen_at[pid] < self.CHILD_GRACE_S:
                    self._child_baseline[pid] = {
                        self._hmod_int(h) for h, _ in self._modules(proc)}
                    continue
                mods = self._modules(proc)
                if pid not in self._child_baseline:
                    self._child_baseline[pid] = {self._hmod_int(h) for h, _ in mods}
                    continue
                base = self._child_baseline[pid]
                for hmod, path in mods:
                    if self._is_ours(hmod, path, base):
                        continue
                    self._unload_remote(proc, hmod, path)
            except Exception:
                pass
            finally:
                self._k32.CloseHandle(proc)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.POLL_S)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                if not self._armed:
                    # Still initializing: don't unload anything. Keep refreshing the
                    # child map so children are tracked, but hold enforcement.
                    if time.time() >= self._init_deadline:
                        # Re-snapshot: everything mapped during init is now the baseline.
                        try:
                            self._baseline = {
                                self._hmod_int(h)
                                for h, _ in self._modules(self._k32.GetCurrentProcess())
                            }
                        except Exception:
                            pass
                        with self._qlock:
                            self._queue = []  # drop anything queued during init
                        self._armed = True
                    else:
                        continue
                self._drain_queue()
                self._sweep_self()
                self._sweep_children()
            except Exception:
                pass


# === MAIN BROWSER WINDOW (Logic-matched to Ceprkac) ===
class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self._tabs: list[ChromeTab] = []
        self._active_tab_index: int = -1
        self._home_url: str = "https://www.google.com"
        self._search_template: str = "https://www.google.com/search?q={}"
        self._bookmarks: list[BookmarkNode] = []
        self._history: list[str] = []
        self._passwords = PasswordManager()
        self._cards = CardManager()
        self._addresses = AddressManager()
        self._ad_blocker = AdBlockInterceptor()
        self._devtools_windows: list[QWebEngineView] = []
        self._download_windows: list[QWidget] = []
        self._closed_tabs: list[str] = []  # Stack of closed tab URLs (max 20)
        self._cached_main_world_js: str = ""  # Cached blocker JS
        self._last_bookmark_hash: int = 0  # For incremental bookmark bar updates
        self._gsec_dir: str = ""
        self._media_always: dict = _load_media_permissions()
        self._media_session: dict[str, str] = {}
        # Credential-offer suppression (Ceprkac parity):
        #  - permanent: user clicked "Type password manually..."
        #  - temporary: closed picker without choosing -> 20s cooldown (epoch seconds)
        self._dismissed_credential_hosts: set[str] = set()
        self._recently_closed_credential_hosts: dict[str, float] = {}
        self._autofill_bridge = _AutofillBridge(self)
        self._downloads: list[DownloadItem] = _load_downloads()
        self._dl_popup: DownloadsPopup | None = None
        self._profile = QWebEngineProfile("GBrowserProfile", self)
        # Keep the stock QtWebEngine user-agent (includes the QtWebEngine/x.y
        # token and Client Hints). Spoofing Chrome or Firefox is what made
        # Google Sign-In fail after 5.4.
        self._profile.setPersistentStoragePath(os.path.join(CONFIG_DIR, "storage"))
        self._profile.setCachePath(os.path.join(CONFIG_DIR, "cache"))
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        try:
            self._profile.setPersistentPermissionsPolicy(
                QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        except Exception:
            pass
        ws = self._profile.settings()
        ws.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        try:
            ws.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
        except Exception:
            pass
        try:
            ws.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        try:
            ws.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True)
        except Exception:
            pass
        self._profile.setUrlRequestInterceptor(self._ad_blocker)
        self._profile.downloadRequested.connect(self._on_download_requested)
        self._install_passkey_script()
        self._install_fedcm_script()
        self._install_context_capture_script()
        self._install_autofill_assist_scripts()

        self._gsec_dir = _find_gsecurity_dir()
        _load_blocklist_file(_resource_path("blocklist.txt"))
        _import_pac(_find_pac_dir())
        _import_gsecurity(self._gsec_dir)
        self._install_gsecurity_scripts()

        self._build_cached_main_world_js()
        self._init_ui()
        self._apply_dark_titlebar()
        self._load_initial_settings()
        self._bookmarks = _load_bookmarks()
        self._history = _load_history()
        self._build_cached_main_world_js()  # Rebuild after blocklist loaded

        # Show search engine picker on first launch
        if not os.path.exists(SETTINGS_FILE):
            self._show_search_engine_picker()

        self._add_new_tab(self._home_url)
        self._refresh_bookmarks_bar()
        self._update_completer_data()

    def _build_cached_main_world_js(self):
        """Build the main-world blocker JS string ONCE (perf improvement #14)."""
        top_domains = [d for d in BLOCKED_AD_DOMAINS if '*' not in d and 3 < len(d) < 60][:15000]
        domain_list = ','.join(f'"{d}"' for d in top_domains)
        wl_domains = "','".join([
            "google.com","youtube.com","accounts.google.com","apis.google.com","ssl.gstatic.com",
            "gstatic.com","discord.com","discordapp.com","github.com","paypal.com","ebay.com",
            "apple.com","icloud.com","mediafire.com","login.microsoftonline.com","login.live.com",
            "pay.google.com","gog.com","steampowered.com","steamcommunity.com","epicgames.com",
            "ea.com","origin.com","ubisoft.com","blizzard.com","battle.net","riotgames.com",
            "xbox.com","playstation.com","nintendo.com","twitch.tv","chase.com","bankofamerica.com",
            "wellsfargo.com","citibank.com","capitalone.com","revolut.com","wise.com","stripe.com","n26.com"
        ])
        self._cached_main_world_js = (
            "(function(){if(window.__gFB)return;window.__gFB=1;"
            f"var b=new Set([{domain_list}]);"
            f"var wl=new Set(['{wl_domains}']);"
            "function isWl(h){while(h){if(wl.has(h))return 1;var i=h.indexOf('.');if(i<0)break;h=h.substr(i+1);}return 0};"
            "function baseDom(h){var p=h.split('.');if(p.length>=3&&/^(uk|au|jp|br|za|nz|kr|in)$/.test(p[p.length-1]))return p.slice(-3).join('.');return p.length>=2?p.slice(-2).join('.'):h;}"
            "function sameSite(h){return baseDom(h)===baseDom(location.hostname);}"
            "function chk(u){try{if(isWl(location.hostname))return 0;var l=u.toLowerCase();var h=new URL(l).hostname;"
            "if(isWl(h))return 0;"
            "if(sameSite(h))return 0;"
            "while(h){if(b.has(h))return 1;var i=h.indexOf('.');if(i<0)break;h=h.substr(i+1);}"
            "if(/(\\/ads?\\/|\\/ad[sx]?\\b|\\/pagead\\/|\\/ptracking|\\/advert|\\/sponsored|\\/promotion|\\/tracking\\/|\\/analytics\\/|\\/collect\\?|\\/beacon|\\/pixel|\\/imp\\?|\\/impression|\\/click\\?|ad_banner|ad_frame|sponsored_content|promo_banner|[?&](ad|ads|adunit|adformat|adtag)=)/i.test(l))return 1;"
            "if(/(?:\\/(?:adcontent|img\\/adv|web-ad|iframead|contentad|ad\\/image|video-ad|stats\\/event|xtclicks|adscript|bannerad|googlead|adhandler|adimages|adconfig|tracking\\/track|tracker\\/track|adrequest|nativead|adman|advertisement|adframe|adcontrol|adoverlay|adserver|adsense|google-ads|ad-banner|banner-ad|adplacement|adblockdetect|advertising|admanagement|adprovider|adrotation|adunit|adcall|adlog|adcount|adserve|adsrv|adsys|adtrack|adview|adwidget|adzone|sidebar-ads|footer-ads|top-ads|bottom-ads|ads\\.php|ad\\.js|ad\\.css))/i.test(l))return 1;"
            "if(/\\/api\\/stats\\/(ads|atr)/i.test(l))return 1;"
            "var hh=new URL(l).hostname;"
            "if(/^(?:.*[-_.])?(ads?|adv(ert(s|ising)?)?|banners?|track(er|ing|s)?|beacons?|doubleclick|adservice|adnxs|adtech|googleads|gads|adwords|partner|sponsor(ed)?|click(s|bank|tale|through)?|pop(up|under)s?|promo(tion)?|market(ing|er)?|affiliates?|metrics?|stat(s|counter|istics)?|analytics?|pixels?|campaign|traff(ic|iq)|monetize|syndicat(e|ion)|revenue|yield|impress(ion)?s?|conver(sion|t)?|audience|target(ing)?|behavior|profil(e|ing)|telemetry|survey|outbrain|taboola|quantcast|scorecard|omniture|comscore|krux|bluekai|exelate|adform|adroll|rubicon|vungle|inmobi|flurry|mixpanel|heap|amplitude|optimizely|bizible|pardot|hubspot|marketo|eloqua|media(math|net)|criteo|appnexus|turn|adbrite|admob|adsonar|adscale|zergnet|revcontent|mgid|nativeads|contentad|displayads|bannerflow|adblade|adcolony|chartbeat|newrelic|pingdom|kissmetrics|tradedesk|bidder|auction|rtb|programmatic|interstitial|overlay|trafficjunky|trafficstars|exoclick|juicyads|realsrv|magsrv)\\./i.test(hh))return 1;"
            "if(/^(?:adcreative(s)?|imageserv|media(mgr)?|stats|switch|track(2|er)?|view|ads?\\d{0,3}|banners?\\d{0,3}|clicks?\\d{0,3}|count(er)?\\d{0,3}|servedby\\d{0,3}|toolbar\\d{0,3}|pageads\\d{0,3}|pops\\d{0,3}|promos?\\d{0,3})\\./i.test(hh))return 1;"
            "if(/(?:\\/(1|blank|b|clear|pixel|transp|spacer)\\.gif|\\.swf)$/i.test(l))return 1;"
            "return 0}catch(e){return 0}};"
            "var F=fetch;window.fetch=function(a,o){var u=typeof a==='string'?a:a&&a.url?a.url:'';if(chk(u))return Promise.reject(new TypeError('blocked'));return F.apply(this,arguments)};"
            "var X=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(){var u=arguments[1]||'';if(typeof u==='string'&&chk(u)){this.__blk=1;return}return X.apply(this,arguments)};"
            "var S=XMLHttpRequest.prototype.send;XMLHttpRequest.prototype.send=function(){if(this.__blk)return;return S.apply(this,arguments)};"
            "})()"
        )

    def _init_ui(self):
        self.setWindowTitle("GBrowser")
        self.setMinimumSize(800, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Custom Chrome-style tab strip
        self._tab_strip = ChromeTabStrip()
        self._tab_strip.tab_clicked.connect(self._on_tab_clicked)
        self._tab_strip.tab_close_clicked.connect(self._on_tab_close_clicked)
        self._tab_strip.new_tab_clicked.connect(lambda: self._add_new_tab(self._home_url))
        layout.addWidget(self._tab_strip)

        # Navigation toolbar
        nav = QWidget()
        nav.setStyleSheet(f"background: rgb({Theme.Toolbar.red()},{Theme.Toolbar.green()},{Theme.Toolbar.blue()}); padding: 4px;")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(6)

        btn_style = (f"QPushButton {{ background: transparent; color: white; border: none; padding: 4px 8px; font-size: 14px; }}"
                     f"QPushButton:hover {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); border-radius: 4px; }}")

        self._back_btn = QPushButton("\u2190")
        self._back_btn.setStyleSheet(btn_style)
        self._back_btn.setToolTip("Back")
        self._back_btn.clicked.connect(self._go_back)
        nav_layout.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("\u2192")
        self._fwd_btn.setStyleSheet(btn_style)
        self._fwd_btn.setToolTip("Forward")
        self._fwd_btn.clicked.connect(self._go_forward)
        nav_layout.addWidget(self._fwd_btn)

        self._reload_btn = QPushButton("\u21bb")
        self._reload_btn.setStyleSheet(btn_style)
        self._reload_btn.setToolTip("Reload")
        self._reload_btn.clicked.connect(self._reload)
        nav_layout.addWidget(self._reload_btn)

        self._address = QLineEdit()
        self._address.setStyleSheet(
            f"QLineEdit {{ background: rgb({Theme.AddressBox.red()},{Theme.AddressBox.green()},{Theme.AddressBox.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()});"
            f"border-radius: 16px; padding: 4px 12px; font-size: 13px; }}"
        )
        self._address.returnPressed.connect(self._on_address_enter)
        nav_layout.addWidget(self._address, 1)

        # Address bar autocomplete (#11)
        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setMaxVisibleItems(8)
        self._address.setCompleter(self._completer)

        self._bookmark_btn = QPushButton("\u2606")
        self._bookmark_btn.setStyleSheet(btn_style)
        self._bookmark_btn.setToolTip("Add bookmark (Ctrl+D)")
        self._bookmark_btn.clicked.connect(self._toggle_bookmark)
        nav_layout.addWidget(self._bookmark_btn)

        self._dl_btn = QPushButton("\u2913")
        self._dl_btn.setStyleSheet(btn_style)
        self._dl_btn.setToolTip("Downloads")
        self._dl_btn.clicked.connect(self._toggle_downloads_popup)
        nav_layout.addWidget(self._dl_btn)

        self._menu_btn = QPushButton("\u2261")
        self._menu_btn.setStyleSheet(btn_style)
        self._menu_btn.setToolTip("Menu")
        self._menu_btn.clicked.connect(self._show_menu)
        nav_layout.addWidget(self._menu_btn)

        layout.addWidget(nav)

        # Bookmark bar
        self._bookmark_bar = QWidget()
        self._bookmark_bar.setStyleSheet(f"background: rgb({Theme.BookmarkBar.red()},{Theme.BookmarkBar.green()},{Theme.BookmarkBar.blue()}); padding: 2px 8px;")
        self._bm_layout = QHBoxLayout(self._bookmark_bar)
        self._bm_layout.setContentsMargins(0, 0, 0, 0)
        self._bm_layout.setSpacing(4)
        layout.addWidget(self._bookmark_bar)

        # Find bar (#6) - hidden by default
        self._find_bar = QWidget()
        self._find_bar.setStyleSheet(
            f"background: rgb({Theme.Toolbar.red()},{Theme.Toolbar.green()},{Theme.Toolbar.blue()}); padding: 2px 8px;")
        find_layout = QHBoxLayout(self._find_bar)
        find_layout.setContentsMargins(8, 2, 8, 2)
        find_layout.setSpacing(4)
        find_label = QLabel("Find:")
        find_label.setStyleSheet("color: white; font-size: 12px;")
        find_layout.addWidget(find_label)
        self._find_input = QLineEdit()
        self._find_input.setStyleSheet(
            f"QLineEdit {{ background: rgb({Theme.AddressBox.red()},{Theme.AddressBox.green()},{Theme.AddressBox.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()});"
            f"border-radius: 4px; padding: 2px 8px; font-size: 12px; }}")
        self._find_input.setPlaceholderText("Search in page...")
        self._find_input.returnPressed.connect(self._find_next)
        self._find_input.textChanged.connect(self._find_live)
        find_layout.addWidget(self._find_input, 1)
        find_btn_style = (f"QPushButton {{ background: transparent; color: white; border: none; padding: 2px 6px; font-size: 12px; }}"
                          f"QPushButton:hover {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); border-radius: 3px; }}")
        prev_btn = QPushButton("\u25b2")
        prev_btn.setStyleSheet(find_btn_style)
        prev_btn.setToolTip("Previous")
        prev_btn.clicked.connect(self._find_prev)
        find_layout.addWidget(prev_btn)
        next_btn = QPushButton("\u25bc")
        next_btn.setStyleSheet(find_btn_style)
        next_btn.setToolTip("Next")
        next_btn.clicked.connect(self._find_next)
        find_layout.addWidget(next_btn)
        close_find_btn = QPushButton("\u2715")
        close_find_btn.setStyleSheet(find_btn_style)
        close_find_btn.setToolTip("Close find bar")
        close_find_btn.clicked.connect(self._close_find_bar)
        find_layout.addWidget(close_find_btn)
        self._find_bar.setVisible(False)
        layout.addWidget(self._find_bar)

        # Web view container
        self._web_panel = QStackedWidget()
        self._web_panel.setStyleSheet(f"background: rgb({Theme.TitleBar.red()},{Theme.TitleBar.green()},{Theme.TitleBar.blue()});")
        layout.addWidget(self._web_panel, 1)

        # Status bar
        self._status_label = QLabel()
        self._status_label.setStyleSheet(
            f"QLabel {{ background: rgb({Theme.StatusBar.red()},{Theme.StatusBar.green()},{Theme.StatusBar.blue()});"
            f"color: rgb({Theme.ForeDim.red()},{Theme.ForeDim.green()},{Theme.ForeDim.blue()}); padding: 2px 8px; font-size: 11px; }}"
        )
        layout.addWidget(self._status_label)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(lambda: self._add_new_tab(self._home_url))
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(self._close_current_tab)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._focus_address_bar)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._toggle_bookmark)
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(self._open_devtools)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._toggle_find_bar)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._close_find_bar)
        QShortcut(QKeySequence("Ctrl+Shift+T"), self).activated.connect(self._restore_closed_tab)
        QShortcut(QKeySequence("Ctrl+Shift+K"), self).activated.connect(self._duplicate_tab)
        # Zoom shortcuts (#7)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self._zoom_reset)
        # Tab cycling (#21)
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(self._prev_tab)

    def _apply_dark_titlebar(self):
        try:
            from ctypes import windll
            HWND = int(self.winId())
            windll.dwmapi.DwmSetWindowAttribute(HWND, 20, int(True), 4)
        except Exception:
            pass

    def _load_initial_settings(self):
        settings = _load_settings()
        self._home_url = settings.get("homepage", self._home_url)
        self._search_template = settings.get("searchurl", self._search_template)

    # === Find-in-page (#6) ===
    def _toggle_find_bar(self):
        visible = not self._find_bar.isVisible()
        self._find_bar.setVisible(visible)
        if visible:
            self._find_input.setFocus()
            self._find_input.selectAll()
        else:
            self._clear_find()

    def _close_find_bar(self):
        self._find_bar.setVisible(False)
        self._clear_find()

    def _find_live(self, text: str):
        tab = self._active_tab()
        if tab and tab.web_view and tab.web_view.page():
            if text:
                tab.web_view.page().findText(text)
            else:
                tab.web_view.page().findText("")

    def _find_next(self):
        text = self._find_input.text()
        tab = self._active_tab()
        if tab and tab.web_view and tab.web_view.page() and text:
            tab.web_view.page().findText(text)

    def _find_prev(self):
        text = self._find_input.text()
        tab = self._active_tab()
        if tab and tab.web_view and tab.web_view.page() and text:
            tab.web_view.page().findText(text, QWebEnginePage.FindFlag.FindBackward)

    def _clear_find(self):
        tab = self._active_tab()
        if tab and tab.web_view and tab.web_view.page():
            tab.web_view.page().findText("")

    # === Zoom controls (#7) ===
    def _zoom_in(self):
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.zoom_factor = min(5.0, tab.zoom_factor + 0.1)
            tab.web_view.setZoomFactor(tab.zoom_factor)
            self._update_zoom_status()

    def _zoom_out(self):
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.zoom_factor = max(0.25, tab.zoom_factor - 0.1)
            tab.web_view.setZoomFactor(tab.zoom_factor)
            self._update_zoom_status()

    def _zoom_reset(self):
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.zoom_factor = 1.0
            tab.web_view.setZoomFactor(1.0)
            self._update_zoom_status()

    def _update_zoom_status(self):
        tab = self._active_tab()
        if tab and abs(tab.zoom_factor - 1.0) > 0.01:
            pct = int(tab.zoom_factor * 100)
            self._status_label.setText(f"Zoom: {pct}%  |  Ads blocked: {self._ad_blocker.blocked_count} | Domains: {len(BLOCKED_AD_DOMAINS)}")
        else:
            self._update_ad_block_status()

    # === Tab cycling (#21) ===
    def _next_tab(self):
        if len(self._tabs) < 2:
            return
        idx = (self._tab_strip.selected_index + 1) % len(self._tabs)
        self._tab_strip.set_current_index(idx)
        self._on_tab_clicked(idx)

    def _prev_tab(self):
        if len(self._tabs) < 2:
            return
        idx = (self._tab_strip.selected_index - 1) % len(self._tabs)
        self._tab_strip.set_current_index(idx)
        self._on_tab_clicked(idx)

    # === Tab restore (#8) ===
    def _restore_closed_tab(self):
        if self._closed_tabs:
            url = self._closed_tabs.pop()
            self._add_new_tab(url)

    # === Duplicate tab (Ctrl+Shift+K, Ceprkac parity) ===
    def _duplicate_tab(self):
        tab = self._active_tab()
        if not tab:
            return
        url = tab.url or self._home_url
        if url.startswith("about:"):
            url = self._home_url
        self._add_new_tab(url, insert_after=self._active_tab_index)

    # === Ad block status in status bar (#22) ===
    def _update_ad_block_status(self):
        self._status_label.setText(
            f"Ads blocked: {self._ad_blocker.blocked_count} | Domains: {len(BLOCKED_AD_DOMAINS)}")

    # === Autocomplete (#11) ===
    def _update_completer_data(self):
        urls = list(self._history)
        urls.extend(_collect_bookmark_urls(self._bookmarks))
        seen = set()
        unique = []
        for u in urls:
            if u.lower() not in seen:
                seen.add(u.lower())
                unique.append(u)
        from PyQt6.QtCore import QStringListModel
        model = QStringListModel(unique, self._completer)
        self._completer.setModel(model)

    def _add_new_tab(self, url: str = "", insert_after: int = None, load_url: bool = True):
        tab = ChromeTab()
        if load_url:
            tab.url = url or self._home_url
        else:
            # Popup/OAuth: Chromium will navigate this page. Do not load() a
            # second copy - that would break window.opener.
            tab.url = url or "about:blank"
            tab.is_popup = True

        # Use custom BrowserPage for OAuth handling + BrowserWebView for context menu
        tab.web_view = BrowserWebView(browser_window=self)
        page = BrowserPage(self._profile, tab.web_view, browser_window=self)
        tab.web_view.setPage(page)

        # QWebChannel bridge so login-form submits can offer to save the password.
        try:
            channel = QWebChannel(page)
            channel.registerObject("__gbridgeObj", self._autofill_bridge)
            page.setWebChannel(channel)
        except Exception:
            pass

        # Connect signals
        page.loadStarted.connect(lambda: self._on_load_started(tab))
        page.loadFinished.connect(lambda ok: self._on_load_finished(tab, ok))
        page.loadProgress.connect(lambda p: self._on_load_progress(tab, p))
        page.urlChanged.connect(lambda u: self._on_url_changed(tab, u))
        page.titleChanged.connect(lambda t: self._on_title_changed(tab, t))
        page.windowCloseRequested.connect(lambda t=tab: self._on_window_close_requested(t))

        # Inject ad hider on load
        page.loadFinished.connect(lambda ok: self._inject_ad_hider(page) if ok else None)

        # Insert tab
        insert_idx = insert_after + 1 if insert_after is not None else len(self._tabs)
        if insert_after is not None and 0 <= insert_after < len(self._tabs):
            self._tabs.insert(insert_idx, tab)
        else:
            self._tabs.append(tab)
            insert_idx = len(self._tabs) - 1

        self._web_panel.addWidget(tab.web_view)
        self._tab_strip.insert_tab(insert_idx, tab, "Loading...")
        self._tab_strip.set_current_index(insert_idx)
        self._active_tab_index = insert_idx
        self._web_panel.setCurrentWidget(tab.web_view)

        if load_url:
            tab.web_view.load(_to_qurl(tab.url))
        # User-created tabs: put the caret in the address bar so typing
        # starts immediately (Chrome omnibox). OAuth popups keep page focus.
        if load_url and not tab.is_popup:
            tab.focus_omnibox = True
            # Don't let the web view steal keys until the user clicks the page.
            tab.web_view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self._address.setText(tab.url)
            self._focus_address_bar()
            QTimer.singleShot(0, self._focus_address_bar)
        return tab

    def _focus_address_bar(self):
        """Focus the address bar and select its text so the next key replaces it."""
        self._address.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._address.selectAll()

    def _set_address_text(self, url: str):
        """Write the omnibox without disturbing an active user edit (Ceprkac
        SetAddressText). Treats about:blank as empty and skips if unchanged."""
        text = "" if (url or "").startswith("about:") else (url or "")
        if self._address.hasFocus():
            return
        if self._address.text() == text:
            return
        self._address.setText(text)

    def _on_tab_clicked(self, index: int):
        if 0 <= index < len(self._tabs):
            self._active_tab_index = index
            self._web_panel.setCurrentWidget(self._tabs[index].web_view)
            self._set_address_text(self._tabs[index].url)
            self._update_bookmark_star()
            self._update_window_title()
            # Apply per-tab zoom
            tab = self._tabs[index]
            if tab.web_view:
                tab.web_view.setZoomFactor(tab.zoom_factor)
            self._update_zoom_status()
            if tab.focus_omnibox:
                self._focus_address_bar()
            elif tab.web_view:
                tab.web_view.setFocus()

    def _on_tab_close_clicked(self, index: int):
        self._close_tab(index)

    def _safe_close_tab(self, tab):
        """Close a tab by reference, not index (fix #3)."""
        if tab in self._tabs:
            idx = self._tabs.index(tab)
            self._close_tab(idx)

    def _close_tab(self, index: int):
        if len(self._tabs) <= 1:
            return
        tab = self._tabs.pop(index)
        # Save URL for restore (#8)
        if tab.url and tab.url != "about:blank":
            self._closed_tabs.append(tab.url)
            if len(self._closed_tabs) > 20:
                self._closed_tabs = self._closed_tabs[-20:]
        self._web_panel.removeWidget(tab.web_view)
        tab.web_view.deleteLater()
        self._tab_strip.remove_tab(index)

        if self._active_tab_index >= len(self._tabs):
            self._active_tab_index = len(self._tabs) - 1
        if 0 <= self._active_tab_index < len(self._tabs):
            self._tab_strip.set_current_index(self._active_tab_index)
            self._web_panel.setCurrentWidget(self._tabs[self._active_tab_index].web_view)
            self._update_window_title()

    def _close_current_tab(self):
        self._close_tab(self._tab_strip.selected_index)

    def _on_load_started(self, tab: ChromeTab):
        tab.is_loading = True
        tab.load_progress = 0
        self._tab_strip.update()
        if tab == self._active_tab():
            if not any(d.status == "Downloading" and not d._finalized for d in self._downloads):
                self._status_label.setText("Loading...")
            # Reclaim keys if the web view stole them, but don't selectAll
            # over characters the user already typed.
            if tab.focus_omnibox and not self._address.hasFocus():
                self._focus_address_bar()

    def _on_load_finished(self, tab: ChromeTab, ok: bool):
        tab.is_loading = False
        tab.load_progress = 100
        idx = self._tabs.index(tab) if tab in self._tabs else -1
        if idx >= 0:
            self._tab_strip.set_tab_text(idx, tab.title[:25] if tab.title else "New Tab")
        if not any(d.status == "Downloading" and not d._finalized for d in self._downloads):
            self._update_ad_block_status()
        self._add_to_history(tab.url)
        self._try_autofill(tab)
        self._try_checkout_autofill(tab)

        # Auto-close auth callback tabs (like Ceprkac)
        self._check_auto_close_auth_tab(tab)

    def _on_load_progress(self, tab: ChromeTab, progress: int):
        tab.load_progress = progress
        idx = self._tabs.index(tab) if tab in self._tabs else -1
        if idx >= 0 and tab.is_loading:
            self._tab_strip.set_tab_text(idx, f"Loading {progress}%")
        self._tab_strip.update()

    def _on_url_changed(self, tab: ChromeTab, url: QUrl):
        url_str = url.toString()
        tab.url = url_str
        if tab.is_popup:
            if url_str and not url_str.startswith("about:") and _is_ad_url(url_str):
                QTimer.singleShot(0, lambda t=tab: self._safe_close_tab(t))
                return
            # After Google/OAuth, the popup often goes to about:blank (black tab).
            if url_str and not url_str.startswith("about:"):
                tab._popup_had_page = True
            elif getattr(tab, "_popup_had_page", False):
                QTimer.singleShot(400, lambda t=tab: self._close_empty_popup(t))
        if tab == self._active_tab():
            # Don't let page-driven URL updates (SPA route changes, ad iframes,
            # redirect chains) rewrite the omnibox while the user is typing in it -
            # that reselects the text and, on focus-stealing pages, feeds a blink
            # loop (Ceprkac 0.8.7/0.8.8 focus-loop breaker).
            if not self._address.hasFocus() and not tab.focus_omnibox:
                self._set_address_text(tab.url)
        # Re-trigger autofill for multi-step logins
        self._try_autofill(tab)
        self._try_checkout_autofill(tab)

    def _close_empty_popup(self, tab: ChromeTab):
        if tab not in self._tabs or not tab.is_popup:
            return
        u = (tab.url or "").lower()
        if u.startswith("about:") or not u:
            self._safe_close_tab(tab)

    def _on_title_changed(self, tab: ChromeTab, title: str):
        tab.title = title
        idx = self._tabs.index(tab) if tab in self._tabs else -1
        if idx >= 0:
            self._tab_strip.set_tab_text(idx, title[:25] if title else "New Tab")
        # Update window title (#20)
        if tab == self._active_tab():
            self._update_window_title()

    def _update_window_title(self):
        """Set window title to '{tab title} - GBrowser' (#20)."""
        tab = self._active_tab()
        if tab and tab.title:
            self.setWindowTitle(f"{tab.title} - GBrowser")
        else:
            self.setWindowTitle("GBrowser")

    def _active_tab(self) -> ChromeTab | None:
        if 0 <= self._active_tab_index < len(self._tabs):
            return self._tabs[self._active_tab_index]
        return None

    def _install_script(self, name: str, source: str, world, point, subframes: bool = True):
        script = QWebEngineScript()
        script.setName(name)
        script.setSourceCode(source)
        script.setWorldId(world)
        script.setInjectionPoint(point)
        script.setRunsOnSubFrames(subframes)
        self._profile.scripts().insert(script)

    def _media_stored_decision(self, origin: str) -> str | None:
        host = origin
        try:
            host = urlparse(origin).scheme + "://" + (urlparse(origin).hostname or origin)
        except Exception:
            pass
        rec = self._media_always.get(host) or self._media_always.get(origin) or {}
        if isinstance(rec, str):
            return rec
        if rec.get("all") in ("allow", "block"):
            return rec["all"]
        if self._media_session.get(host) or self._media_session.get(origin):
            return self._media_session.get(host) or self._media_session.get(origin)
        return None

    def _store_media_decision(self, origin: str, choice: str) -> None:
        host = origin
        try:
            parsed = urlparse(origin)
            if parsed.hostname:
                host = f"{parsed.scheme}://{parsed.hostname}"
        except Exception:
            pass
        if choice == "always":
            self._media_always[host] = {"all": "allow"}
            _save_media_permissions(self._media_always)
        elif choice == "block-always":
            self._media_always[host] = {"all": "block"}
            _save_media_permissions(self._media_always)
        elif choice == "session":
            self._media_session[host] = "allow"

    def _apply_media_result(self, permission, legacy, granted: bool) -> None:
        if permission is not None:
            try:
                if granted:
                    permission.grant()
                else:
                    permission.deny()
            except Exception:
                pass
            return
        if not legacy:
            return
        page, origin, feature = legacy
        try:
            policy = (QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                      if granted else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
            page.setFeaturePermission(origin, feature, policy)
        except Exception:
            pass

    def _handle_media_permission(self, origin: str, kinds: list[str], permission, legacy):
        stored = self._media_stored_decision(origin)
        if stored == "allow":
            self._apply_media_result(permission, legacy, True)
            return
        if stored == "block":
            self._apply_media_result(permission, legacy, False)
            return
        dlg = MediaPermissionDialog(origin, kinds, self)
        result = dlg.exec()
        choice = dlg.choice()
        if result != QDialog.DialogCode.Accepted:
            if choice == "block-always":
                self._store_media_decision(origin, "block-always")
            self._apply_media_result(permission, legacy, False)
            return
        self._store_media_decision(origin, choice)
        self._apply_media_result(permission, legacy, True)

    def _install_passkey_script(self):
        """Dismiss WebAuthn/passkey prompts; do not spoof browser identity."""
        self._install_script(
            "gbrowser-no-passkey",
            DISABLE_PASSKEY_JS,
            QWebEngineScript.ScriptWorldId.MainWorld,
            QWebEngineScript.InjectionPoint.DocumentCreation,
            True,
        )

    def _install_fedcm_script(self):
        """Suppress Google One Tap / FedCM prompts (Ceprkac 0.8.8 parity).

        Must run in the MAIN world so it can see the page's real
        navigator.credentials - an isolated-world copy cannot patch it.
        """
        self._install_script(
            "gbrowser-no-fedcm",
            FEDCM_SUPPRESS_JS,
            QWebEngineScript.ScriptWorldId.MainWorld,
            QWebEngineScript.InjectionPoint.DocumentCreation,
            True,
        )

    def _install_context_capture_script(self):
        """Record the real right-click target for the native context menu."""
        self._install_script(
            "gbrowser-ctx-capture",
            CONTEXT_CAPTURE_JS,
            QWebEngineScript.ScriptWorldId.MainWorld,
            QWebEngineScript.InjectionPoint.DocumentCreation,
            True,
        )

    def _install_autofill_assist_scripts(self):
        """Install the QWebChannel client + bridge bootstrap + the save-password
        assist script (Ceprkac AutofillAssistJs) into the main world."""
        # Read Qt's bundled qwebchannel.js client so window.QWebChannel exists.
        qwc = ""
        try:
            from PyQt6.QtCore import QFile, QIODevice
            f = QFile(":/qtwebchannel/qwebchannel.js")
            if f.open(QIODevice.OpenModeFlag.ReadOnly):
                qwc = bytes(f.readAll()).decode("utf-8", "ignore")
                f.close()
        except Exception:
            qwc = ""
        if not qwc:
            # Cannot expose the bridge without the client; skip save-password wiring.
            return
        # qt.webChannelTransport is not guaranteed to exist in the main world at
        # DocumentCreation, so poll for it (and for the QWebChannel client) instead
        # of bailing once. Without this the bridge can silently never bind and
        # save-password never fires.
        bootstrap = (
            "(function(){"
            "var tries=0;"
            "function bind(){"
            "if(window.__gbridge)return;"
            "if(typeof QWebChannel!=='undefined'&&window.qt&&qt.webChannelTransport){"
            "try{new QWebChannel(qt.webChannelTransport,function(ch){"
            "window.__gbridge=ch.objects.__gbridgeObj;});}catch(e){}"
            "return;}"
            "if(++tries<60)setTimeout(bind,100);"
            "}"
            "bind();"
            "})();"
        )
        self._install_script(
            "gbrowser-qwebchannel",
            qwc + "\n" + bootstrap,
            QWebEngineScript.ScriptWorldId.MainWorld,
            QWebEngineScript.InjectionPoint.DocumentCreation,
            True,
        )
        self._install_script(
            "gbrowser-autofill-assist",
            AUTOFILL_ASSIST_JS,
            QWebEngineScript.ScriptWorldId.MainWorld,
            QWebEngineScript.InjectionPoint.DocumentReady,
            True,
        )

    def _install_gsecurity_scripts(self):
        """Install GSecurity-Ad-Shield content/main-world scripts on the profile."""
        if not self._gsec_dir:
            return
        # Never run Shield scripts on IdP hosts - they break Google Sign-In.
        auth_prefix = (
            "(function(){var h=(location.hostname||'').toLowerCase();"
            "if(/accounts\\.google|accounts\\.youtube|myaccount\\.google|signin\\.google|"
            "accounts\\.gstatic|appleid\\.apple|"
            "login\\.microsoft|login\\.live|idmsa\\.apple/.test(h))return;\n"
        )
        auth_suffix = "\n})();"
        chrome_shim = (
            "window.__gsecMainWorldLink=true;"
            "if(typeof chrome==='undefined'){window.chrome={runtime:{getURL:function(){return '';}}};}\n"
        )
        files = (
            ("gsec-main-world", "main-world.js",
             QWebEngineScript.ScriptWorldId.MainWorld,
             QWebEngineScript.InjectionPoint.DocumentCreation, True, False),
            ("gsec-cosmetic", "content-cosmetic.js",
             QWebEngineScript.ScriptWorldId.ApplicationWorld,
             QWebEngineScript.InjectionPoint.DocumentCreation, True, True),
            ("gsec-sites", "content-sites.js",
             QWebEngineScript.ScriptWorldId.ApplicationWorld,
             QWebEngineScript.InjectionPoint.DocumentCreation, True, True),
            ("gsec-youtube", "content.js",
             QWebEngineScript.ScriptWorldId.ApplicationWorld,
             QWebEngineScript.InjectionPoint.DocumentCreation, True, True),
            ("gsec-generic", "content-generic.js",
             QWebEngineScript.ScriptWorldId.ApplicationWorld,
             QWebEngineScript.InjectionPoint.Deferred, True, True),
        )
        for name, filename, world, point, frames, need_shim in files:
            path = os.path.join(self._gsec_dir, filename)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    source = f.read()
            except Exception:
                continue
            if need_shim:
                source = chrome_shim + source
            self._install_script(name, auth_prefix + source + auth_suffix, world, point, frames)
        self._install_script(
            "gsec-slot-collapse",
            GSEC_SLOT_COLLAPSE_JS,
            QWebEngineScript.ScriptWorldId.ApplicationWorld,
            QWebEngineScript.InjectionPoint.DocumentReady,
            True,
        )

    def _on_window_close_requested(self, tab: ChromeTab):
        """Honor window.close() so OAuth callback tabs can dismiss themselves."""
        if tab not in self._tabs:
            return
        if len(self._tabs) > 1:
            self._safe_close_tab(tab)
        elif tab.is_popup:
            tab.is_popup = False
            self._navigate_tab(tab, self._home_url)

    def _check_auto_close_auth_tab(self, tab: ChromeTab):
        """Auto-close auth callback tabs like Ceprkac.
        Only close if this is clearly a popup-style auth tab (opened by createWindow),
        not the main tab the user is actively using."""
        # Disabled: auto-closing tabs during OAuth flows causes login failures
        # (e.g. Reddit via Google OAuth - the callback page needs to finish processing)
        pass

    def _on_download_requested(self, download):
        """Handle download requests like Ceprkac's DownloadStarting."""
        suggested = download.suggestedFileName() or "download"
        path, _ = QFileDialog.getSaveFileName(self, "Save As", suggested)
        if not path:
            download.cancel()
            return
        directory, filename = os.path.split(path)
        if hasattr(download, "setDownloadDirectory") and directory:
            download.setDownloadDirectory(directory)
            download.setDownloadFileName(filename)
        else:
            download.setDownloadFileName(path)
        download.accept()
        url = ""
        try:
            url = download.url().toString()
        except Exception:
            pass
        dl_item = DownloadItem(filename or os.path.basename(path), path, url)
        # Must keep the Qt download object alive. If Python GCs the wrapper,
        # progress/finished signals never fire and the UI stays on "Downloading".
        dl_item._request = download
        self._downloads.append(dl_item)
        if len(self._downloads) > 40:
            self._downloads = self._downloads[-40:]
        self._status_label.setText(f"Downloading {dl_item.filename}...")
        self._refresh_dl_button()
        self._wire_download(download, dl_item)
        if self._dl_popup and self._dl_popup.isVisible():
            self._dl_popup.refresh()

    def _wire_download(self, download, dl_item: DownloadItem):
        """Connect Qt5 and Qt6 download signals; poll as a fallback."""
        if hasattr(download, "downloadProgress"):
            download.downloadProgress.connect(
                lambda received, total, item=dl_item: self._update_download_status(received, total, item))
        def _sync_bytes(item=dl_item, req=download):
            try:
                recv = int(req.receivedBytes())
            except Exception:
                recv = item.received
            try:
                total = int(req.totalBytes())
            except Exception:
                total = item.total
            self._update_download_status(recv, total, item)
        if hasattr(download, "receivedBytesChanged"):
            download.receivedBytesChanged.connect(_sync_bytes)
        if hasattr(download, "totalBytesChanged"):
            download.totalBytesChanged.connect(_sync_bytes)
        if hasattr(download, "finished"):
            download.finished.connect(
                lambda item=dl_item, req=download: self._download_finished(item, req))
        if hasattr(download, "isFinishedChanged"):
            download.isFinishedChanged.connect(
                lambda item=dl_item, req=download: self._apply_download_state(item, req))
        if hasattr(download, "stateChanged"):
            download.stateChanged.connect(
                lambda *_args, item=dl_item, req=download: self._apply_download_state(item, req))
        QTimer.singleShot(0, lambda item=dl_item, req=download: self._apply_download_state(item, req))
        QTimer.singleShot(400, lambda item=dl_item, req=download: self._poll_download(item, req))

    def _poll_download(self, dl_item: DownloadItem, download):
        if dl_item._finalized:
            return
        self._apply_download_state(dl_item, download)
        if not dl_item._finalized:
            QTimer.singleShot(400, lambda item=dl_item, req=download: self._poll_download(item, req))

    def _apply_download_state(self, dl_item: DownloadItem, download=None):
        if dl_item._finalized:
            return
        req = download if download is not None else dl_item._request
        try:
            if req is not None:
                if hasattr(req, "receivedBytes"):
                    dl_item.received = int(req.receivedBytes())
                if hasattr(req, "totalBytes"):
                    dl_item.total = int(req.totalBytes())
        except Exception:
            pass
        name = ""
        finished = False
        try:
            if req is not None:
                state = req.state()
                name = getattr(state, "name", str(state))
                fin = getattr(req, "isFinished", None)
                if callable(fin):
                    finished = bool(fin())
                elif isinstance(fin, bool):
                    finished = fin
        except Exception:
            pass
        if "Cancel" in name:
            self._download_finished(dl_item, req)
            return
        if "Interrupt" in name:
            self._download_finished(dl_item, req)
            return
        if "Completed" in name or "Complete" in name:
            self._download_finished(dl_item, req)
            return
        if finished and "Progress" not in name and "Requested" not in name:
            self._download_finished(dl_item, req)
            return
        # File is fully on disk but Qt never sent a completion signal.
        try:
            if (dl_item.total > 0 and dl_item.received >= dl_item.total
                    and dl_item.path and os.path.isfile(dl_item.path)
                    and os.path.getsize(dl_item.path) >= dl_item.total):
                self._download_finished(dl_item, req)
                return
        except Exception:
            pass
        self._update_download_status(dl_item.received, dl_item.total, dl_item)

    def _update_download_status(self, received: int, total: int, dl_item: DownloadItem):
        if dl_item._finalized or dl_item.status != "Downloading":
            return
        dl_item.received = received
        dl_item.total = total
        if total > 0:
            pct = min(100, int(received * 100 / total))
            self._status_label.setText(
                f"Downloading {dl_item.filename}: {_format_bytes(received)} / {_format_bytes(total)} ({pct}%)")
            self._dl_btn.setToolTip(f"Downloads - {dl_item.filename} {pct}%")
        else:
            self._status_label.setText(
                f"Downloading {dl_item.filename}: {_format_bytes(received)}")

    def _download_finished(self, dl_item: DownloadItem, download=None):
        if dl_item._finalized:
            return
        status = "Complete"
        req = download if download is not None else dl_item._request
        try:
            if req is not None:
                state = req.state()
                name = getattr(state, "name", str(state))
                if "Cancel" in name:
                    status = "Cancelled"
                elif "Interrupt" in name:
                    status = "Interrupted"
        except Exception:
            pass
        if status == "Complete" and req is not None:
            try:
                if hasattr(req, "receivedBytes"):
                    dl_item.received = int(req.receivedBytes()) or dl_item.received
                if hasattr(req, "totalBytes"):
                    total = int(req.totalBytes())
                    if total > 0:
                        dl_item.total = total
            except Exception:
                pass
            if dl_item.total <= 0 and dl_item.received > 0:
                dl_item.total = dl_item.received
        dl_item.status = status
        dl_item._finalized = True
        dl_item._request = None
        if status == "Complete":
            self._status_label.setText(f"Download complete: {dl_item.filename}")
        else:
            self._status_label.setText(f"Download {status.lower()}: {dl_item.filename}")
        self._refresh_dl_button()
        _save_downloads(self._downloads)
        if self._dl_popup and self._dl_popup.isVisible():
            self._dl_popup.refresh()

    def _refresh_dl_button(self):
        active = sum(1 for d in self._downloads if d.status == "Downloading")
        if active:
            self._dl_btn.setText(f"\u2913 {active}")
            self._dl_btn.setToolTip(f"Downloads - {active} in progress")
        else:
            self._dl_btn.setText("\u2913")
            self._dl_btn.setToolTip("Downloads")

    def _toggle_downloads_popup(self):
        if self._dl_popup and self._dl_popup.isVisible():
            self._dl_popup.hide()
            return
        if self._dl_popup is None:
            self._dl_popup = DownloadsPopup(self)
        pos = self._dl_btn.mapToGlobal(QPoint(self._dl_btn.width() - 380, self._dl_btn.height()))
        if pos.x() < 8:
            pos.setX(8)
        self._dl_popup.popup_at(pos)

    def _show_downloads(self):
        self._toggle_downloads_popup()

    def _inject_ad_hider(self, page):
        """Inject ad blocking scripts - matches Ceprkac's InjectAdElementHider + InjectMainWorldBlocker."""
        try:
            url = page.url().toString()
            page_host = urlparse(url).hostname or ""
            page_host = page_host.lower()
        except Exception:
            page_host = ""

        # YouTube gets its own dedicated ad blocking
        is_youtube = page_host in ("www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com") \
            or page_host.endswith(".youtube.com") or page_host.endswith(".youtube-nocookie.com")

        if is_youtube:
            page.runJavaScript(YOUTUBE_AD_BLOCKER_JS)
            page.runJavaScript(YOUTUBE_MAIN_WORLD_INJECTOR_JS)
            return

        # GSecurity-Ad-Shield scripts (plus Pac lists) are installed on the
        # profile and run on every page. Do not pile on the old element hider.
        if self._gsec_dir:
            return

        if _is_whitelisted(page_host):
            return
        page.runJavaScript(AD_ELEMENT_HIDER_JS)

    # === Credential-offer suppression (Ceprkac parity) ===
    def _credential_host(self, url: str) -> str:
        try:
            return (urlparse(url).hostname or url).lower()
        except Exception:
            return (url or "").lower()

    def _is_credential_offer_dismissed(self, url: str) -> bool:
        """Permanent dismiss ('Type password manually') OR a live 20s cooldown
        from an accidental click-away close."""
        host = self._credential_host(url)
        if not host:
            return False
        if host in self._dismissed_credential_hosts:
            return True
        until = self._recently_closed_credential_hosts.get(host)
        if until is not None:
            if time.time() < until:
                return True
            del self._recently_closed_credential_hosts[host]
        return False

    def _dismiss_credential_offer(self, url: str):
        host = self._credential_host(url)
        if host:
            self._dismissed_credential_hosts.add(host)

    def _temporarily_suppress_credential_offer(self, url: str):
        host = self._credential_host(url)
        if host:
            self._recently_closed_credential_hosts[host] = time.time() + 20

    def _try_autofill(self, tab: ChromeTab):
        if not self._passwords.passwords:
            return

        try:
            page_url = tab.url or ""
            domain = urlparse(page_url).hostname
            if not domain:
                return
            domain = domain.lower()
        except Exception:
            return

        # Per-URL de-dupe (Ceprkac 0.8.0): if a loop is already running for THIS
        # exact URL, skip. A genuinely different URL (identifier -> password step)
        # always proceeds even mid-loop; the older loop self-cancels when it sees
        # the URL move on. A same-URL non-running attempt is 3s-debounced.
        now = time.time()
        if tab.autofill_in_progress and tab.last_autofill_url == page_url:
            return
        if (not tab.autofill_in_progress and tab.last_autofill_url == page_url
                and now - tab.last_autofill_attempt < 3):
            return

        # Phone 2FA / OAuth consent pages often have leftover password fields.
        # Filling them submits a malformed request (Google HTTP 400) even though
        # the authenticator tap already signed the user in.
        if _is_idp_challenge_url(page_url):
            return

        matches = self._passwords.get_matches(domain)
        if not matches:
            return

        # User chose "type manually" (or accidental click-away cooldown) for this host.
        if self._is_credential_offer_dismissed(page_url):
            return

        path_lower = urlparse(page_url).path.lower() + (urlparse(page_url).query or "").lower()
        is_login_page = any(kw in path_lower for kw in
                            ["login", "signin", "sign-in", "auth", "account", "sso",
                             "register", "signup", "sign-up", "challenge", "pwd",
                             "identifier", "session", "oauth", "passwd"])

        # Claim this URL up front with a fresh token so a concurrent
        # loadFinished/urlChanged pair does not run two loops against the same page.
        tab.last_autofill_attempt = now
        tab.last_autofill_url = page_url
        tab.autofill_in_progress = True
        tab.autofill_token += 1
        self._autofill_attempt(tab, matches, is_login_page, 0, domain,
                               page_url, tab.autofill_token)

    def _autofill_attempt(self, tab: ChromeTab, matches: list[SavedCredential],
                          is_login_page: bool, attempt: int, domain: str,
                          page_url: str, token: int):
        # Self-cancel if superseded by a newer invocation, or the page navigated on.
        if tab.autofill_token != token:
            return
        if tab not in self._tabs or tab.web_view is None or tab.url != page_url:
            if tab.autofill_token == token:
                tab.autofill_in_progress = False
            return
        if attempt >= 8:
            if tab.autofill_token == token:
                tab.autofill_in_progress = False
            return
        delay = 400 if attempt == 0 else (600 + attempt * 450)

        def do_check():
            # Tab-alive + still-current guard
            if tab.autofill_token != token:
                return
            if tab not in self._tabs or tab.web_view is None or tab.url != page_url:
                if tab.autofill_token == token:
                    tab.autofill_in_progress = False
                return
            if not tab.web_view.page():
                if tab.autofill_token == token:
                    tab.autofill_in_progress = False
                return
            tab.web_view.page().runJavaScript(CHECK_LOGIN_FIELDS_JS, 0,
                lambda result: self._handle_field_check(
                    tab, matches, is_login_page, attempt, domain, page_url, token, result))

        QTimer.singleShot(delay, do_check)

    def _handle_field_check(self, tab: ChromeTab, matches: list[SavedCredential],
                            is_login_page: bool, attempt: int, domain: str,
                            page_url: str, token: int, result):
        # Self-cancel / tab-alive / still-current guards
        if tab.autofill_token != token:
            return
        if tab not in self._tabs or tab.web_view is None or tab.url != page_url:
            if tab.autofill_token == token:
                tab.autofill_in_progress = False
            return
        field_status = result.strip('"') if isinstance(result, str) else str(result)

        if field_status == "none":
            self._autofill_attempt(tab, matches, is_login_page, attempt + 1,
                                   domain, page_url, token)
            return

        # From here we are done with the loop for this page.
        if tab.autofill_token == token:
            tab.autofill_in_progress = False

        if field_status == "pwonly":
            # A password field present means this is a login step regardless of the
            # URL path - this is what makes Google's separate password page work.
            if len(matches) == 1:
                tab.web_view.page().runJavaScript(_make_fill_password_js(matches[0].password))
                self._status_label.setText(f"Auto-filled password for {domain}")
            else:
                self._show_credential_picker(tab, matches, password_only=True)
            return

        if field_status == "both":
            if len(matches) == 1:
                tab.web_view.page().runJavaScript(
                    _make_fill_js(matches[0].username, matches[0].password))
                self._status_label.setText(f"Auto-filled credentials for {domain}")
            else:
                self._show_credential_picker(tab, matches)
            return

        if field_status == "useronly":
            # Auto-fill silently only on login-like paths with a single match;
            # otherwise always show the picker.
            if len(matches) == 1 and is_login_page:
                tab.web_view.page().runJavaScript(_make_fill_username_js(matches[0].username))
                self._status_label.setText(f"Filled username for {domain} (continue to password)")
            else:
                self._show_credential_picker(tab, matches)

    def _show_credential_picker(self, tab: ChromeTab, matches: list[SavedCredential],
                                password_only: bool = False):
        if not matches:
            return
        page_url = tab.url or ""
        if self._is_credential_offer_dismissed(page_url):
            return
        # Non-modal QMenu (Ceprkac never uses a modal dialog here so the page stays
        # usable). Track whether the user actually chose something.
        state = {"chose": False}
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
            f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
        header = menu.addAction("Choose a password:" if password_only else "Choose an account:")
        header.setEnabled(False)
        menu.addSeparator()
        for cred in matches:
            host = cred.url
            try:
                host = urlparse(cred.url).hostname or cred.url
            except Exception:
                pass
            action = menu.addAction(f"{cred.username}  ({host})")
            action.triggered.connect(
                lambda checked=False, c=cred: self._fill_selected_credential(
                    tab, c, password_only, state))
        menu.addSeparator()
        dismiss = menu.addAction("Type password manually...")
        dismiss.triggered.connect(lambda checked=False: self._on_credential_dismiss(tab, page_url, state))

        def on_close():
            # Closed without picking -> 20s cooldown so an accidental click-away
            # does not permanently hide the picker for this session.
            if not state["chose"]:
                self._temporarily_suppress_credential_offer(page_url)
        menu.aboutToHide.connect(on_close)

        menu.exec(self._web_panel.mapToGlobal(QPoint(max(8, self._web_panel.width() // 2 - 80), 10)))

    def _on_credential_dismiss(self, tab: ChromeTab, page_url: str, state: dict):
        state["chose"] = True
        self._dismiss_credential_offer(page_url)
        if tab.web_view:
            tab.web_view.setFocus()

    def _fill_selected_credential(self, tab: ChromeTab, cred: SavedCredential,
                                  password_only: bool = False, state: dict = None):
        if state is not None:
            state["chose"] = True
        if tab.web_view and tab.web_view.page():
            try:
                if password_only:
                    tab.web_view.page().runJavaScript(_make_fill_password_js(cred.password))
                    self._status_label.setText(f"Filled password for {cred.username}")
                else:
                    tab.web_view.page().runJavaScript(_make_fill_js(cred.username, cred.password))
                    self._status_label.setText(f"Filled credentials for {cred.username}")
            except Exception as ex:
                self._status_label.setText(f"Autofill error: {ex}")

    # === Save-password prompt (Ceprkac OfferSavePassword) ===
    def _offer_save_password(self, url: str, username: str, password: str):
        if not password:
            return
        if not url:
            tab = self._active_tab()
            url = tab.url if tab else ""
        if not url:
            return
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            return
        if not host:
            return
        # Already saved identical credentials? Do nothing.
        existing = self._passwords.find_exact(host.lower(), username)
        if existing is not None and existing.password == password:
            return
        who = f" ({username})" if username else ""
        if existing is None:
            msg = f"Save password for {host}{who}?"
        else:
            msg = f"Update saved password for {host}{who}?"
        reply = QMessageBox.question(
            self, "GBrowser", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._passwords.add_or_update(url, username, password)
        self._status_label.setText(f"Password saved for {host}.")

    def _manage_passwords(self):
        dlg = CredentialManagerDialog(self._passwords, self)
        dlg.exec()
        self._status_label.setText("Passwords updated.")

    # === Checkout autofill: payment methods + addresses (Ceprkac 0.7.8) ===
    def _try_checkout_autofill(self, tab: ChromeTab):
        if not self._cards.cards and not self._addresses.addresses:
            return
        page_url = tab.url or ""
        if not page_url or page_url.startswith("about:"):
            return
        now = time.time()
        # Per-URL de-dupe mirroring the password path: skip if a loop is already
        # running for this URL, or a same-URL non-running attempt within 3s.
        if tab.checkout_in_progress and tab.last_checkout_url == page_url:
            return
        if (not tab.checkout_in_progress and tab.last_checkout_url == page_url
                and now - tab.last_checkout_attempt < 3):
            return
        tab.last_checkout_attempt = now
        tab.last_checkout_url = page_url
        tab.checkout_in_progress = True
        tab.checkout_token += 1
        looks_checkout = any(k in page_url.lower() for k in
                             ("checkout", "payment", "billing", "shipping", "address",
                              "cart", "order", "/pay"))
        self._checkout_attempt(tab, page_url, looks_checkout, 0, tab.checkout_token)

    def _checkout_attempt(self, tab: ChromeTab, page_url: str, looks_checkout: bool,
                          attempt: int, token: int):
        if tab.checkout_token != token:
            return
        if tab not in self._tabs or tab.web_view is None or tab.url != page_url or attempt >= 4:
            if tab.checkout_token == token:
                tab.checkout_in_progress = False
            return
        delay = 700 + attempt * 500

        def do_check():
            if tab.checkout_token != token:
                return
            if tab not in self._tabs or tab.web_view is None or tab.url != page_url:
                if tab.checkout_token == token:
                    tab.checkout_in_progress = False
                return
            page = tab.web_view.page()
            if not page:
                if tab.checkout_token == token:
                    tab.checkout_in_progress = False
                return
            page.runJavaScript(CHECKOUT_DETECT_JS, 0,
                lambda res: self._handle_checkout_check(tab, page_url, looks_checkout, attempt, token, res))

        QTimer.singleShot(delay, do_check)

    def _handle_checkout_check(self, tab: ChromeTab, page_url: str, looks_checkout: bool,
                               attempt: int, token: int, result):
        if tab.checkout_token != token:
            return
        if tab not in self._tabs or tab.web_view is None or tab.url != page_url:
            if tab.checkout_token == token:
                tab.checkout_in_progress = False
            return
        status = result.strip('"') if isinstance(result, str) else str(result or "")
        has_card = status.startswith("card")
        has_addr = status.endswith("addr")
        if not has_card and not has_addr:
            if looks_checkout:
                self._checkout_attempt(tab, page_url, looks_checkout, attempt + 1, token)
            elif tab.checkout_token == token:
                tab.checkout_in_progress = False
            return
        # Found fields -> loop is done.
        if tab.checkout_token == token:
            tab.checkout_in_progress = False
        page = tab.web_view.page()
        filled = False
        if has_addr and self._addresses.addresses:
            if len(self._addresses.addresses) == 1:
                page.runJavaScript(_make_fill_address_js(self._addresses.addresses[0]))
                filled = True
            else:
                self._show_address_picker(tab)
        if has_card and self._cards.cards:
            if len(self._cards.cards) == 1:
                page.runJavaScript(_make_fill_card_js(self._cards.cards[0]))
                filled = True
            else:
                self._show_card_picker(tab)
        if filled:
            self._status_label.setText("Autofilled saved details.")

    def _show_card_picker(self, tab: ChromeTab):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
            f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
        header = menu.addAction("Choose a card:")
        header.setEnabled(False)
        menu.addSeparator()
        for card in self._cards.cards:
            menu.addAction(card.display,
                           lambda checked=False, c=card: self._fill_card(tab, c))
        menu.exec(self._web_panel.mapToGlobal(QPoint(max(8, self._web_panel.width() // 2 - 100), 10)))

    def _fill_card(self, tab: ChromeTab, card: SavedCard):
        if tab.web_view and tab.web_view.page():
            tab.web_view.page().runJavaScript(_make_fill_card_js(card))
            self._status_label.setText(f"Filled card ---- {card.last4}")

    def _show_address_picker(self, tab: ChromeTab):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
            f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
        header = menu.addAction("Choose an address:")
        header.setEnabled(False)
        menu.addSeparator()
        for addr in self._addresses.addresses:
            menu.addAction(addr.display,
                           lambda checked=False, a=addr: self._fill_address(tab, a))
        menu.exec(self._web_panel.mapToGlobal(QPoint(max(8, self._web_panel.width() // 2 - 100), 10)))

    def _fill_address(self, tab: ChromeTab, addr: SavedAddress):
        if tab.web_view and tab.web_view.page():
            tab.web_view.page().runJavaScript(_make_fill_address_js(addr))
            self._status_label.setText(f"Filled address for {addr.full_name}")

    def _manage_cards(self):
        dlg = CardManagerDialog(self._cards, self)
        dlg.exec()

    def _manage_addresses(self):
        dlg = AddressManagerDialog(self._addresses, self)
        dlg.exec()

    def _set_as_default_browser(self):
        if sys.platform != "win32":
            QMessageBox.information(self, "GBrowser",
                                    "Default-browser registration is only supported on Windows.")
            return
        ok = _register_browser()
        if ok:
            _open_default_apps_settings()
            self._status_label.setText("Registered - confirm GBrowser as default in Settings.")
        else:
            QMessageBox.warning(self, "GBrowser", "Could not register GBrowser as a browser.")

    def open_external_url(self, url: str):
        """Open a URL forwarded from a second launch (single-instance)."""
        if not url:
            self.raise_()
            self.activateWindow()
            return
        self._add_new_tab(url)
        self.raise_()
        self.activateWindow()

    # === Context menu (right-click image/video/link search - Ceprkac parity) ===
    def _search_host(self) -> str:
        try:
            return urlparse(self._search_template.format("x")).hostname.lower()
        except Exception:
            return ""

    def _search_engine_name(self) -> str:
        for name, _, search in SEARCH_ENGINES:
            if search.lower() == self._search_template.lower():
                return name
        host = self._search_host().replace("www.", "")
        return host or "web"

    def _build_text_search_url(self, query: str) -> str:
        return self._search_template.format(quote_plus(query))

    def _build_image_search_url(self, image_url: str) -> str:
        host = self._search_host()
        enc = quote_plus(image_url)
        if "google." in host:
            return "https://lens.google.com/uploadbyurl?url=" + enc
        if "bing." in host:
            return "https://www.bing.com/images/search?q=imgurl:" + enc + "&view=detailv2&iss=sbi"
        if "yandex." in host:
            return "https://yandex.com/images/search?rpt=imageview&url=" + enc
        return "https://lens.google.com/uploadbyurl?url=" + enc

    def _build_video_search_url(self, video_url: str) -> str:
        host = self._search_host()
        enc = quote_plus(video_url)
        if "google." in host:
            return "https://www.google.com/search?q=" + enc + "&tbm=vid"
        if "bing." in host:
            return "https://www.bing.com/videos/search?q=" + enc
        return self._build_text_search_url(video_url)

    def _build_context_menu(self, view: "BrowserWebView", raw):
        """Build the right-click menu from the JS-captured target (Ceprkac AddSearchMenuItems)."""
        # The tab may have been closed during the async runJavaScript hop; touching a
        # deleted view/page would be a use-after-free.
        if not any(t.web_view is view for t in self._tabs):
            return
        kind, src, href, sel = "page", "", "", ""
        try:
            if raw and raw != "null":
                data = json.loads(raw)
                kind = data.get("kind", "page")
                src = data.get("src", "") or ""
                href = data.get("href", "") or ""
                sel = data.get("sel", "") or ""
        except Exception:
            pass

        page = view.page()
        engine = self._search_engine_name()
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
            f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}"
            f"QMenu::separator {{ background: rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); height: 1px; }}")

        added = False

        def add_open(label: str, url: str):
            nonlocal added
            if not url:
                return
            menu.addAction(label, lambda checked=False, u=url: self._add_new_tab(u))
            added = True

        def add_copy(label: str, text: str):
            nonlocal added
            if not text:
                return
            menu.addAction(label, lambda checked=False, t=text: self._copy_to_clipboard(t))
            added = True

        sel = (sel or "").strip()
        if sel:
            shown = (sel[:40] + "...") if len(sel) > 40 else sel
            add_open(f'Search {engine} for "{shown}"', self._build_text_search_url(sel))

        media_uri = src or href
        is_image = (kind == "image" or _looks_like_image_url(src) or _looks_like_image_url(href)
                    or _looks_like_image_host(src) or _looks_like_image_host(href))
        is_video = (kind == "video" or _looks_like_video_url(src) or _looks_like_video_url(href))

        if is_image and media_uri:
            add_open("Search image with Google Lens",
                     "https://lens.google.com/uploadbyurl?url=" + quote_plus(media_uri))
            if "google." not in self._search_host():
                add_open(f"Search {engine} for this image", self._build_image_search_url(media_uri))
            add_open("Open image in new tab", media_uri)
            add_copy("Copy image address", media_uri)
        elif is_video and media_uri:
            add_open(f"Search {engine} for this video", self._build_video_search_url(media_uri))
            add_open("Open media in new tab", media_uri)
            add_copy("Copy media address", media_uri)
        elif href and not sel:
            add_open("Open link in new tab", href)
            add_copy("Copy link address", href)

        if added:
            menu.addSeparator()

        # Standard navigation / edit actions from the page itself.
        if page:
            for act_enum in (QWebEnginePage.WebAction.Back, QWebEnginePage.WebAction.Forward,
                             QWebEnginePage.WebAction.Reload):
                act = page.action(act_enum)
                if act and act.isEnabled():
                    menu.addAction(act)
            menu.addSeparator()
            for act_enum in (QWebEnginePage.WebAction.Copy, QWebEnginePage.WebAction.Paste,
                             QWebEnginePage.WebAction.SelectAll):
                act = page.action(act_enum)
                if act and act.isEnabled():
                    menu.addAction(act)

        if menu.isEmpty():
            return
        menu.exec(QCursor.pos())

    def _copy_to_clipboard(self, text: str):
        try:
            QApplication.clipboard().setText(text)
            self._status_label.setText("Copied.")
        except Exception:
            pass

    def _toggle_bookmark(self):
        tab = self._active_tab()
        if not tab:
            return
        url = tab.url
        if not url:
            return
        if _remove_bookmark(self._bookmarks, url):
            _save_bookmarks(self._bookmarks)
            self._refresh_bookmarks_bar()
            self._bookmark_btn.setText("\u2606")
            self._status_label.setText("Bookmark removed.")
        else:
            self._bookmarks.insert(0, BookmarkNode("link", tab.title or _display_title(url), url))
            _save_bookmarks(self._bookmarks)
            self._refresh_bookmarks_bar()
            self._bookmark_btn.setText("\u2605")
            self._status_label.setText("Bookmark added.")
        self._update_completer_data()

    def _bookmark_hash(self) -> int:
        """Compute a simple hash of bookmark list for incremental update check (#15)."""
        h = len(self._bookmarks)
        for n in self._bookmarks:
            h = h * 31 + hash(n.title) + hash(getattr(n, 'href', ''))
        return h

    def _refresh_bookmarks_bar(self):
        # Incremental update: skip rebuild if bookmarks haven't changed (#15)
        new_hash = self._bookmark_hash()
        if new_hash == self._last_bookmark_hash:
            return
        self._last_bookmark_hash = new_hash

        while self._bm_layout.count():
            item = self._bm_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        bm_btn_style = (f"QPushButton {{ background: rgb({Theme.AddressBox.red()},{Theme.AddressBox.green()},{Theme.AddressBox.blue()});"
                        f"color: white; border: none; border-radius: 4px; padding: 2px 8px; font-size: 11px; }}"
                        f"QPushButton:hover {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")

        # Calculate how many bookmarks fit before overflow (#10)
        max_bar_width = max(200, self.width() - 80)
        used_width = 0
        visible_count = 0
        avg_btn_width = 100  # approximate width per bookmark button

        for node in self._bookmarks:
            est_width = min(len(node.title), 30) * 7 + 20  # rough estimate
            if used_width + est_width > max_bar_width and visible_count > 0:
                break
            used_width += est_width
            visible_count += 1

        for i, node in enumerate(self._bookmarks[:visible_count]):
            if node.type == "folder":
                btn = QPushButton(node.title[:30])
                btn.setStyleSheet(bm_btn_style)
                menu = QMenu(btn)
                menu.setStyleSheet(
                    f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
                    f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
                self._add_children_to_menu(menu, node.children)
                btn.setMenu(menu)
                self._bm_layout.addWidget(btn)
            else:
                btn = QPushButton(node.title[:30])
                btn.setStyleSheet(bm_btn_style)
                href = node.href
                btn.clicked.connect(lambda checked, u=href: self._navigate_tab(self._active_tab(), u) if self._active_tab() else None)
                self._bm_layout.addWidget(btn)

        # Overflow button (>>) if there are more bookmarks (#10)
        if visible_count < len(self._bookmarks):
            overflow_btn = QPushButton("\u00bb")
            overflow_btn.setStyleSheet(bm_btn_style)
            overflow_btn.setToolTip("More bookmarks")
            overflow_menu = QMenu(overflow_btn)
            overflow_menu.setStyleSheet(
                f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
                f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}")
            for node in self._bookmarks[visible_count:]:
                if node.type == "folder":
                    sub = overflow_menu.addMenu(node.title[:40])
                    sub.setStyleSheet(overflow_menu.styleSheet())
                    self._add_children_to_menu(sub, node.children)
                else:
                    href = node.href
                    action = overflow_menu.addAction(node.title[:40])
                    action.triggered.connect(lambda checked, u=href: self._navigate_tab(self._active_tab(), u) if self._active_tab() else None)
            overflow_btn.setMenu(overflow_menu)
            self._bm_layout.addWidget(overflow_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._bm_layout.addWidget(spacer)

    def _add_children_to_menu(self, menu: QMenu, children: list[BookmarkNode]):
        for child in children:
            if child.type == "folder":
                sub = menu.addMenu(child.title)
                sub.setStyleSheet(menu.styleSheet())
                self._add_children_to_menu(sub, child.children)
            else:
                href = child.href
                action = menu.addAction(child.title)
                action.triggered.connect(lambda checked, u=href: self._navigate_tab(self._active_tab(), u) if self._active_tab() else None)

    def _import_bookmarks_html(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Bookmarks", "",
                                              "Bookmark Files (*.html *.htm);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                html_text = f.read()
            parsed = _parse_bookmarks_html(html_text)
            self._bookmarks.clear()
            self._bookmarks.extend(parsed)
            _save_bookmarks(self._bookmarks)
            self._last_bookmark_hash = 0  # Force rebuild
            self._refresh_bookmarks_bar()
            self._update_completer_data()
            count = _count_links(self._bookmarks)
            self._status_label.setText(f"Imported {count} bookmarks.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Import failed:\n{e}")

    def _export_bookmarks_html(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Bookmarks", "bookmarks.html",
                                              "Bookmark File (*.html)")
        if not path:
            return
        try:
            _export_bookmarks_html(self._bookmarks, path)
            count = _count_links(self._bookmarks)
            self._status_label.setText(f"Exported {count} bookmarks.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Export failed:\n{e}")

    def _clear_bookmarks(self):
        reply = QMessageBox.question(self, "Confirm", "Clear all bookmarks?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._bookmarks.clear()
            _save_bookmarks(self._bookmarks)
            self._last_bookmark_hash = 0
            self._refresh_bookmarks_bar()
            self._update_completer_data()
            self._status_label.setText("Bookmarks cleared.")

    def _add_to_history(self, url: str):
        if not url:
            return
        self._history = [h for h in self._history if h.lower() != url.lower()]
        self._history.append(url)
        if len(self._history) > 100:
            self._history = self._history[-100:]
        _save_history(self._history)
        self._update_completer_data()

    def _clear_history(self):
        reply = QMessageBox.question(self, "Confirm", "Clear all history?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._history.clear()
            _save_history(self._history)
            self._update_completer_data()
            self._status_label.setText("History cleared.")

    def _show_history_dialog(self):
        """Show history dialog (#9)."""
        dlg = HistoryDialog(self._history, self)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            url = dlg.selected_url()
            if url:
                tab = self._active_tab()
                if tab:
                    self._navigate_tab(tab, url)
                else:
                    self._add_new_tab(url)
        elif result == 2:  # Clear
            self._history.clear()
            _save_history(self._history)
            self._update_completer_data()
            self._status_label.setText("History cleared.")

    def _import_passwords_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Passwords (Chrome/Edge CSV)",
                                              "", "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        try:
            count = self._passwords.import_csv(path)
            self._status_label.setText(f"Imported {count} passwords.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Import failed:\n{e}")

    def _clear_passwords(self):
        reply = QMessageBox.question(self, "Confirm", "Clear all saved passwords?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._passwords.clear()
            self._status_label.setText("Passwords cleared.")

    def _show_search_engine_picker(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose Your Search Engine")
        dlg.setFixedSize(360, 340)
        dlg.setStyleSheet(
            f"QDialog {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()}); color: white; }}")

        layout = QVBoxLayout(dlg)
        label = QLabel("Select your default search engine:")
        label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(label)

        listbox = QListWidget()
        listbox.setStyleSheet(
            f"QListWidget {{ background: rgb({Theme.TitleBar.red()},{Theme.TitleBar.green()},{Theme.TitleBar.blue()});"
            f"color: white; border: 1px solid rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); }}"
            f"QListWidget::item:selected {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()}); color: black; }}")
        listbox.setFont(QFont("Segoe UI", 11))
        for name, _, _ in SEARCH_ENGINES:
            listbox.addItem(name)
        listbox.setCurrentRow(0)
        layout.addWidget(listbox)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(
            f"QPushButton {{ background: rgb({Theme.Accent.red()},{Theme.Accent.green()},{Theme.Accent.blue()});"
            f"color: black; border: none; border-radius: 4px; padding: 8px 24px; font-size: 13px; }}")
        ok_btn.clicked.connect(dlg.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignRight)

        dlg.exec()
        if listbox.currentRow() >= 0:
            idx = listbox.currentRow()
            _, home, search = SEARCH_ENGINES[idx]
            self._home_url = home
            self._search_template = search
            _save_settings(self._home_url, self._search_template)

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: rgb({Theme.ActiveTab.red()},{Theme.ActiveTab.green()},{Theme.ActiveTab.blue()});"
            f"color: white; }} QMenu::item:selected {{ background: rgb({Theme.TabHover.red()},{Theme.TabHover.green()},{Theme.TabHover.blue()}); }}"
            f"QMenu::separator {{ background: rgb({Theme.Border.red()},{Theme.Border.green()},{Theme.Border.blue()}); height: 1px; }}")

        menu.addAction("New Tab (Ctrl+T)", lambda: self._add_new_tab(self._home_url))
        menu.addAction("Duplicate Tab (Ctrl+Shift+K)", self._duplicate_tab)
        menu.addAction("Restore Closed Tab (Ctrl+Shift+T)", self._restore_closed_tab)
        menu.addSeparator()
        menu.addAction("Find in Page (Ctrl+F)", self._toggle_find_bar)
        menu.addSeparator()
        menu.addAction("Add Bookmark (Ctrl+D)", self._toggle_bookmark)
        menu.addAction("Import Bookmarks...", self._import_bookmarks_html)
        menu.addAction("Export Bookmarks...", self._export_bookmarks_html)
        menu.addAction("Clear Bookmarks", self._clear_bookmarks)
        menu.addSeparator()
        menu.addAction("View History...", self._show_history_dialog)
        menu.addAction("Clear History", self._clear_history)
        menu.addSeparator()
        menu.addAction("Downloads...", self._show_downloads)
        menu.addSeparator()
        menu.addAction("Manage Passwords...", self._manage_passwords)
        menu.addAction("Import Passwords (CSV)...", self._import_passwords_csv)
        menu.addAction("Clear Saved Passwords", self._clear_passwords)
        menu.addSeparator()
        menu.addAction("Payment Methods...", self._manage_cards)
        menu.addAction("Addresses...", self._manage_addresses)
        menu.addSeparator()
        menu.addAction("DevTools (Ctrl+I)", self._open_devtools)
        menu.addAction("Change Search Engine...", self._show_search_engine_picker)
        menu.addAction("Set as Default Browser...", self._set_as_default_browser)
        menu.addSeparator()
        menu.addAction("Exit", self.close)

        menu.exec(self._menu_btn.mapToGlobal(QPoint(0, self._menu_btn.height())))

    def _open_devtools(self):
        tab = self._active_tab()
        if tab and tab.web_view and tab.web_view.page():
            inspector = QWebEngineView()
            tab.web_view.page().setDevToolsPage(inspector.page())
            inspector.setWindowTitle("DevTools")
            inspector.resize(900, 600)
            inspector.show()
            if not hasattr(self, '_devtools_windows'):
                self._devtools_windows = []
            self._devtools_windows.append(inspector)

    def _on_address_enter(self):
        text = self._address.text().strip()
        if not text:
            return
        url = text
        if not text.startswith(("http://", "https://", "file://")):
            if "." in text and " " not in text:
                url = "https://" + text
            else:
                url = self._search_template.format(quote_plus(text))
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.focus_omnibox = False
            tab.web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            tab.url = url
            tab.web_view.load(_to_qurl(url))

    def _go_back(self):
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.web_view.back()

    def _go_forward(self):
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.web_view.forward()

    def _reload(self):
        tab = self._active_tab()
        if tab and tab.web_view:
            tab.web_view.reload()

    def _navigate_tab(self, tab: ChromeTab | None, url: str):
        if tab and tab.web_view:
            tab.url = url
            tab.web_view.load(_to_qurl(url))

    def _update_bookmark_star(self):
        tab = self._active_tab()
        if tab and tab.url and _bookmark_exists(self._bookmarks, tab.url):
            self._bookmark_btn.setText("\u2605")
        else:
            self._bookmark_btn.setText("\u2606")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounced bookmark bar overflow recalculation on resize
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._on_resize_done)
        self._resize_timer.start(150)

    def _on_resize_done(self):
        self._last_bookmark_hash = 0
        self._refresh_bookmarks_bar()

    def closeEvent(self, event):
        try:
            g = self.geometry()
            cfg = {
                "geometry": {
                    "x": g.x(), "y": g.y(),
                    "width": g.width(), "height": g.height(),
                    "maximized": self.isMaximized()
                }
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
        try:
            if getattr(self, "_module_cleaner", None):
                self._module_cleaner.stop()
        except Exception:
            pass
        super().closeEvent(event)


def _resource_path(filename: str) -> str:
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        path = os.path.join(base, filename)
        if os.path.exists(path):
            return path
        path = os.path.join(os.path.dirname(sys.executable), filename)
        if os.path.exists(path):
            return path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


# === DEFAULT-BROWSER REGISTRATION (Windows, ported from BrowserRegistration.cs) ===
_APP_NAME = "GBrowser"
_URL_PROGID = "GBrowserURL"
_HTML_PROGID = "GBrowserHTML"
_URL_PROTOCOLS = ("http", "https")
_HTML_EXTS = (".htm", ".html", ".shtml", ".xhtml", ".xht", ".mht", ".mhtml")
_SINGLE_INSTANCE_KEY = "GBrowser_SingleInstance"


def _exe_launch_command() -> tuple[str, str]:
    """Return (command_with_arg, open_command) for the registry, handling both a
    frozen .exe and a `python GBrowser.py` dev run."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}" "%1"', f'"{exe}"'
    exe = sys.executable  # python
    script = os.path.abspath(__file__)
    return f'"{exe}" "{script}" "%1"', f'"{exe}" "{script}"'


def _register_browser() -> bool:
    """Write StartMenuInternet / ProgId / RegisteredApplications entries under HKCU
    so GBrowser appears in Windows 'Default apps'. Returns True on success."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except Exception:
        return False
    cmd, open_cmd = _exe_launch_command()
    icon = _resource_path("GBrowser.ico") + ",0"

    def set_val(root, path, name, value):
        with winreg.CreateKey(root, path) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    try:
        hkcu = winreg.HKEY_CURRENT_USER
        root = r"Software\Clients\StartMenuInternet\GBrowser"
        set_val(hkcu, root, "", _APP_NAME)
        set_val(hkcu, root, "LocalizedString", _APP_NAME)
        set_val(hkcu, root + r"\DefaultIcon", "", icon)
        set_val(hkcu, root + r"\shell\open\command", "", open_cmd)
        caps = root + r"\Capabilities"
        set_val(hkcu, caps, "ApplicationName", _APP_NAME)
        set_val(hkcu, caps, "ApplicationIcon", icon)
        set_val(hkcu, caps, "ApplicationDescription", "GBrowser web browser")
        set_val(hkcu, root + r"\Capabilities\StartMenu", "StartMenuInternet", _APP_NAME)
        for p in _URL_PROTOCOLS:
            set_val(hkcu, caps + r"\URLAssociations", p, _URL_PROGID)
        for ext in _HTML_EXTS:
            set_val(hkcu, caps + r"\FileAssociations", ext, _HTML_PROGID)
        set_val(hkcu, caps + r"\MimeAssociations", "text/html", _HTML_PROGID)

        # ProgIds
        for progid, friendly, is_url in (
            (_URL_PROGID, "GBrowser URL", True),
            (_HTML_PROGID, "GBrowser HTML Document", False),
        ):
            base = r"Software\Classes\\" + progid
            set_val(hkcu, base, "", friendly)
            if is_url:
                set_val(hkcu, base, "URL Protocol", "")
            set_val(hkcu, base + r"\DefaultIcon", "", icon)
            set_val(hkcu, base + r"\shell\open\command", "", cmd)

        set_val(hkcu, r"Software\RegisteredApplications", _APP_NAME,
                r"Software\Clients\StartMenuInternet\GBrowser\Capabilities")

        # Notify the shell that associations changed.
        try:
            from ctypes import windll
            windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _open_default_apps_settings():
    if sys.platform != "win32":
        return
    for target in (f"ms-settings:defaultapps?registeredAppUser={_APP_NAME}",
                   "ms-settings:defaultapps"):
        try:
            os.startfile(target)
            return
        except Exception:
            continue


if __name__ == "__main__":
    # QTWEBENGINE_CHROMIUM_FLAGS is set at import time (before QtWebEngine loads).

    # Note: GPU acceleration is enabled by default for best performance.
    # If you encounter crashes in VMs or headless environments, uncomment:
    # os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

    # Parse CLI: --register-browser registers and exits; other non-flag args are URLs.
    _startup_urls: list[str] = []
    _do_register = False
    for _a in sys.argv[1:]:
        s = (_a or "").strip().strip('"')
        if not s:
            continue
        if s.lower() in ("--register-browser", "/register"):
            _do_register = True
        elif s.startswith("-") or s.startswith("/"):
            continue
        else:
            _startup_urls.append(s)

    if _do_register:
        _register_browser()
        _open_default_apps_settings()
        sys.exit(0)

    # Ensure exceptions aren't silently swallowed by Qt
    def _excepthook(exc_type, exc_value, exc_tb):
        import traceback
        traceback.print_exception(exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook

    try:
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("Gorstak.GBrowser.0.6.1")
    except Exception:
        pass

    # Single-instance: if a GBrowser is already running, forward our URLs to it
    # over a local socket and exit (Ceprkac Mutex + NamedPipe parity).
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    _connected = False
    for _attempt in range(3):
        _probe = QLocalSocket()
        _probe.connectToServer(_SINGLE_INSTANCE_KEY)
        if _probe.waitForConnected(500):
            _connected = True
            payload = ("\n".join(_startup_urls) if _startup_urls else "").encode("utf-8")
            _probe.write(payload)
            _probe.flush()
            _probe.waitForBytesWritten(500)
            _probe.disconnectFromServer()
            break
        _probe.abort()
    if _connected:
        sys.exit(0)

    app = QApplication(sys.argv)

    ico_path = _resource_path("GBrowser.ico")
    if os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        geo = cfg.get("geometry", {})
    except Exception:
        geo = {}

    try:
        win = Browser()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFATAL: Browser failed to initialize: {e}", file=sys.stderr)
        sys.exit(1)

    if geo:
        if geo.get("maximized"):
            win.showMaximized()
        else:
            win.setGeometry(geo.get("x", 100), geo.get("y", 100),
                            geo.get("width", 1280), geo.get("height", 860))
            win.show()
    else:
        win.resize(1280, 860)
        win.show()

    try:
        win._module_cleaner = InjectedModuleCleaner(win)
        win._module_cleaner.start()
    except Exception:
        pass

    # Open any URLs passed on the command line (e.g. from the OS as default browser).
    for _u in _startup_urls:
        try:
            win.open_external_url(_u)
        except Exception:
            pass

    # Register GBrowser as a browser on first run so it shows up in Default apps.
    if sys.platform == "win32" and not os.path.exists(SETTINGS_FILE):
        try:
            _register_browser()
        except Exception:
            pass

    # Single-instance server: accept forwarded URLs from later launches.
    _server = QLocalServer()
    QLocalServer.removeServer(_SINGLE_INSTANCE_KEY)
    _server.listen(_SINGLE_INSTANCE_KEY)

    _conn_buffers: dict = {}

    def _on_new_connection():
        conn = _server.nextPendingConnection()
        if conn is None:
            return
        _conn_buffers[conn] = bytearray()

        def _read():
            try:
                _conn_buffers[conn].extend(bytes(conn.readAll()))
            except Exception:
                pass

        def _finish():
            # Parse the full accumulated payload once the sender disconnects, so a
            # payload split across packets is not truncated.
            data = bytes(_conn_buffers.pop(conn, b"")).decode("utf-8", "ignore")
            urls = [u.strip() for u in data.splitlines() if u.strip()]
            if not urls:
                win.raise_()
                win.activateWindow()
            else:
                for u in urls:
                    win.open_external_url(u)
            conn.deleteLater()

        conn.readyRead.connect(_read)
        conn.disconnected.connect(_finish)

    _server.newConnection.connect(_on_new_connection)

    sys.exit(app.exec())
