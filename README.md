# PDAnet-linux

Use your phone's cellular data on Linux through a PDA Net "WiFi Direct Hotspot".

## What this is

PDA Net's WiFi Direct Hotspot is **not** a NAT hotspot. The phone hands out DHCP,
responds to pings, and shows a default route, but it does NOT forward arbitrary
internet traffic. Instead, it runs a local HTTP proxy on port 8000 of the gateway
IP it advertises. That proxy tunnels everything over the phone's cellular connection.

This project finds that proxy and points Linux at it — across **all common shells**
and GUI apps. You can use it from the command line or with a small libadwaita GUI.

## Install

### From source

```bash
git clone https://github.com/phantomic12/pdanet-linux
cd pdanet-linux
make install-user     # user-local (~/.local/bin)
# or
sudo make install     # system-wide (/usr/local)
```

### Arch / CachyOS

```bash
makepkg -si           # from this repo
# or from AUR (coming soon):
# yay -S pdanet-linux
```

### Debian / Ubuntu

```bash
dpkg-buildpackage -us -uc -b
sudo dpkg -i ../pdanet-linux_*.deb
```

## Usage

**CLI:**

```
pdanet status       show connection + proxy state
pdanet on           enable proxy (asks polkit for the password once)
pdanet off          disable proxy
pdanet test         verify proxy + 1 MB speed test
pdanet watch        foreground: auto-toggle on SSID events
```

**GUI:**

```
pdanet-gui          single window: Connect / Disconnect + status
                    + live traffic monitor + speed test
```

Also available in the GNOME app menu as "PDAnet-linux".

## What `pdanet on` actually does

Writes the proxy URL everywhere so **all shells and GUI apps** pick it up:

| Target | File | Who it covers |
|--------|------|---------------|
| systemd user env | `~/.config/environment.d/pdanet.conf` | GUI apps launched by systemd |
| POSIX login shells | `/etc/profile.d/pdanet.sh` | dash, sh, login bash/zsh/ksh |
| bash interactive | `~/.bashrc` (prepended) | bash terminal windows |
| zsh interactive | `~/.zshrc` (prepended) | zsh terminal windows |
| fish interactive | `~/.config/fish/config.fish` (appended) | fish terminal windows |
| tcsh/csh | `~/.tcshrc` (appended) | tcsh/csh terminal windows |
| ksh interactive | `~/.kshrc` (prepended) | ksh terminal windows |
| GNOME | `org.gnome.system.proxy` (gsettings) | GNOME/GTK apps |

`pdanet off` reverses all of these. Each shell config uses `# PDANET_BEGIN … # PDANET_END`
sentinels so the script never corrupts hand-edited configs.

## Layout

```
scripts/pdanet            bash helper (CLI, called by the GUI)
src/pdanet-gui.py         libadwaita GUI
system/pdanet-gui.desktop GNOME app menu launcher
```

## The traffic monitor

The GUI polls `/proc/net/dev` for the active wlan interface every 1 s. When you
tap Connect, it captures the current RX/TX byte counts as a baseline; from
then on, the displayed Downloaded/Uploaded/Session total/Current rate values
are deltas against that baseline. Tap Reset to re-baseline at any time.

## Notes

* The phone must be running PDA Net's "WiFi Direct Hotspot" mode (not USB or
  Bluetooth mode). Look for the SSID `DIRECT-...-PdaNet` in `nmcli`.
* Speed is whatever the phone's cellular uplink is — about 23 Mbps on
  Verizon LTE in testing.
* The first toggle on each session will pop a polkit auth dialog asking for
  your password. Subsequent toggles use the cached authorization.
* `no_proxy` includes `100.64.0.0/10` and `.ts.net` so Tailscale traffic
  bypasses the proxy.

## License

MIT — see [LICENSE](LICENSE).
