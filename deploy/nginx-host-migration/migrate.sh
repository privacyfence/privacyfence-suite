#!/usr/bin/env bash
# Moves a pip PrivacyFence 7.x + separate Peek and Grist containers into this folder's stack,
# keeping every app's data. Run as root in this folder, after README.md step 1.
#
#   ./migrate.sh preflight     read-only checks; changes nothing
#   ./migrate.sh copy          stops the old services and copies their data into the stack's volumes
#   ./migrate.sh nginx         prints the rendered nginx site (README.md, step 5); writes nothing
#   ./migrate.sh nginx-files   lists the nginx files that serve the three names (README.md, step 5)
#   ./migrate.sh rollback      stops the stack and starts the old services again
#
# The old data is only read, never changed or deleted, so rollback returns to the state at `copy`.
set -euo pipefail

cd "$(dirname "$0")"
PROJECT=privacyfence-host
STATE=.migrate-state
ALPINE=alpine:3.22

die() { printf 'migrate: %s\n' "$*" >&2; exit 1; }
ok() { printf '  ok    %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
section() { printf '\n== %s\n' "$*"; }
WARNINGS=0
FAILURES=0

[ "$(id -u)" = 0 ] || die "run as root"
[ -f .env ] || die "missing .env (cp .env.example .env and fill it in)"
set -a
# shellcheck disable=SC1091
. ./.env
set +a
OLD_PF_DATA=${OLD_PF_DATA:-/var/lib/privacyfence-org/.privacyfence}
OLD_PF_UNIT=${OLD_PF_UNIT:-privacyfence-org}
OLD_PEEK_CONTAINER=${OLD_PEEK_CONTAINER:-peek}
OLD_GRIST_CONTAINER=${OLD_GRIST_CONTAINER:-grist}

container_exists() { docker inspect "$1" >/dev/null 2>&1; }
container_running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ]; }
has_mount() { docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$1" | grep -qx "$2"; }
volume_empty() {
    # volume_empty NAME: true if the volume is missing or holds no file (empty folders, such as the
    # ones Docker copies from an image into a new volume, do not count)
    docker volume inspect "$1" >/dev/null 2>&1 || return 0
    [ -z "$(docker run --rm -v "$1:/v:ro" "$ALPINE" find /v -mindepth 1 ! -type d -print -quit)" ]
}

clear_volume() {
    # clear_volume NAME: removes everything inside the volume (used only on the stack's own new volumes)
    docker run --rm -v "$1:/v" "$ALPINE" find /v -mindepth 1 -delete
}

# old_peek_google_org_signup: prints the old Peek's stored auth_google_org_signup value, or "unknown".
# Reads a copy of the database inside a throwaway container, so the old data stays untouched.
old_peek_google_org_signup() {
    docker run --rm --volumes-from "$OLD_PEEK_CONTAINER:ro" "$ALPINE" sh -c \
        'apk add -q --no-cache sqlite >/dev/null 2>&1 || exit 3; mkdir /tmp/p && cp /data/peek.db* /tmp/p/ && sqlite3 /tmp/p/peek.db "$0"' \
        "SELECT value FROM settings WHERE key='auth_google_org_signup';" 2>/dev/null || echo unknown
}

is_true() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
        1 | true | yes | on) return 0 ;;
        *) return 1 ;;
    esac
}

# nginx_conf_dump: the configuration nginx loads, or nothing when nginx is not installed.
nginx_conf_dump() {
    command -v nginx >/dev/null 2>&1 || return 0
    nginx -T 2>/dev/null || true
}

# existing_pf_oauth_zone: the file, other than this kit's site, that already defines the pf_oauth zone.
existing_pf_oauth_zone() {
    nginx_conf_dump | awk '/^# configuration file /{f=$4; sub(/:$/,"",f)}
        f !~ /privacyfence-suite\.conf$/ && /^[[:space:]]*limit_req_zone[[:space:]].*zone=pf_oauth:/ {print f; exit}'
}

# nginx_files: the files whose server_name lists one of the names (not this kit's own site).
nginx_files() {
    nginx_conf_dump | awk -v names="$PF_HOSTNAME $PEEK_HOSTNAME $GRIST_HOSTNAME ${OLD_EXTRA_HOSTNAMES:-}" '
        BEGIN { n = split(names, a, " "); for (i = 1; i <= n; i++) want[a[i]] = 1 }
        /^# configuration file / { f = $4; sub(/:$/, "", f); next }
        f ~ /privacyfence-suite\.conf$/ { next }
        $1 == "server_name" { for (i = 2; i <= NF; i++) { t = $i; sub(/;$/, "", t); if (t in want) print f } }
    ' | sort -u
}

