"""Explicit foreground, loopback-only launch; no background/startup integration."""

import argparse
import os
import platform
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from . import demo
from .demo_services import reject_links

SAFE_OPTIONS = {
    "server.address": "127.0.0.1", "server.port": 8501, "server.headless": True,
    "server.fileWatcherType": "none", "server.runOnSave": False, "server.enableStaticServing": False,
    "server.enableCORS": True, "server.enableXsrfProtection": True,
    "browser.serverAddress": "127.0.0.1", "browser.gatherUsageStats": False,
    "client.showErrorDetails": "none", "client.toolbarMode": "minimal", "theme.font": "sans-serif",
    "secrets.files": [],
}


def offline_audit_guard(public_root, python_root):
    """Process-lifetime guard: loopback transport only, no persisted writes."""
    root, runtime = Path(public_root).resolve(), Path(python_root).resolve()
    attempts = {"external_network": 0, "external_input": 0, "filesystem_write": 0}

    def fail(kind):
        attempts[kind] += 1
        raise PermissionError("Offline dashboard safety boundary refused an unexpected operation")

    def path_check(raw, *, writing=False, database=False):
        if isinstance(raw, int) or raw is None or raw in {":memory:", os.devnull}: return
        raw = os.fsdecode(raw)
        uri = raw.startswith("file:")
        if uri:
            parsed = urlsplit(raw)
            raw = unquote(parsed.path)
            if len(raw) > 2 and raw[0] == "/" and raw[2] == ":": raw = raw[1:]
        path = Path(raw).resolve()
        if writing:
            label = path.relative_to(root).as_posix() if path.is_relative_to(root) else "outside-public-workspace"
            print("Blocked dashboard auxiliary write:", label, file=sys.stderr)
            fail("filesystem_write")
        if not (path.is_relative_to(root) or path.is_relative_to(runtime)): fail("external_input")
        if path.is_relative_to(root):
            parts = path.relative_to(root).parts
            if parts and parts[0] in {"candidate", "resumes", "reports", "logs", "private", "credentials", "secrets"}: fail("external_input")
        if database and (not uri or parsed.query != "mode=ro" or path != root / "data" / "demo" / "demo.sqlite3"):
            fail("filesystem_write")

    def guard(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.bind", "socket.sendto"}:
            address = args[-1]
            if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}: fail("external_network")
            if event == "socket.bind" and address[0] != "127.0.0.1": fail("external_network")
        elif event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
            if args[0] not in {"127.0.0.1", "::1", "localhost"}: fail("external_network")
        elif event in {"subprocess.Popen", "os.system"}: fail("external_network")
        elif event == "open":
            mode, flags = args[1] or "", args[2] or 0
            path_check(args[0], writing=any(char in mode for char in "wax+") or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        elif event == "sqlite3.connect": path_check(args[0], database=True)
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.rename", "os.link", "os.symlink"}:
            path_check(args[0], writing=True)
        elif event in {"os.listdir", "os.scandir"}: path_check(args[0])
    return guard, attempts


def configure_streamlit(*, public_root, theme="light"):
    """Use only reviewed workspace configuration, never user/global secrets.

    Streamlit's config-file provider is explicitly constrained before parsing.
    This adapter is verified against the locally installed Streamlit version.
    """
    if theme not in {"light", "dark"}: raise ValueError("Unsupported local theme")
    root = Path(public_root)
    config_file = root / ".streamlit" / "config.toml"
    reject_links(config_file)
    for key in tuple(os.environ):
        if key.startswith("STREAMLIT_"): os.environ.pop(key)
    from streamlit import config
    config.get_config_files = lambda name: [str(config_file)] if name == "config.toml" else []
    options = {**SAFE_OPTIONS, "theme.base": theme}
    config.get_config_options(force_reparse=True, options_from_flags=options)
    return options


def disable_config_polling(bootstrap):
    """Streamlit 1.65 installs a poll watcher independently of fileWatcherType.

    Manual configuration is immutable for this server run. Explicitly suppress
    that separate hook; fail closed if the reviewed bootstrap API changes.
    """
    if not callable(getattr(bootstrap, "_install_config_watchers", None)):
        raise RuntimeError("Unsupported Streamlit bootstrap; review the no-polling adapter before launch")
    bootstrap._install_config_watchers = lambda flag_options: None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manual synthetic dashboard on 127.0.0.1 only.")
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    args = parser.parse_args(argv)
    root = demo.PUBLIC_ROOT
    script = root / "src" / "internship_agent" / "dashboard_app.py"
    reject_links(script)
    if Path(sys.prefix).resolve() != (root / ".venv").resolve():
        print("Use the public workspace's isolated .venv to launch this demonstration.", file=sys.stderr)
        return 1
    os.chdir(root)
    local_temp = root / ".venv" / "dashboard-tmp"
    reject_links(local_temp)
    local_temp.mkdir(exist_ok=True)
    tempfile.tempdir = str(local_temp)
    # Windows' stdlib platform probe may use a local `ver` subprocess and NUL
    # streams. Resolve that runtime metadata before the no-subprocess guard;
    # subsequent framework reads use the standard-library cache.
    platform.uname()
    guard, attempts = offline_audit_guard(root, sys.base_prefix)
    sys.addaudithook(guard)
    options = configure_streamlit(public_root=root, theme=args.theme)
    from streamlit.web import bootstrap
    disable_config_polling(bootstrap)
    print(demo.NOTICE)
    print("Manual local server: http://127.0.0.1:8501 — stop with Ctrl+C in this terminal.")
    try:
        bootstrap.run(str(script), False, [], options)
    finally:
        print("Offline dashboard blocked attempts:", attempts)
    return 0
