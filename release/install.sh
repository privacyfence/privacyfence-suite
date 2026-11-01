#!/bin/sh
# PrivacyFence suite installer.
# Usage: install.sh <config> [--dir DIR] [--upgrade] [--start]
# Installs the release this script came from. Everything is in functions and the last line
# calls main, so a download that is cut short runs nothing.
set -eu

VERSION="@VERSION@"
CONFIGS="@CONFIGS@"
BASE_URL=${PRIVACYFENCE_SUITE_BASE_URL:-https://github.com/privacyfence/privacyfence-suite/releases/download/v@VERSION@}
DOCS_URL=https://github.com/privacyfence/privacyfence-suite/blob/v@VERSION@

TMP=

cleanup() {
    if [ -n "$TMP" ]; then
        rm -rf "$TMP"
    fi
}

die() {
    printf 'install: %s\n' "$*" >&2
    exit 1
}

have() {
    command -v "$1" >/dev/null 2>&1
}

usage() {
    printf 'usage: install.sh <config> [--dir DIR] [--upgrade] [--start]\n'
    printf 'configurations: %s\n' "$CONFIGS"
    printf '  --dir DIR   install into DIR (default ./privacyfence-<config>)\n'
    printf '  --upgrade   update an existing folder; .env and secrets are kept\n'
    printf '  --start     run docker compose up -d afterwards\n'
}

usage_error() {
    if [ $# -gt 0 ]; then
        printf 'install: %s\n' "$*" >&2
    fi
    usage >&2
    exit 2
}

fetch() {
    # fetch URL DEST
    if have curl; then
        curl -fsSL -o "$2" "$1" || die "download failed: $1"
    else
        wget -q -O "$2" "$1" || die "download failed: $1"
    fi
}

sha256_of() {
    if have sha256sum; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

check_tools() {
    # check_tools START
    if ! have curl && ! have wget; then
        die "missing curl"
    fi
    have tar || die "missing tar"
    if ! have sha256sum && ! have shasum; then
        die "missing sha256sum"
    fi
    if ! have docker; then
        if [ "$1" = 1 ]; then
            die "missing docker"
        fi
        printf 'install: warning: docker not found; running the stack needs Docker Engine 24+ with Compose 2.24+\n' >&2
    fi
}

verify() {
    # verify ASSET: check $TMP/ASSET against its line in $TMP/SHA256SUMS
    expected=$(awk -v n="$1" '$2 == n || $2 == "*" n { print $1; exit }' "$TMP/SHA256SUMS")
    actual=$(sha256_of "$TMP/$1")
    if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
        die "checksum mismatch for $1"
    fi
}

install_fresh() {
    # install_fresh SRC DIR
    if [ -e "$2" ] && { [ ! -d "$2" ] || [ -n "$(ls -A "$2")" ]; }; then
        die "$2 exists; use --upgrade to update it"
    fi
    if [ -d "$2" ]; then
        rmdir "$2"
    fi
    mkdir -p "$(dirname "$2")"
    mv "$1" "$2"
    cp "$2/.env.example" "$2/.env"
    printf 'installed %s in %s\n' "$VERSION" "$2"
}

install_upgrade() {
    # install_upgrade SRC DIR
    if [ ! -f "$2/VERSION" ]; then
        die "$2 is not a suite folder"
    fi
    old=$(cat "$2/VERSION")
    cp -R "$1/." "$2/"
    printf 'upgraded %s -> %s\n' "$old" "$VERSION"
}

next_steps() {
    # next_steps CONFIG DIR UPGRADE
    printf '\nNext steps:\n'
    printf '  cd %s\n' "$2"
    if [ "$3" = 1 ]; then
        printf '  docker compose pull && docker compose up -d\n'
        return 0
    fi
    case $1 in
    localhost)
        printf '  docker compose up -d\n'
        printf '  docker compose logs privacyfence | grep "Setup code"\n'
        ;;
    caddy-idp)
        printf '  edit .env (hostnames, admin e-mail addresses, your identity provider)\n'
        printf '  write the client secret to secrets/idp_client_secret\n'
        printf '  docker compose up -d\n'
        ;;
    nginx-google)
        printf '  edit .env (hostnames, admin e-mail addresses, allowed domain)\n'
        printf '  install the example site configuration in your nginx: see nginx/README.md\n'
        printf '  docker compose up -d\n'
        ;;
    *)
        printf '  edit .env (hostnames, admin e-mail addresses, allowed domain)\n'
        printf '  docker compose up -d\n'
        ;;
    esac
    printf 'Documentation: %s/README.md\n' "$DOCS_URL"
}

main() {
    config=
    dir=
    upgrade=0
    start=0
    while [ $# -gt 0 ]; do
        case $1 in
        -h | --help)
            usage
            exit 0
            ;;
        --dir)
            [ $# -ge 2 ] || usage_error "--dir needs a value"
            dir=$2
            shift 2
            ;;
        --upgrade)
            upgrade=1
            shift
            ;;
        --start)
            start=1
            shift
            ;;
        -*)
            usage_error "unknown option $1"
            ;;
        *)
            [ -z "$config" ] || usage_error "unexpected argument $1"
            config=$1
            shift
            ;;
        esac
    done

    [ -n "$config" ] || usage_error
    known=0
    for c in $CONFIGS; do
        if [ "$c" = "$config" ]; then
            known=1
        fi
    done
    [ "$known" = 1 ] || usage_error "unknown configuration $config"
    if [ -z "$dir" ]; then
        dir=./privacyfence-$config
    fi

    check_tools "$start"

    TMP=$(mktemp -d)
    trap cleanup EXIT
    trap 'exit 1' INT TERM

    asset=privacyfence-suite-$config.tar.gz
    fetch "$BASE_URL/$asset" "$TMP/$asset"
    fetch "$BASE_URL/SHA256SUMS" "$TMP/SHA256SUMS"
    verify "$asset"

    mkdir "$TMP/x"
    tar -xzf "$TMP/$asset" -C "$TMP/x"
    src=$TMP/x/privacyfence-$config
    [ -d "$src" ] || die "unexpected archive layout in $asset"

    if [ "$upgrade" = 1 ]; then
        install_upgrade "$src" "$dir"
    else
        install_fresh "$src" "$dir"
    fi

    if [ "$start" = 1 ]; then
        (cd "$dir" && docker compose up -d </dev/null)
    fi
    next_steps "$config" "$dir" "$upgrade"
}

main "$@"