# grist_py ARGS...: runs the Python on stdin in the old Grist container (it reads the home database read-only).
grist_py() {
    docker exec -i "$OLD_GRIST_CONTAINER" python3 - "$@"
}

# report TEXT: prints ok/WARN/FAIL lines produced elsewhere and counts them.
report() {
    printf '%s\n' "$1"
    WARNINGS=$((WARNINGS + $(printf '%s\n' "$1" | grep -c '^  WARN' || true)))
    FAILURES=$((FAILURES + $(printf '%s\n' "$1" | grep -c '^  FAIL' || true)))
}

preflight() {
    section "tools"
    docker compose version --short >/dev/null 2>&1 || fail "docker compose v2 is missing (Ubuntu: apt-get install docker-compose-v2; Docker's packages: docker-compose-plugin)"
    local v
    v=$(docker compose version --short 2>/dev/null || echo 0)
    if [ "$(printf '%s\n2.24.0\n' "${v#v}" | sort -V | head -1)" = 2.24.0 ]; then ok "compose $v"; else fail "compose $v is older than 2.24"; fi
    if docker compose config -q 2>/dev/null; then ok "compose.yaml and .env resolve"; else fail "docker compose config fails: fill in .env and privacyfence.env"; fi
    if [ -f privacyfence.env ]; then ok "privacyfence.env present"; else fail "missing privacyfence.env (README.md, step 2)"; fi
    if [ -f privacyfence.env ] && grep -q '^PRIVACYFENCE_IDP_CLIENT_SECRET_FILE=' privacyfence.env; then
        grep -q '^PRIVACYFENCE_IDP_CLIENT_SECRET_FILE=/run/suite/idp_client_secret$' privacyfence.env \
            || fail "privacyfence.env: PRIVACYFENCE_IDP_CLIENT_SECRET_FILE must be /run/suite/idp_client_secret"
        if [ -s secrets/idp_client_secret ]; then ok "secrets/idp_client_secret present"; else fail "missing secrets/idp_client_secret"; fi
    fi
    if [ -f privacyfence.env ] && grep -Eq '^PRIVACYFENCE_(PEEK|GRIST)_PROVISIONING_KEY' privacyfence.env; then
        warn "privacyfence.env sets a provisioning key; remove it (the stack generates and installs its own)"
    fi

    section "PrivacyFence (pip)"
    if [ -d "$OLD_PF_DATA" ]; then ok "data directory $OLD_PF_DATA"; else fail "no data directory at $OLD_PF_DATA (OLD_PF_DATA)"; fi
    local pfver=""
    if [ -x /opt/privacyfence/venv/bin/pip ]; then
        pfver=$(/opt/privacyfence/venv/bin/pip show privacyfence 2>/dev/null | awk '/^Version:/{print $2}')
    fi
    case "$pfver" in
        7.*) ok "pip install is $pfver" ;;
        "") warn "could not read the pip version from /opt/privacyfence/venv" ;;
        *) fail "pip install is $pfver: upgrade it to 7.x first (README.md, step 1)" ;;
    esac
    if [ -n "$pfver" ] && [ "$pfver" != "${PRIVACYFENCE_IMAGE_TAG:-}" ]; then
        warn "PRIVACYFENCE_IMAGE_TAG=${PRIVACYFENCE_IMAGE_TAG:-} but the pip install runs $pfver; use the same version for the move"
    fi
    if [ -f "$OLD_PF_DATA/org/org_bundle.json" ]; then
        warn "org/org_bundle.json is still there: retire the bundle first (README.md, step 1), or its settings win over privacyfence.env"
    else
        ok "no active 6.x bundle"
    fi

    section "Peek (container $OLD_PEEK_CONTAINER)"
    if container_exists "$OLD_PEEK_CONTAINER"; then
        ok "image $(docker inspect -f '{{.Config.Image}}' "$OLD_PEEK_CONTAINER"), version $(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$OLD_PEEK_CONTAINER")"
        if has_mount "$OLD_PEEK_CONTAINER" /data; then ok "data mounted at /data"; else fail "$OLD_PEEK_CONTAINER has no mount at /data"; fi
        if docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$OLD_PEEK_CONTAINER" | grep -q '^PEEK_GOOGLE_ORG_SIGNUP=true'; then
            warn "the old Peek sets PEEK_GOOGLE_ORG_SIGNUP=true; the stack uses SSO sign-up, which cannot be combined with it"
        fi
    else
        fail "no container $OLD_PEEK_CONTAINER (OLD_PEEK_CONTAINER)"
    fi
    if container_exists "$OLD_PEEK_CONTAINER"; then
        local gos
        gos=$(old_peek_google_org_signup)
        if [ "$gos" = unknown ]; then
            warn "could not read the old Peek's stored Google org sign-up setting (needs apk to reach the Alpine mirrors)"
        elif is_true "$gos"; then
            echo "  info  the old Peek has Google org sign-up on; copy switches it off in the copied database, because the stack uses sign-up through PrivacyFence"
        else
            ok "Google org sign-up is off in the old Peek"
        fi
    fi
    echo "  info  PEEK_PROVISIONING_KEY_NAME=${PEEK_PROVISIONING_KEY_NAME:-PrivacyFence}: a provisioning key with this name in Peek is rotated in place, otherwise a new one is registered"

    section "Grist (container $OLD_GRIST_CONTAINER)"
    if ! container_exists "$OLD_GRIST_CONTAINER"; then
        fail "no container $OLD_GRIST_CONTAINER (OLD_GRIST_CONTAINER)"
    elif ! container_running "$OLD_GRIST_CONTAINER"; then
        fail "$OLD_GRIST_CONTAINER is not running; preflight reads its database through it"
    else
        if has_mount "$OLD_GRIST_CONTAINER" /persist; then ok "data mounted at /persist"; else fail "$OLD_GRIST_CONTAINER has no mount at /persist"; fi
        local env gv want
        env=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$OLD_GRIST_CONTAINER")
        if printf '%s\n' "$env" | grep -Eq '^TYPEORM_TYPE=postgres'; then
            fail "the old Grist uses PostgreSQL; the provisioner supports only the SQLite home database"
        fi
        gv=$(docker exec "$OLD_GRIST_CONTAINER" node -p "require('/grist/package.json').version" 2>/dev/null || echo unknown)
        want=${GRIST_IMAGE_TAG%%-*}
        if [ "$gv" = unknown ]; then
            warn "could not read the old Grist's version"
        elif [ "$(printf '%s\n%s\n' "$gv" "$want" | sort -V | tail -1)" != "$want" ]; then
            fail "the old Grist is $gv, newer than $GRIST_IMAGE_TAG: its database cannot be moved back to it"
        elif [ "${gv%.*}" != "${want%.*}" ]; then
            warn "the old Grist is $gv; the provisioner supports grist-core 1.7 (Grist upgrades the database on start)"
        else
            ok "old Grist $gv, new $GRIST_IMAGE_TAG"
        fi

        local htnames="" homedb out
        homedb=$(printf '%s\n' "$env" | sed -n 's/^TYPEORM_DATABASE=//p' | tail -1)
        homedb=${homedb:-/persist/home.sqlite3}
        if [ -n "${OLD_GRIST_HTPASSWD:-}" ] && [ -f "$OLD_GRIST_HTPASSWD" ]; then
            htnames=$(cut -d: -f1 "$OLD_GRIST_HTPASSWD" | tr '\n' ' ')
        fi
        out=$(grist_py "$homedb" "${GRIST_TEAM_SITE:-}" "${GRIST_ADMIN_EMAIL:-}" "${ALLOWED_DOMAIN:-}" "$htnames" \
            < preflight_grist.py 2>&1) || out="$out
  FAIL  could not read Grist's home database"
        report "$out"
    fi

    section "network"
    if ip -o -4 addr show 2>/dev/null | grep -v pf-suite | grep -q ' 172\.30\.87\.'; then
        fail "172.30.87.0/24 is already in use on this host"
    else
        ok "172.30.87.0/24 is free"
    fi
    if ss -ltn 2>/dev/null | grep -q '127\.0\.0\.1:8485 '; then
        fail "127.0.0.1:8485 (the new provisioner's port) is in use"
    else
        ok "127.0.0.1:8485 is free (8765, 7700 and 8484 are freed by copy)"
    fi

    section "nginx"
    if ! command -v nginx >/dev/null 2>&1; then
        warn "nginx is not installed on this host"
    else
        local files zone
        files=$(nginx_files)
        if [ -n "$files" ]; then
            printf '  info  files that serve the three names now (step 5 moves them):\n'
            printf '%s\n' "$files" | sed 's/^/          /'
        else
            warn "no nginx file serves $PF_HOSTNAME, $PEEK_HOSTNAME or $GRIST_HOSTNAME"
        fi
        zone=$(existing_pf_oauth_zone)
        if [ -n "$zone" ]; then
            echo "  info  $zone already defines the pf_oauth zone; the rendered site uses it instead of defining it again"
        fi
    fi

    section "target volumes"
    for v in pf-data peek-data grist-data; do
        if volume_empty "${PROJECT}_$v"; then ok "${PROJECT}_$v empty"; else warn "${PROJECT}_$v already holds data (copy refuses it)"; fi
    done

    printf '\n%d failure(s), %d warning(s)\n' "$FAILURES" "$WARNINGS"
    [ "$FAILURES" = 0 ]
}

