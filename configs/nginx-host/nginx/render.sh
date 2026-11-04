#!/bin/sh
# Prints this configuration's nginx site, filled in from ../.env. Writes nothing.
#   sh nginx/render.sh > /etc/nginx/conf.d/privacyfence-suite.conf
# Certificates default to /etc/ssl/certs/<host>/fullchain.pem and privkey.pem; set CERT_ROOT, or
# PF_CERT/PF_KEY, PEEK_CERT/PEEK_KEY, GRIST_CERT/GRIST_KEY, in .env or the environment to change that.
# Every name in PEEK_REDIRECT_HOSTNAMES gets a server that redirects to PEEK_HOSTNAME.
# If another nginx file already defines the pf_oauth rate-limit zone, the site uses that one.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dir=$(dirname "$here")
if [ ! -f "$dir/.env" ]; then
    echo "render: missing $dir/.env" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$dir/.env"
set +a
: "${PF_HOSTNAME:?set PF_HOSTNAME in .env}" "${PEEK_HOSTNAME:?set PEEK_HOSTNAME in .env}" "${GRIST_HOSTNAME:?set GRIST_HOSTNAME in .env}"
root=${CERT_ROOT:-/etc/ssl/certs}

# The file, other than this site, that already defines the pf_oauth zone.
zone=
if command -v nginx >/dev/null 2>&1; then
    zone=$(nginx -T 2>/dev/null | awk '/^# configuration file /{f=$4; sub(/:$/,"",f)}
        f !~ /privacyfence-suite\.conf$/ && /^[[:space:]]*limit_req_zone[[:space:]].*zone=pf_oauth:/ {print f; exit}' || true)
fi

sed -e "s|@PF_CERT@|${PF_CERT:-$root/$PF_HOSTNAME/fullchain.pem}|g" \
    -e "s|@PF_KEY@|${PF_KEY:-$root/$PF_HOSTNAME/privkey.pem}|g" \
    -e "s|@PEEK_CERT@|${PEEK_CERT:-$root/$PEEK_HOSTNAME/fullchain.pem}|g" \
    -e "s|@PEEK_KEY@|${PEEK_KEY:-$root/$PEEK_HOSTNAME/privkey.pem}|g" \
    -e "s|@GRIST_CERT@|${GRIST_CERT:-$root/$GRIST_HOSTNAME/fullchain.pem}|g" \
    -e "s|@GRIST_KEY@|${GRIST_KEY:-$root/$GRIST_HOSTNAME/privkey.pem}|g" \
    -e "s|@PF@|$PF_HOSTNAME|g" -e "s|@PEEK@|$PEEK_HOSTNAME|g" -e "s|@GRIST@|$GRIST_HOSTNAME|g" \
    "$here/privacyfence-suite.conf.template" |
    if [ -n "$zone" ]; then
        echo "render: $zone already defines the pf_oauth zone; the site uses it" >&2
        sed "s|^limit_req_zone .*zone=pf_oauth.*|# & (already defined in $zone)|"
    else
        cat
    fi

# $request_uri is nginx's, not the shell's.
# shellcheck disable=SC2016
for name in ${PEEK_REDIRECT_HOSTNAMES:-}; do
    printf '\n# %s redirects to Peek'"'"'s one name.\nserver {\n' "$name"
    printf '    listen 443 ssl http2;\n    server_name %s;\n' "$name"
    printf '    ssl_certificate     %s;\n    ssl_certificate_key %s;\n' "$root/$name/fullchain.pem" "$root/$name/privkey.pem"
    printf '    ssl_protocols TLSv1.2 TLSv1.3;\n    return 301 https://%s$request_uri;\n}\n' "$PEEK_HOSTNAME"
    printf 'server {\n    listen 80;\n    server_name %s;\n    return 301 https://%s$request_uri;\n}\n' "$name" "$PEEK_HOSTNAME"
done
