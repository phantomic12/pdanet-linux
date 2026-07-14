#!/usr/bin/env python3
"""PDAnet-linux — a libadwaita GUI for sharing a PDA Net hotspot's cellular link.

PDA Net's "WiFi Direct Hotspot" is *not* a NAT hotspot — the phone hands out
DHCP and responds to pings, but it does not forward arbitrary traffic.
Instead it runs a local HTTP proxy on port 8000 of the gateway IP, which
tunnels everything over the phone's cellular connection. This GUI:

  1. Detects whether the active WiFi network is a PDA Net hotspot.
  2. Shows the phone's gateway IP, the proxy status, and a live traffic
     counter (read from /proc/net/dev for the wlan0 interface).
  3. Connects / disconnects by invoking the `pdanet` helper script (which
     handles pkexec, /etc/profile.d, gsettings, etc.) via explicit
     Connect and Disconnect buttons.

The GUI itself never holds root — the helper script does the elevation.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

APP_ID = "io.github.pdanetlinux.PDAnet"
APP_NAME = "PDAnet-linux"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pdanet"
USER_ENV_FILE = Path.home() / ".config" / "environment.d" / "pdanet.conf"
PROFILE_SH = Path("/etc/profile.d/pdanet.sh")

# Traffic sampling
TRAFFIC_POLL_MS = 1000  # how often to refresh /proc/net/dev


# ---------- subprocess helpers ----------

def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", str(e)


def pdanet_status() -> dict:
    rc, out, err = _run([str(SCRIPT), "status"])
    info = {
        "rc": rc, "ssid": None, "gateway": None, "proxy_set": False,
        "raw": out.strip(), "err": err.strip(),
    }
    for line in out.splitlines():
        if line.startswith("WiFi:"):
            if "PdaNet" in line:
                info["ssid"] = line.split("'")[-2] if "'" in line else "?"
                info["connected"] = True
            else:
                info["ssid"] = None
                info["connected"] = False
        elif line.startswith("Gateway:"):
            info["gateway"] = line.split(":", 1)[1].strip()
        elif line.startswith("Proxy:"):
            info["proxy_set"] = "not set" not in line
    return info


def pdanet_on() -> tuple[int, str, str]:
    return _run([str(SCRIPT), "on"], timeout=60)


def pdanet_off() -> tuple[int, str, str]:
    return _run([str(SCRIPT), "off"], timeout=60)


def pdanet_test() -> tuple[int, str, str]:
    return _run([str(SCRIPT), "test"], timeout=30)


def run_async(fn, on_done, *args):
    def worker():
        try:
            result = fn(*args)
        except Exception as e:  # noqa: BLE001
            result = e
        GLib.idle_add(on_done, result)
    threading.Thread(target=worker, daemon=True).start()


# ---------- traffic counter ----------

def read_wlan0_bytes() -> Optional[tuple[int, int]]:
    """Return (rx_bytes, tx_bytes) for the active WiFi interface, or None.

    Reads /proc/net/dev and looks for the interface whose name starts with
    "wlan". Strips whitespace and parses the 1st (RX) and 9th (TX) fields.
    """
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                iface, rest = line.split(":", 1)
                iface = iface.strip()
                if iface.startswith("wlan") and not iface.startswith("wlan-") \
                        and not iface.endswith("-mon") and "mon" not in iface:
                    parts = rest.split()
                    if len(parts) >= 9:
                        return int(parts[0]), int(parts[8])
    except (OSError, ValueError):
        pass
    return None


def human_bytes(n: int) -> str:
    """Format bytes with binary units (KiB, MiB, GiB)."""
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024.0:
            return f"{n:6.2f} {unit}"
        n /= 1024.0
    return f"{n:6.2f} EiB"


# ---------- main window ----------

class PdaNetWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(620, 800)
        self.set_size_request(480, 640)

        # Window -> ToastOverlay -> Box
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(outer)

        # Header bar
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label=APP_NAME))
        outer.append(header)

        # Scrollable content
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.append(scroller)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(720)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scroller.set_child(clamp)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        clamp.set_child(content)

        # ---- Status group ----
        status_group = Adw.PreferencesGroup()
        status_group.set_title("Status")
        content.append(status_group)

        self.ssid_row = Adw.ActionRow()
        self.ssid_row.set_title("Hotspot")
        self.ssid_row.set_subtitle("scanning…")
        status_group.add(self.ssid_row)

        self.gateway_row = Adw.ActionRow()
        self.gateway_row.set_title("Phone gateway")
        self.gateway_row.set_subtitle("—")
        status_group.add(self.gateway_row)

        self.wan_row = Adw.ActionRow()
        self.wan_row.set_title("Phone WAN IP")
        self.wan_row.set_subtitle("—")
        status_group.add(self.wan_row)

        # ---- Connect / Disconnect group ----
        connect_group = Adw.PreferencesGroup()
        connect_group.set_title("Connection")
        content.append(connect_group)

        # Big prominent action row
        connect_row = Adw.ActionRow()
        connect_row.set_title("Share phone's cellular link")
        self.status_label_row = connect_row  # we'll update its subtitle

        self.connect_btn = Gtk.Button(label="Connect")
        self.connect_btn.set_valign(Gtk.Align.CENTER)
        self.connect_btn.set_size_request(110, -1)
        self.connect_btn.add_css_class("suggested-action")
        self.connect_btn.add_css_class("pill")
        self.connect_btn.connect("clicked", lambda *_: self._do_on())

        self.disconnect_btn = Gtk.Button(label="Disconnect")
        self.disconnect_btn.set_valign(Gtk.Align.CENTER)
        self.disconnect_btn.set_size_request(110, -1)
        self.disconnect_btn.add_css_class("destructive-action")
        self.disconnect_btn.add_css_class("pill")
        self.disconnect_btn.connect("clicked", lambda *_: self._do_off())
        self.disconnect_btn.set_visible(False)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.append(self.connect_btn)
        button_box.append(self.disconnect_btn)
        connect_row.add_suffix(button_box)
        connect_group.add(connect_row)

        # ---- Traffic monitor group ----
        traffic_group = Adw.PreferencesGroup()
        traffic_group.set_title("Traffic through hotspot")
        content.append(traffic_group)

        # Session totals — when proxy turns on, capture baseline; everything
        # after that is the session.
        self._session_rx: Optional[int] = None
        self._session_tx: Optional[int] = None
        self._session_start_rx: int = 0
        self._session_start_tx: int = 0
        self._prev_rx: Optional[int] = None
        self._prev_tx: Optional[int] = None
        self._prev_time: Optional[float] = None

        self.rx_row = Adw.ActionRow()
        self.rx_row.set_title("Downloaded")
        self.rx_row.set_subtitle("—")
        traffic_group.add(self.rx_row)

        self.tx_row = Adw.ActionRow()
        self.tx_row.set_title("Uploaded")
        self.tx_row.set_subtitle("—")
        traffic_group.add(self.tx_row)

        self.session_row = Adw.ActionRow()
        self.session_row.set_title("Session total")
        self.session_row.set_subtitle("—")
        traffic_group.add(self.session_row)

        self.rate_row = Adw.ActionRow()
        self.rate_row.set_title("Current rate")
        self.rate_row.set_subtitle("—")
        traffic_group.add(self.rate_row)

        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset counters")
        reset_row.set_subtitle("Clear the session total to zero")
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", lambda *_: self._reset_counters())
        reset_row.add_suffix(reset_btn)
        reset_row.set_activatable_widget(reset_btn)
        traffic_group.add(reset_row)

        # ---- Actions group ----
        actions_group = Adw.PreferencesGroup()
        actions_group.set_title("Actions")
        content.append(actions_group)

        test_row = Adw.ActionRow()
        test_row.set_title("Speed test")
        test_row.set_subtitle("Download 1 MB through the proxy")
        test_btn = Gtk.Button(label="Run")
        test_btn.set_valign(Gtk.Align.CENTER)
        test_btn.connect("clicked", lambda *_: self._run_test())
        test_row.add_suffix(test_btn)
        test_row.set_activatable_widget(test_btn)
        actions_group.add(test_row)

        refresh_row = Adw.ActionRow()
        refresh_row.set_title("Refresh status")
        refresh_row.set_subtitle("Re-scan WiFi networks")
        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.connect("clicked", lambda *_: self.refresh())
        refresh_row.add_suffix(refresh_btn)
        refresh_row.set_activatable_widget(refresh_btn)
        actions_group.add(refresh_row)

        # ---- Log ----
        log_group = Adw.PreferencesGroup()
        log_group.set_title("Log")
        content.append(log_group)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.set_top_margin(8)
        self.log_view.set_bottom_margin(8)
        self.log_view.set_left_margin(8)
        self.log_view.set_right_margin(8)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_buffer = self.log_view.get_buffer()

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_min_content_height(120)
        log_scroll.set_max_content_height(220)
        log_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        log_scroll.set_child(self.log_view)

        log_row = Adw.ActionRow()
        log_row.set_child(log_scroll)
        log_group.add(log_row)

        # ---- Init state ----
        self._is_busy = False
        self._traffic_timer_id: Optional[int] = None
        self.refresh()
        # start the traffic timer regardless; it will just show "—" if
        # there's no wlan0 or no baseline
        self._start_traffic_timer()

    # ----- logging -----
    def log(self, msg: str, level: str = "info"):
        prefix = {"info": "•", "ok": "✓", "warn": "!", "err": "✗"}.get(level, "•")
        end = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end, f"{prefix} {msg}\n")
        mark = self._log_buffer.create_mark(None, self._log_buffer.get_end_iter(), False)
        self.log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def toast(self, msg: str, timeout: int = 3):
        toast = Adw.Toast.new(msg)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    # ----- state refresh -----
    def refresh(self):
        if self._is_busy:
            return
        self._set_busy(True, "Scanning…")
        run_async(pdanet_status, self._on_refresh_done)

    def _on_refresh_done(self, result):
        self._set_busy(False)
        if isinstance(result, Exception):
            self.log(f"refresh failed: {result}", "err")
            return
        info = result
        if info.get("connected"):
            self.ssid_row.set_subtitle(info.get("ssid") or "—")
            self.gateway_row.set_subtitle(info.get("gateway") or "—")
        else:
            self.ssid_row.set_subtitle("Not on PDA Net hotspot")
            self.gateway_row.set_subtitle("—")
            self.wan_row.set_subtitle("—")
        if info["proxy_set"]:
            self.wan_row.set_subtitle("proxy is ON — see below")
            self._set_connected_ui(True)
        else:
            self.wan_row.set_subtitle("—")
            self._set_connected_ui(False)
        if info["err"]:
            self.log(info["err"], "warn")

    def _set_connected_ui(self, connected: bool):
        """Switch between Connect / Disconnect button visibility."""
        if connected:
            self.connect_btn.set_visible(False)
            self.disconnect_btn.set_visible(True)
            self.status_label_row.set_subtitle("Connected — phone's cellular link is shared with this machine")
        else:
            self.connect_btn.set_visible(True)
            self.disconnect_btn.set_visible(False)
            self.status_label_row.set_subtitle("Tap Connect to share the phone's cellular link")

    def _set_disconnected(self):
        self.ssid_row.set_subtitle("Not on PDA Net hotspot")
        self.gateway_row.set_subtitle("—")
        self.wan_row.set_subtitle("—")
        self._set_connected_ui(False)

    def _set_busy(self, busy: bool, label: Optional[str] = None):
        self._is_busy = busy
        self.connect_btn.set_sensitive(not busy)
        self.disconnect_btn.set_sensitive(not busy)
        if busy and label:
            self.log(label, "info")

    # ----- connect / disconnect handlers -----
    def _do_on(self):
        self._set_busy(True, "Enabling PDA Net proxy…")
        run_async(pdanet_on, self._on_on_done)

    def _on_on_done(self, result):
        if isinstance(result, Exception):
            self.log(f"connect failed: {result}", "err")
            self.toast("Failed to connect — see log")
            self._set_busy(False)
            self._set_connected_ui(False)
            return
        rc, out, err = result
        for line in (out + err).splitlines():
            if line.strip():
                self.log(line)
        if rc == 0:
            self.log("connected", "ok")
            self.toast("PDAnet-linux is ON")
            self._set_connected_ui(True)
            self._reset_counters()
            self._fetch_wan_ip()
        else:
            self.log(f"connect exited with code {rc}", "err")
            self.toast("Failed to connect — see log")
            self._set_connected_ui(False)
        self._set_busy(False)

    def _do_off(self):
        self._set_busy(True, "Disconnecting…")
        run_async(pdanet_off, self._on_off_done)

    def _on_off_done(self, result):
        if isinstance(result, Exception):
            self.log(f"disconnect failed: {result}", "err")
            self.toast("Failed to disconnect — see log")
            self._set_busy(False)
            self._set_connected_ui(True)
            return
        rc, out, err = result
        for line in (out + err).splitlines():
            if line.strip():
                self.log(line)
        if rc == 0:
            self.log("disconnected", "ok")
            self.toast("PDAnet-linux is OFF")
            self._set_connected_ui(False)
            self.wan_row.set_subtitle("—")
        else:
            self.log(f"disconnect exited with code {rc}", "err")
            self.toast("Failed to disconnect — see log")
            self._set_connected_ui(True)
        self._set_busy(False)

    def _fetch_wan_ip(self):
        gateway = self.gateway_row.get_subtitle()
        if not gateway or gateway == "—":
            return

        def work():
            return _run(
                [
                    "curl", "-sS", "-m", "6",
                    "-x", f"http://{gateway}:8000",
                    "https://ipinfo.io/json",
                ],
                timeout=10,
            )
        run_async(work, self._on_wan_ip)

    def _on_wan_ip(self, result):
        rc, out, err = result
        if rc == 0 and out.strip():
            try:
                data = json.loads(out)
                ip = data.get("ip", "?")
                city = data.get("city", "")
                region = data.get("region", "")
                self.wan_row.set_subtitle(f"{ip}  ({city}, {region})")
            except json.JSONDecodeError:
                self.wan_row.set_subtitle(out.strip()[:60])

    def _run_test(self):
        if self._is_busy:
            return
        self._set_busy(True, "Running speed test…")
        run_async(pdanet_test, self._on_test_done)

    def _on_test_done(self, result):
        self._set_busy(False)
        if isinstance(result, Exception):
            self.log(f"test failed: {result}", "err")
            return
        rc, out, err = result
        for line in (out + err).splitlines():
            if line.strip():
                self.log(line, "ok" if "OK" in line else "info")

    # ----- traffic monitor -----
    def _start_traffic_timer(self):
        if self._traffic_timer_id is not None:
            return
        self._traffic_timer_id = GLib.timeout_add(
            TRAFFIC_POLL_MS, self._tick_traffic
        )

    def _tick_traffic(self) -> bool:
        """Poll /proc/net/dev for the wlan0 bytes; update the rows."""
        sample = read_wlan0_bytes()
        if sample is None:
            self.rx_row.set_subtitle("no wlan interface")
            self.tx_row.set_subtitle("—")
            self.session_row.set_subtitle("—")
            self.rate_row.set_subtitle("—")
            return True  # keep timer running
        rx, tx = sample
        # detect counter wrap (kernel restarts, etc.)
        if self._prev_rx is None or rx < self._prev_rx:
            self._prev_rx = rx
            self._prev_tx = tx
            self._prev_time = None
        # init session baseline if not set
        if self._session_rx is None:
            self._session_start_rx = rx
            self._session_start_tx = tx
            self._session_rx = 0
            self._session_tx = 0
        else:
            self._session_rx = rx - self._session_start_rx
            self._session_tx = tx - self._session_start_tx
        # compute rate
        import time as _t
        now = _t.monotonic()
        rate_text = "—"
        if self._prev_time is not None and (now - self._prev_time) > 0:
            dr = max(0, rx - self._prev_rx)
            dt = max(0, tx - self._prev_tx)
            elapsed = now - self._prev_time
            # average of rx+tx rate
            rate = (dr + dt) / elapsed
            rate_text = f"{human_bytes(rate)}/s"
        self._prev_rx = rx
        self._prev_tx = tx
        self._prev_time = now
        # update rows
        self.rx_row.set_subtitle(f"{human_bytes(self._session_rx)}")
        self.tx_row.set_subtitle(f"{human_bytes(self._session_tx)}")
        total = self._session_rx + self._session_tx
        self.session_row.set_subtitle(f"{human_bytes(total)}")
        self.rate_row.set_subtitle(rate_text)
        return True  # keep timer running

    def _reset_counters(self):
        """Reset session baseline to current wlan0 byte count."""
        sample = read_wlan0_bytes()
        if sample is None:
            self.log("cannot reset: no wlan interface", "warn")
            return
        rx, tx = sample
        self._session_start_rx = rx
        self._session_start_tx = tx
        self._session_rx = 0
        self._session_tx = 0
        self._prev_rx = rx
        self._prev_tx = tx
        self._prev_time = None
        self.rx_row.set_subtitle("0.00 B")
        self.tx_row.set_subtitle("0.00 B")
        self.session_row.set_subtitle("0.00 B")
        self.rate_row.set_subtitle("—")
        self.log("traffic counters reset", "info")


# ---------- app ----------

class PdaNetApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self, _user_data=None):
        win = self.get_active_window()
        if not win:
            win = PdaNetWindow(self)
        win.present()


def main():
    if not SCRIPT.exists():
        sys.stderr.write(f"FATAL: helper script not found at {SCRIPT}\n")
        sys.exit(2)
    app = PdaNetApp()
    app.run(None)


if __name__ == "__main__":
    import sys
    main()