copy_into() {
    # copy_into VOLUME DOCKER_ARGS... -- SRC_PATH [CHOWN] [MODE]
    # The volume was checked empty before the stack was created; Docker may since have filled it
    # with the image's own default folders, so it is cleared before the copy.
    local vol=$1; shift
    local args=()
    while [ "$1" != -- ]; do args+=("$1"); shift; done
    shift
    local src=$1 owner=${2:-} mode=${3:-}
    clear_volume "${PROJECT}_$vol"
    local cmd="cp -a $src/. /dst/"
    [ -z "$owner" ] || cmd="$cmd && chown -R $owner /dst"
    [ -z "$mode" ] || cmd="$cmd && chmod $mode /dst"
    docker run --rm "${args[@]}" -v "${PROJECT}_$vol:/dst" "$ALPINE" sh -c "$cmd"
    echo "  copied into ${PROJECT}_$vol"
}

# old_compose_files CONTAINER: the Compose files a container was started from, if any.
old_compose_files() {
    docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$1" 2>/dev/null | tr ',' '\n' | sed '/^$/d'
}

copy() {
    preflight || die "preflight failed; fix the failures first"
    for v in pf-data peek-data grist-data; do
        volume_empty "${PROJECT}_$v" || die "${PROJECT}_$v already holds data; refusing to overwrite"
    done
    section "pulling images and creating the stack (the old services keep running)"
    docker compose pull
    docker compose up --no-start

    printf '\nThis stops %s and the containers %s and %s, then copies their data.\n' \
        "$OLD_PF_UNIT" "$OLD_PEEK_CONTAINER" "$OLD_GRIST_CONTAINER"
    read -r -p "Type yes to continue: " answer
    [ "$answer" = yes ] || die aborted

    section "stopping the old services"
    local parked=() f
    for c in "$OLD_PEEK_CONTAINER" "$OLD_GRIST_CONTAINER"; do
        while read -r f; do
            if [ -f "$f" ]; then mv "$f" "$f.migrated" && parked+=("$f") && echo "  parked $f (so docker compose up there cannot start the old app again)"; fi
        done < <(old_compose_files "$c")
    done
    {
        echo "PEEK_RESTART=$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$OLD_PEEK_CONTAINER")"
        echo "GRIST_RESTART=$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$OLD_GRIST_CONTAINER")"
        echo "PF_ENABLED=$(systemctl is-enabled "$OLD_PF_UNIT" 2>/dev/null || echo disabled)"
        printf 'PARKED=%q\n' "${parked[*]:-}"
    } > "$STATE"
    systemctl disable --now "$OLD_PF_UNIT"
    docker update --restart=no "$OLD_PEEK_CONTAINER" "$OLD_GRIST_CONTAINER" >/dev/null
    docker stop "$OLD_PEEK_CONTAINER" "$OLD_GRIST_CONTAINER" >/dev/null
    echo "  stopped (state saved in $STATE for rollback)"

    section "copying data"
    copy_into pf-data -v "$OLD_PF_DATA:/src:ro" -- /src 10001:10001 0700
    copy_into peek-data --volumes-from "$OLD_PEEK_CONTAINER:ro" -- /data "" 0700
    copy_into grist-data --volumes-from "$OLD_GRIST_CONTAINER:ro" -- /persist

    # The stack signs people up to Peek through PrivacyFence, which Peek refuses next to its own
    # Google org sign-up. Switch that off in the copy; the old Peek's database is not touched.
    docker run --rm -v "${PROJECT}_peek-data:/data" "$ALPINE" sh -c \
        'apk add -q --no-cache sqlite >/dev/null && n=$(sqlite3 /data/peek.db "$0") && chown 65532:65532 /data/peek.db* && echo "$n"' \
        "UPDATE settings SET value='false', updated_at=strftime('%s','now') WHERE key='auth_google_org_signup' AND lower(trim(value)) IN ('1','true','yes','on'); SELECT changes();" \
        | { read -r n || n=""; if [ "$n" = 1 ]; then echo "  switched off Google org sign-up in the copied Peek database"; fi; } \
        || echo "  WARN  could not check Peek's Google org sign-up in the copy; if Peek will not start, see README.md, step 4"

    printf '\nNext: install the new nginx site and start the stack (README.md, step 5).\n'
}

