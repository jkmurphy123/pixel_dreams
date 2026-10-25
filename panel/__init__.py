# panel/__init__.py
#
# Lazy bootstrap for the embedded control panel.
#
# `import panel` MUST NOT import nicegui: the kiosk runs without the panel most of the time
# and should not carry fastapi/uvicorn/nicegui in memory for a feature it is not using.
# NiceGUI is imported inside start_panel(), and a test asserts the difference.
#
# The panel is a THREAD in the controller process (see AGENTS.md, "the thread contract").
# It talks to the render loop only through core.bus.ControlBus.

from __future__ import annotations

import threading

from core.bus import APP_NAME, require_loopback_or_token

DEFAULT_PANEL_PORT = 8090
DEFAULT_PANEL_BIND = "127.0.0.1"


class PanelHandle:
    """A running panel: its thread plus what it was told to serve on."""

    def __init__(self, thread: threading.Thread, host: str, port: int):
        self.thread = thread
        self.host = host
        self.port = port

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::", "") else self.host
        return f"http://{host}:{self.port}/"

    def join(self, timeout: float | None = None) -> None:
        self.thread.join(timeout)


def start_panel(*, base_dir: str, bus, host: str = DEFAULT_PANEL_BIND,
                port: int = DEFAULT_PANEL_PORT, token: str | None = None,
                config_override: str | None = None, ungated: bool = False) -> PanelHandle:
    """
    Register the panel's pages and serve them from a daemon thread.

    Raises ValueError (before importing nicegui, or touching the network) when a
    non-loopback bind has no token configured, unless `ungated` says the operator asked
    for an open panel (`--panel-open`).
    """
    require_loopback_or_token(host, token, allow_open=ungated)

    # Imported here, not at module import: this is the lazy boundary.
    from .app import register_pages, PageContext
    import nicegui

    ctx = PageContext(
        base_dir=base_dir,
        bus=bus,
        bind=host,
        port=int(port),
        token=token or None,
        config_override=config_override,
        ungated=bool(ungated),
    )
    register_pages(ctx)
    bus.update_status(panel_bind=host, panel_port=int(port),
                      nicegui_version=getattr(nicegui, "__version__", "?"))

    thread = threading.Thread(
        target=_serve, kwargs={"host": host, "port": int(port)}, daemon=True, name="panel"
    )
    thread.start()
    return PanelHandle(thread, host, int(port))


def _serve(*, host: str, port: int) -> None:
    """uvicorn's own thread. Everything the panel serves lives in panel/app.py."""
    import nicegui.ui as ui

    ui.run(
        host=host,
        port=port,
        title=APP_NAME,
        reload=False,          # one worker, no reload: state is in-process by design
        show=False,            # never try to open a browser on the kiosk
        uvicorn_logging_level="warning",
        uvicorn_reload_dirs=None,
    )
