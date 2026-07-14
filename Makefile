# PDAnet-linux — Makefile
# install / uninstall / package targets

PREFIX    ?= /usr/local
BINDIR    ?= $(PREFIX)/bin
DATADIR   ?= $(PREFIX)/share
APPDIR    ?= $(DATADIR)/applications
ICONDIR   ?= $(DATADIR)/icons/hicolor/scalable/apps

SCRIPTS   = scripts/pdanet
GUI       = src/pdanet-gui.py
DESKTOP   = system/pdanet-gui.desktop
DISPATCHER = system/99-pdanet-proxy
ICON      = icons/pdanet-linux.svg

.PHONY: all install uninstall install-user deb arch pkg

all:

# ---------- system-wide install ----------
install:
	install -Dm755 $(SCRIPTS)  $(DESTDIR)$(BINDIR)/pdanet
	install -Dm755 $(GUI)      $(DESTDIR)$(BINDIR)/pdanet-gui
	install -Dm644 $(DESKTOP)  $(DESTDIR)$(APPDIR)/pdanet-gui.desktop
	install -Dm755 $(DISPATCHER) $(DESTDIR)/etc/NetworkManager/dispatcher.d/99-pdanet-proxy
	@if [ -f "$(ICON)" ]; then \
		install -Dm644 $(ICON) $(DESTDIR)$(ICONDIR)/pdanet-linux.svg; \
	fi

# ---------- user-local install (no root) ----------
install-user:
	install -Dm755 $(SCRIPTS)  $(HOME)/.local/bin/pdanet
	install -Dm755 $(GUI)      $(HOME)/.local/bin/pdanet-gui
	install -Dm644 $(DESKTOP)  $(HOME)/.local/share/applications/pdanet-gui.desktop
	@if [ -f "$(ICON)" ]; then \
		install -Dm644 $(ICON) $(HOME)/.local/share/icons/hicolor/scalable/apps/pdanet-linux.svg; \
	fi

# ---------- uninstall ----------
uninstall:
	rm -f $(DESTDIR)$(BINDIR)/pdanet
	rm -f $(DESTDIR)$(BINDIR)/pdanet-gui
	rm -f $(DESTDIR)$(APPDIR)/pdanet-gui.desktop

# ---------- Arch package ----------
arch:
	makepkg -sf --noconfirm

# ---------- Debian package ----------
deb:
	dpkg-buildpackage -us -uc -b

# ---------- generic tarball ----------
dist:
	git archive --format=tar.gz --prefix=pdanet-linux-$$(git describe --tags --always 2>/dev/null || echo "dev")/ HEAD \
		> pdanet-linux-$$(git describe --tags --always 2>/dev/null || echo "dev").tar.gz