render_nginx() {
    : "${PF_HOSTNAME:?}" "${PEEK_HOSTNAME:?}" "${GRIST_HOSTNAME:?}"
    local root=${CERT_ROOT:-/etc/ssl/certs}
    sed -e "s|@PF_CERT@|${PF_CERT:-$root/$PF_HOSTNAME/fullchain.pem}|g" \
        -e "s|@PF_KEY@|${PF_KEY:-$root/$PF_HOSTNAME/privkey.pem}|g" \
        -e "s|@PEEK_CERT@|${PEEK_CERT:-$root/$PEEK_HOSTNAME/fullchain.pem}|g" \
        -e "s|@PEEK_KEY@|${PEEK_KEY:-$root/$PEEK_HOSTNAME/privkey.pem}|g" \
        -e "s|@GRIST_CERT@|${GRIST_CERT:-$root/$GRIST_HOSTNAME/fullchain.pem}|g" \
        -e "s|@GRIST_KEY@|${GRIST_KEY:-$root/$GRIST_HOSTNAME/privkey.pem}|g" \
        -e "s|@PF@|$PF_HOSTNAME|g" -e "s|@PEEK@|$PEEK_HOSTNAME|g" -e "s|@GRIST@|$GRIST_HOSTNAME|g" \
        nginx/privacyfence-suite.conf.template | {
        local zone
        zone=$(existing_pf_oauth_zone)
        if [ -n "$zone" ]; then
            echo "migrate: $zone already defines the pf_oauth zone; the site uses it" >&2
            sed "s|^limit_req_zone .*zone=pf_oauth.*|# & (already defined in $zone)|"
        else
            cat
        fi
    }
}

