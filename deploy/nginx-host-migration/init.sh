#!/bin/sh
# Generates the suite's shared secrets once and installs a copy into each consumer's volume.
# Runs as root in the one-shot `init` service on every `docker compose up`.
# POSIX sh, busybox only.
set -eu
umask 077

# 1. Directories
for dir in /out/pf /out/peek /out/grist /out/provisioner; do
    chmod 0755 "$dir"
done

# generate NAME PREFIX
# First run only: write the canonical root-only copy /out/pf/.NAME (PREFIX + 43 base64url characters).
generate() {
    name=$1
    prefix=$2
    canonical="/out/pf/.$name"
    if [ -s "$canonical" ]; then
        return 0
    fi
    value=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')
    tmp="/out/pf/.$name.tmp"
    printf '%s%s' "$prefix" "$value" > "$tmp"
    chown 0:0 "$tmp"
    chmod 0400 "$tmp"
    mv -f "$tmp" "$canonical"
    echo "init: generated $name"
}

# install_copy NAME VOLUME OWNER
# Every run: temp file, chown, chmod, mv, so ownership is always right.
install_copy() {
    name=$1
    volume=$2
    owner=$3
    tmp="/out/$volume/.$name.tmp"
    cat "/out/pf/.$name" > "$tmp"
    chown "$owner" "$tmp"
    chmod 0400 "$tmp"
    mv -f "$tmp" "/out/$volume/$name"
}

# 2. Shared values
generate peek_provisioning_key peekprov_
generate grist_provisioning_key gristprov_
generate peek_oidc_client_secret ""
generate grist_oidc_client_secret ""
generate grist_boot_key ""
generate grist_session_secret ""

# 3. Copies (volume: owner)
install_copy peek_provisioning_key pf 10001:10001
install_copy peek_provisioning_key peek 65532:65532
install_copy grist_provisioning_key pf 10001:10001
install_copy grist_provisioning_key provisioner 1001:1001
install_copy peek_oidc_client_secret pf 10001:10001
install_copy peek_oidc_client_secret peek 65532:65532
install_copy grist_oidc_client_secret pf 10001:10001
install_copy grist_oidc_client_secret grist 0:0
install_copy grist_boot_key grist 0:0
install_copy grist_boot_key provisioner 1001:1001
install_copy grist_session_secret grist 0:0

# The operator's identity-provider secret (caddy-idp only), installed on every run.
if [ -f /user-secrets/idp_client_secret ]; then
    tmp="/out/pf/.idp_client_secret.tmp"
    cat /user-secrets/idp_client_secret > "$tmp"
    chown 10001:10001 "$tmp"
    chmod 0400 "$tmp"
    mv -f "$tmp" /out/pf/idp_client_secret
    echo "init: installed idp_client_secret"
fi
