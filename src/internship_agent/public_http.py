"""Bounded public HTTPS GET transport used by company-source verification."""

from io import BytesIO
import ipaddress
import socket
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

API_HOSTS = frozenset({"boards-api.greenhouse.io", "api.lever.co", "api.ashbyhq.com"})
BOARD_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com"})
USER_AGENT = "InternshipAgent/2027"


class PublicAccessError(ValueError):
    """Public access was unavailable or rejected by the verification policy."""


def validate_https_url(url, allowed_hosts):
    p = urlsplit(url)
    if (p.scheme != "https" or not p.hostname or p.hostname not in allowed_hosts
            or p.username is not None or p.password is not None or p.port not in (None, 443)):
        raise PublicAccessError("URL must use HTTPS on an explicitly allowed host without credentials")
    if p.hostname == "localhost" or p.hostname.endswith((".localhost", ".local", ".internal")):
        raise PublicAccessError("Local hosts are forbidden")
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise PublicAccessError("Private or reserved addresses are forbidden")
    if any(part.casefold() in {"apply", "application", "applications", "submit", "login", "signin"}
           for part in p.path.split("/")):
        raise PublicAccessError("Application, submission and login paths are outside this workflow")
    return p


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PublicAccessError("Redirect rejected; supply and verify the final public URL explicitly")


class PublicGetTransport:
    """One cached, paced GET channel; ATS response parsing stays in existing clients."""
    def __init__(self, allowed_hosts, *, timeout=15, max_requests=160, interval=0.3,
                 opener=None, resolver=None, sleeper=None):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.timeout = timeout
        self.max_requests = max_requests
        self.interval = interval
        self.opener = opener or build_opener(_NoRedirect()).open
        self.resolver = resolver or socket.getaddrinfo
        self.sleeper = sleeper or time.sleep
        self.cache = {}
        self.requests = []
        self.last_request = 0.0

    def __call__(self, request, timeout=None):
        if not isinstance(request, Request) or request.get_method() != "GET" or request.data is not None:
            raise PublicAccessError("Only unauthenticated public GET requests are allowed")
        if any(k.casefold() in {"authorization", "cookie", "proxy-authorization"} for k in request.headers):
            raise PublicAccessError("Authentication and cookie headers are forbidden")
        url = request.full_url
        parsed = validate_https_url(url, self.allowed_hosts)
        if url in self.cache:
            return self._response(self.cache[url])
        if len(self.requests) >= self.max_requests:
            raise PublicAccessError("Public request budget exhausted")
        addresses = self.resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise PublicAccessError("Host resolved to a private or reserved network")
        delay = self.interval - (time.monotonic() - self.last_request)
        if delay > 0:
            self.sleeper(delay)
        self.last_request = time.monotonic()
        self.requests.append({"method": "GET", "url": url})
        with self.opener(request, timeout=min(timeout or self.timeout, self.timeout)) as response:
            status = getattr(response, "status", None) or response.getcode()
            final_url = response.geturl() if hasattr(response, "geturl") else url
            if final_url != url:
                raise PublicAccessError("Unexpected redirect target")
            if status != 200:
                raise HTTPError(url, status, "Unsuccessful public response", {}, None)
            body = response.read(32 * 1024 * 1024 + 1)
            if len(body) > 32 * 1024 * 1024:
                raise PublicAccessError("Public response exceeded size limit")
        self.cache[url] = body
        return self._response(body)

    @staticmethod
    def _response(body):
        response = BytesIO(body)
        response.status = 200
        response.getcode = lambda: 200
        return response

    def page(self, url, *, respect_robots=True):
        validate_https_url(url, self.allowed_hosts)
        if respect_robots:
            parsed = urlsplit(url)
            robots_url = f"https://{parsed.hostname}/robots.txt"
            try:
                with self(Request(robots_url, method="GET", headers={"User-Agent": USER_AGENT})) as response:
                    robots = response.read().decode("utf-8", errors="replace")
                policy = RobotFileParser()
                policy.parse(robots.splitlines())
                if not policy.can_fetch(USER_AGENT, url):
                    raise PublicAccessError("robots.txt disallows this public page")
            except HTTPError as error:
                if error.code not in {404, 410}:
                    raise PublicAccessError(f"robots.txt could not be verified (HTTP {error.code})") from error
        with self(Request(url, method="GET", headers={"User-Agent": USER_AGENT})) as response:
            return response.read().decode("utf-8", errors="replace")
