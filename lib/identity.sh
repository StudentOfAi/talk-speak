#!/bin/bash
# lib/identity.sh — the local code-signing identity talk-speak signs its app with.
# Sourced by install.sh and talk/app/build.sh. Self-signed, in the login keychain,
# created without a single Keychain Access click. macOS keys the Microphone,
# Accessibility and Input Monitoring grants to (bundle id + this certificate),
# so the SAME identity must sign every rebuild or the grants have to be redone.
IDENTITY="${TALK_SPEAK_IDENTITY:-talk-speak Local Dev}"
# the user's login keychain, wherever macOS says it is (TALK_SPEAK_KEYCHAIN overrides, for tests)
KEYCHAIN="${TALK_SPEAK_KEYCHAIN:-$(security login-keychain 2>/dev/null | tr -d ' "')}"
[ -n "$KEYCHAIN" ] || KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

identity_exists() {
  # no `/usr/bin/grep -q` here: under `set -o pipefail` its early exit makes a found identity look missing
  security find-identity -v -p codesigning 2>/dev/null | /usr/bin/grep -F "\"$IDENTITY\"" >/dev/null
}

identity_create() {   # idempotent; returns 1 if the identity is still not usable
  identity_exists && return 0
  local d; d=$(mktemp -d)
  cat > "$d/cfg" <<CFG
[req]
distinguished_name=dn
x509_extensions=ext
prompt=no
[dn]
CN=$IDENTITY
[ext]
keyUsage=critical,digitalSignature
extendedKeyUsage=critical,codeSigning
basicConstraints=critical,CA:false
subjectKeyIdentifier=hash
CFG
  # /usr/bin/openssl on purpose: Homebrew OpenSSL 3 writes a PKCS12 that `security import` rejects
  /usr/bin/openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -config "$d/cfg" \
      -keyout "$d/key.pem" -out "$d/cert.pem" >/dev/null 2>&1
  /usr/bin/openssl pkcs12 -export -inkey "$d/key.pem" -in "$d/cert.pem" -name "$IDENTITY" \
      -out "$d/id.p12" -passout pass:talk-speak >/dev/null 2>&1
  security import "$d/id.p12" -k "$KEYCHAIN" -P talk-speak -T /usr/bin/codesign -T /usr/bin/security >/dev/null
  security add-trusted-cert -p codeSign -k "$KEYCHAIN" "$d/cert.pem"
  rm -rf "$d"
  identity_exists
}

identity_delete() {   # used by install.sh --uninstall --purge and by the test suite
  identity_exists || return 0
  local d; d=$(mktemp -d)
  security find-certificate -c "$IDENTITY" -p "$KEYCHAIN" > "$d/cert.pem" 2>/dev/null \
    && security remove-trusted-cert "$d/cert.pem" >/dev/null 2>&1 || true
  security delete-identity -c "$IDENTITY" "$KEYCHAIN" >/dev/null 2>&1 || true
  rm -rf "$d"
}
