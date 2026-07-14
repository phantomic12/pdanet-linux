# Maintainer: pdanet-linux contributors
# Contributor: phantomic12 <https://github.com/phantomic12>

pkgname=pdanet-linux
pkgver=1.0.0
pkgrel=1
pkgdesc="Linux client for PDA Net WiFi Direct Hotspot — proxy manager with libadwaita GUI"
arch=('any')
url="https://github.com/phantomic12/pdanet-linux"
license=('MIT')
depends=('bash' 'curl' 'networkmanager' 'python' 'python-gobject' 'gtk4' 'libadwaita')
makedepends=('git')
optdepends=('polkit: for system-wide proxy configuration via pkexec')
provides=('pdanet-linux')
conflicts=('pdanet-linux-git')
source=("$pkgname-$pkgver.tar.gz::https://github.com/phantomic12/pdanet-linux/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # CLI
    install -Dm755 scripts/pdanet                "$pkgdir/usr/bin/pdanet"

    # GUI
    install -Dm755 src/pdanet-gui.py            "$pkgdir/usr/bin/pdanet-gui"

    # Desktop entry
    install -Dm644 system/pdanet-gui.desktop    "$pkgdir/usr/share/applications/pdanet-gui.desktop"

    # Icon (if present)
    if [[ -f icons/pdanet-linux.svg ]]; then
        install -Dm644 icons/pdanet-linux.svg   "$pkgdir/usr/share/icons/hicolor/scalable/apps/pdanet-linux.svg"
    fi

    # License
    install -Dm644 LICENSE                      "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