rollback() {
    [ -f "$STATE" ] || die "no $STATE: copy never ran here"
    # shellcheck disable=SC1090
    . "./$STATE"
    read -r -p "Stop the stack and start the old services again? Type yes: " answer
    [ "$answer" = yes ] || die aborted
    docker compose stop
    docker update --restart="${PEEK_RESTART:-unless-stopped}" "$OLD_PEEK_CONTAINER" >/dev/null
    docker update --restart="${GRIST_RESTART:-unless-stopped}" "$OLD_GRIST_CONTAINER" >/dev/null
    docker start "$OLD_PEEK_CONTAINER" "$OLD_GRIST_CONTAINER" >/dev/null
    local f
    for f in ${PARKED:-}; do
        if [ -f "$f.migrated" ]; then mv "$f.migrated" "$f" && echo "restored $f"; fi
    done
    if [ "${PF_ENABLED:-enabled}" = enabled ]; then systemctl enable --now "$OLD_PF_UNIT"; else systemctl start "$OLD_PF_UNIT"; fi
    echo "Old services started. Put the old nginx site back and reload nginx (README.md, Rollback)."
    echo "The stack's volumes are kept; 'docker compose down -v' removes them."
}

case "${1:-}" in
    preflight) preflight ;;
    copy) copy ;;
    nginx) render_nginx ;;
    nginx-files) nginx_files ;;
    rollback) rollback ;;
    *) sed -n 2,10p "$0"; exit 2 ;;
esac
