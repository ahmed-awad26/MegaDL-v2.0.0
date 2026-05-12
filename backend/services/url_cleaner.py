"""
MegaDL — services/url_cleaner.py
URL cleaning and ad/tracker redirect filter.
Detects and strips tracker parameters, shortener wrappers,
and known ad domain middlemen.
"""

import re
import logging
from urllib.parse import urlparse, urlencode, parse_qs

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger('megadl.url_cleaner')

# Known ad/tracker domains that wrap real download URLs
TRACKER_DOMAINS = {
    'adf.ly', 'sh.st', 'shorte.st', 'linkvertise.com', 'exe.io',
    'exe.app', 'sub2get.com', 'up-to-down.net', 'link-to.net',
    'dlupload.com', 'fc-lc.com', 'fc-lc.link', 'earnl.xyz',
    'shortconnect.com', 'boost.ink', 'mypixeles.com', 'topurl.cc',
    'budgeturls.com', 'urlz.net', 'urlshortx.com', 'shrinkearn.com',
    'tinyurl.com', 'bit.ly', 'goo.gl', 'ow.ly', 'tiny.cc',
    'bitly.com', 'cutt.ly', 'rebrand.ly', 'shorturl.at',
    'clck.ru', 'is.gd', 'soo.gd', 's.id',
}

# Tracking query params to strip from URLs
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'gclsrc', 'dclid', 'gbraid', 'wbraid',
    'msclkid', 'twclid', 'igshid', 'mc_cid', 'mc_eid',
    'ref', 'ref_src', 'ref_url', 'source', 'si',
    'feature', 'v', '_ga', '_gl', 'trk',
}

# Known ad network / tracker patterns in URLs
AD_PATTERNS = [
    r'doubleclick\.net',
    r'googleadservices\.com',
    r'googlesyndication\.com',
    r'facebook\.com/tr/?',
    r'amazon-adsystem\.com',
    r'outbrain\.com',
    r'taboola\.com',
    r'criteo\.com',
]


class UrlCleaner:
    """Static methods for URL cleaning and validation."""

    @staticmethod
    def is_tracker_url(url: str) -> bool:
        """Check if a URL is a known tracker/ad domain."""
        try:
            domain = urlparse(url).netloc.lower()
            for td in TRACKER_DOMAINS:
                if td in domain:
                    return True
            for pat in AD_PATTERNS:
                if re.search(pat, url, re.IGNORECASE):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def clean_url(url: str) -> str:
        """Remove tracking parameters from a URL."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            clean_params = {k: v for k, v in params.items()
                           if k.lower() not in TRACKING_PARAMS}
            if clean_params:
                new_query = urlencode(clean_params, doseq=True)
                return parsed._replace(query=new_query).geturl()
            elif parsed.query:
                return parsed._replace(query='').geturl()
            return url
        except Exception:
            return url

    @staticmethod
    def resolve_short_url(url: str, timeout: int = 5) -> str:
        """Try to follow a short URL redirect to get the real URL."""
        if not requests:
            return url
        try:
            resp = requests.head(url, allow_redirects=True, timeout=timeout,
                                 headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200 and len(resp.history) > 0:
                final = resp.url
                if final != url:
                    logger.info(f'[URL] Resolved short URL: {url} -> {final}')
                    return final
        except Exception:
            pass
        return url

    @staticmethod
    def is_downloadable(url: str) -> bool:
        """Check if URL is likely a downloadable file (not a tracker/ad)."""
        return not UrlCleaner.is_tracker_url(url)

    @staticmethod
    def prepare_url(url: str, resolve_short: bool = True) -> str:
        """
        Full URL preparation pipeline:
        1. Resolve short URLs
        2. Strip tracking params
        3. Validate not a tracker
        """
        result = url.strip()
        if resolve_short:
            result = UrlCleaner.resolve_short_url(result)
        result = UrlCleaner.clean_url(result)
        return result

    @staticmethod
    def batch_prepare(urls: list[str], resolve_short: bool = True) -> list[str]:
        """Prepare multiple URLs."""
        return [UrlCleaner.prepare_url(u, resolve_short) for u in urls]

    @staticmethod
    def get_url_info(url: str) -> dict:
        """Get basic info about a URL (type, domain, etc.)"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = parsed.path.lower()

            info = {
                'url': url,
                'domain': domain,
                'is_known_host': False,
                'host_type': 'unknown',
                'file_ext': None,
            }

            # Known file hosts
            known_hosts = {
                'mega.nz': 'mega', 'mega.co.nz': 'mega',
                'mediafire.com': 'mediafire',
                '4shared.com': '4shared',
                'gofile.io': 'gofile',
                'drive.google.com': 'gdrive',
                'docs.google.com': 'gdrive',
                'dropbox.com': 'dropbox',
                'onedrive.live.com': 'onedrive',
                '1drv.ms': 'onedrive',
                'pixeldrain.com': 'pixeldrain',
                'zippyshare.com': 'zippyshare',
            }

            for d, htype in known_hosts.items():
                if d in domain:
                    info['is_known_host'] = True
                    info['host_type'] = htype
                    break

            # Detect file extension
            ext_match = re.search(r'\.([a-zA-Z0-9]+)(?:\?|$)', path)
            if ext_match:
                info['file_ext'] = ext_match.group(1).lower()

            return info
        except Exception:
            return {'url': url, 'domain': '', 'is_known_host': False, 'host_type': 'unknown'}
