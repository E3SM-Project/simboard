#!/usr/bin/env bash
set -e

CERT_DIR="$(dirname "$0")"

echo "🔐 Generating self-signed local SSL certificates..."

# --- Detect OS -------------------------------------------------------------

OS="$(uname -s)"

case "$OS" in
    Darwin*)
        PLATFORM="macOS"
        INSTALL_INSTRUCTIONS="brew install mkcert nss"
        ;;
    Linux*)
        PLATFORM="Linux"
        INSTALL_INSTRUCTIONS="sudo apt install mkcert libnss3-tools || sudo dnf install mkcert nss-tools || sudo pacman -S mkcert nss"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        PLATFORM="Windows (WSL recommended)"
        INSTALL_INSTRUCTIONS="
Windows detected.

➡ Recommended: Run this script inside WSL and install mkcert via:
  sudo apt install mkcert libnss3-tools

Or install mkcert manually from:
  https://github.com/FiloSottile/mkcert/releases
"
        ;;
    *)
        PLATFORM="unknown"
        INSTALL_INSTRUCTIONS="Please install mkcert manually: https://github.com/FiloSottile/mkcert"
        ;;
esac

echo "🖥  Detected platform: $PLATFORM"

# --- Check mkcert availability --------------------------------------------

if ! command -v mkcert &> /dev/null; then
  echo "❌ mkcert is not installed."
  echo "➡ To install mkcert on $PLATFORM, run:"
  echo "   $INSTALL_INSTRUCTIONS"
  exit 1
fi

# --- Generate certs --------------------------------------------------------

echo "🔧 Installing mkcert root CA (first time only)..."
mkcert -install

echo "📜 Creating local.key and local.crt in $CERT_DIR..."
mkcert \
  -key-file "$CERT_DIR/local.key" \
  -cert-file "$CERT_DIR/local.crt" \
  "localhost" "127.0.0.1" "::1"

echo "✅ Done!"
echo "   Key : $CERT_DIR/local.key"
echo "   Cert: $CERT_DIR/local.crt"
