# privacyfence-suite: PrivacyFence, Peek and Grist in one Docker stack, already connected

> This plan lives on the `plan/privacyfence-suite` branch of `privacyfence/privacyfence-suite`,
> together with the repository's profile (`.claude/toolkit.yaml`, also shown in
> [Appendix A](#appendix-a-claudetoolkityaml)). The profile reaches `main` with the feature PR.

## Goal

An organization starts PrivacyFence (organization mode), Peek and Grist with one
`docker compose up -d`. Every person who signs in to PrivacyFence finds Peek and Grist already
connected, and signs in to Peek and Grist **through PrivacyFence**. Nobody has to:

- create a provisioning key, or copy one between containers;
- register Peek or Grist with an identity provider;
- turn a switch on the Admin page.

The repository ships four configurations, each a self-contained folder:

| Folder | Proxy | PrivacyFence signs people in with | Peek and Grist sign in with |
|---|---|---|---|
| `configs/caddy-idp` | Caddy (automatic HTTPS) | the organization's own OIDC identity provider (one client registration, for PrivacyFence only) | PrivacyFence |
| `configs/caddy-google` | Caddy (automatic HTTPS) | PrivacyFence's built-in Google sign-in (nothing to register) | PrivacyFence |
| `configs/nginx-google` | nginx with the operator's certificate | the same as `caddy-google` | PrivacyFence |
| `configs/localhost` | none | single-user mode: setup code, then passkey | PrivacyFence |

PrivacyFence is the OpenID Connect provider for Peek and Grist (the user's decision). Whatever
PrivacyFence uses upstream reaches Peek and Grist as the same identity.

## Current state

- **Nothing exists yet.** The repository does not exist. The starting points are:
  - the compose file in the request: PrivacyFence, Peek, Grist and Caddy on `172.30.87.0/24`, with
    Caddy at `.2` and network aliases for the three public names;
  - PrivacyFence's own `deploy/docker/` files (`compose.yaml`, `Caddyfile`,
    `privacyfence.env.example`), explained in `docs/org-mode-docker.md`.
- **The upstream versions are fixed** (`manual_before` `mb2-upstream-releases`):

  | Repository | Release | Image tag |
  |---|---|---|
  | privacyfence/privacyfence | `v7.0.0b1`, a GitHub **pre-release** | `PRIVACYFENCE_IMAGE_TAG=7.0.0b1` (only this tag; `latest` does not move to a pre-release) |
  | privacyfence/peek | `v0.18.0` | `PEEK_IMAGE_TAG=0.18.0` |
  | privacyfence/grist-provisioner | `v0.2.0` | `GRIST_PROVISIONER_IMAGE_TAG=0.2.0` |
  | privacyfence/grist-core (the fork) | `v1.7.22-pf.2`, published 2026-10-31 | `GRIST_IMAGE_TAG=1.7.22-pf.2` |

  - 7.0.0b1 must include [privacyfence/privacyfence#1051](https://github.com/privacyfence/privacyfence/pull/1051).
    It makes the single-user person `admin@privacyfence.localhost` instead of `admin@localhost`.
    Grist's access API refuses an address whose domain has no dot (grist-core
    `app/common/gutil.ts:26-27` `EMAIL_RE`, used at `UsersManager.ts:841`), so with
    `admin@localhost` the provisioner could never add the person to the team site.
  - GitHub's "latest release" API skips pre-releases, and a PrivacyFence pre-release has no release
    notes of its own (`release.yml`: pre-release tags fold into the version they lead to). So nothing
    in this plan looks versions up through "latest release". The phases use these tags, and check
    PrivacyFence through the tag's own `CHANGELOG.md` and source.
- **What those releases provide:**
  - **PrivacyFence 7.0.0b1.**
    - `PRIVACYFENCE_PEEK_AUTO_PROVISION=true` and `PRIVACYFENCE_GRIST_AUTO_PROVISION=true` offer the
      services and turn automatic accounts on. Any other non-empty value refuses the start.
    - In single-user mode they provision `admin@privacyfence.localhost`, as verified, only against
      `localhost` addresses, at start and at each sign-in (setup code or passkey).
    - Start-time provisioning can fail when Peek or Grist is not up yet. It is retried at the next
      sign-in, or by the six-hourly sweep, whose first run is at start (`peek_provisioning.py:250-291`).
    - `PRIVACYFENCE_OIDC_CLIENTS`, plus `PRIVACYFENCE_OIDC_CLIENT_<NAME>_REDIRECT_URIS` and
      `…_SECRET_FILE`, make PrivacyFence an OIDC provider at `<issuer>/oidc`.
      - The `client_id` is the lower-cased name.
      - A client secret must be at least 32 characters.
      - Redirect URIs match exactly; `http://localhost:<port>` is accepted.
    - The provider:
      - requires PKCE S256;
      - has no consent page and no `end_session_endpoint`;
      - signs with RS256;
      - accepts `client_secret_basic` or `client_secret_post`.

      ID tokens and userinfo carry `sub`, `email`, `email_verified` and `name`.
    - `email_verified` is true for the single-user person and for built-in Google. With your own IdP
      it is true only if the IdP sends it, or with `PRIVACYFENCE_IDP_TRUST_UNVERIFIED_EMAIL=true` for
      an address in an allowed domain (`org_identity.py:490-500`).
    - The single-user issuer is `http://localhost:8765/oidc` (`org_mode.py:378-379`).
    - Every `*_FILE` secret (provisioning keys, OIDC client secrets, the IdP client secret) is read
      **once at start**; a new value needs a restart.
    - `PRIVACYFENCE_ALLOWED_DOMAINS` seeds Admin → Sign-in at the first start of an organization
      server (`admin_config.py:331-332`). It is then enforced with any identity provider
      (`org_identity.py:466-478`). PrivacyFence's own docs say "with builtin-google"; the code wins.
  - **Peek 0.18.0.**
    - Sign-in from the environment, locked on the Admin page: `PEEK_OIDC_ISSUER_URL`,
      `PEEK_OIDC_CLIENT_ID`, `PEEK_OIDC_CLIENT_SECRET_FILE`, `PEEK_OIDC_SIGNUP` (needs an allowed
      domain) and `PEEK_ALLOWED_EMAIL_DOMAIN` (empty allows any address).
    - `PEEK_PROVISIONING_KEY_FILE`, with rotation in place. The key must start with `peekprov_` and
      be at least 40 characters (`internal/peekd/run.go:341`).
    - `PEEK_ADMIN_EMAILS`. Peek refuses to provision an admin's address (409). A provisioned account
      that later becomes admin keeps its token, but the token is refused with 403.
    - `/setup` is skipped when admin emails are set, or when sign-in comes from the environment
      together with a sign-up or a provisioning key file.
      - The line `Peek first-run setup is skipped: <reason>.` goes to stdout, and only while Peek's
        database has no accounts (`internal/server/bootstrap.go:104-112`).
    - `PEEK_OIDC_ALLOW_PRIVATE_ISSUER` (`internal/peekd/run.go:165`) allows an `http://` issuer and
      one at a private address (`internal/server/oauth_config.go:157-168`).
    - Peek's OIDC sign-in:
      - routes are `/oauth/oidc/start` and `/oauth/oidc/callback`;
      - it uses PKCE S256 and a nonce, and requires `email_verified`;
      - it adopts an existing account by email at the first sign-in, whatever the sign-up setting;
      - sign-out is local.
    - `PEEK_TRUSTED_PROXY_CIDRS` defaults to loopback, so the proxy's address must be set.
  - **grist-provisioner 0.2.0.**
    - `PROVISIONER_KEY_FILE`.
    - `PROVISIONER_GRIST_URL`, `PROVISIONER_GRIST_TEAM_SITE` and `PROVISIONER_GRIST_BOOT_KEY_FILE`:
      - must be set together;
      - add a person to the team site through `PATCH /api/orgs/{site}/access` with `x-boot-key`,
        which creates the Grist user;
      - require `PROVISIONER_ALLOWED_DOMAINS`.
    - It refuses `GRIST_ADMIN_EMAIL` (and `GRIST_DEFAULT_EMAIL`, `GRIST_SUPPORT_EMAIL`) with 409.
    - It writes Grist's `/persist/home.sqlite3` (`GRIST_HOME_DB`) and its own `/data/provisioner.sqlite3`.
    - The image entry point is `grist-provisioner` (command `serve`), on port 8485, with `/healthz`
      and `python` on `PATH`.
    - `grist-provisioner check` prints `ok: N Grist users, M linked`, then `team site: <site>`.
    - Routes: `/api/provisioning/self` and `/api/provisioning/accounts/{id}[/key]`. There is no path
      prefix.
- **Facts the design rests on:**
  - **PrivacyFence.**
    - Addresses: `http://` only for `localhost`, `127.0.0.1` and `::1` (`grist_auth.py:72-97`,
      `peek_client.py:63-84`). The variables are at `oauth_apps.py:56-58`.
    - The Host allowlist is `127.0.0.1`, `::1` and the issuer's host (`web/server.py:1691-1695`; the
      image binds `0.0.0.0`, which is left out). A request with any other Host, such as
      `privacyfence:8765`, gets 400. So the proxies pass the original `Host`, and nothing calls
      PrivacyFence by its service name.
    - The single-user setup code appears in the log as `Setup code: XXXX-XXXX. Open …`
      (`web/single_user_auth.py:276`).
      - `GET /login` sets the `pf_setup_binding` cookie (`Path=/login`) and hidden `binding` and
        `next` fields.
      - `POST /login/setup` answers 303 to `/security?next=…` with `pf_org_session`
        (`single_user_auth.py:361-396`).
      - `check_origin` accepts a missing `Origin` (`web/org_session.py:205-207`).
      - Over `http://` the cookies have no `Secure` and no `Domain`.
      - `/oidc/authorize` needs only a live session; no passkey is required.
      - Five wrong codes use the code up, and a restart with no passkey prints a new one.
    - The image runs as uid 10001, read-only, with data in `/var/lib/privacyfence-org/.privacyfence`.
      Its HEALTHCHECK probes `127.0.0.1`. Single-user credentials live in
      `users/single-user/credentials/{peek,grist}_token.json` under that directory.
    - A volume that once ran with an identity provider refuses a single-user start. Each
      configuration's Compose project name keeps its volumes apart.
  - **Peek.** The image is `FROM scratch` with uid and gid 65532 and no shell. It serves `/healthz`
    on 7700, and its exec-form HEALTHCHECK needs no shell. Data is in `/data`; large uploads spill
    to `/tmp`, so the tmpfs is needed.
  - **Grist.**
    - The image starts as root, chowns `/persist` and drops to `grist` (uid 1001, checked in CI).
    - It reads secrets only from the environment.
    - Its OIDC discovery runs server-side at start. With `GRIST_IN_SERVICE=true`, a failure stops
      the start.
    - It requires `email_verified === true`.
    - Its callback is `/oauth2/callback` under `APP_HOME_URL`, and its default protections are PKCE
      and state.
    - Without an `end_session_endpoint` it needs `GRIST_OIDC_IDP_SKIP_END_SESSION_ENDPOINT=true`.
    - `GRIST_SINGLE_ORG=team` creates the `team` site at start, owned by `GRIST_ADMIN_EMAIL`.
    - New users do not join the team site by themselves.
    - Its access API refuses an email whose domain has no dot.
    - Grist lists OIDC as a full-edition feature, and upstream's `gristlabs/grist` image can switch
      itself to the paid edition. The suite therefore uses PrivacyFence's fork instead (next bullet).
- **The Grist image comes from PrivacyFence's fork** (`privacyfence/grist-core`, `pf/README.md`).
  - The fork builds upstream's unchanged `Dockerfile` with no full-edition extensions, channel `core`
    and an empty `GRIST_EXT_FULL_EDITION_BASE_URL`, so the full-edition switch is off. It publishes
    `ghcr.io/privacyfence/grist-core:X.Y.Z-pf.N` for amd64 and arm64, with build provenance.
  - Every fork build runs a lock-out check:
    - OIDC sign-in;
    - API keys;
    - the boot key;
    - the team-site access API;
    - the free plan's limits.

    A Grist release that gates any of them is not released by the fork.
  - The current release is `1.7.22-pf.2`, built from upstream `v1.7.22`.
  - The upstream Dockerfile has `WORKDIR /grist`, `ENTRYPOINT ["./sandbox/docker_entrypoint.sh"]`
    and `CMD ["./sandbox/run.sh"]`. The final stage is `node:22-trixie-slim`, which has `/bin/sh`
    and Node 22's global `fetch`. The `grist-image` CI job confirms these against the pinned tag.

## Design

### Repository layout

```
README.md                      quick start per configuration, what "already connected" means
CHANGELOG.md                   "## [Unreleased]"
LICENSE                        Apache-2.0 (created with the repository)
.claude/toolkit.yaml           Appendix A (on the plan branch; reaches main with the feature PR)
.gitignore
requirements-dev.txt           pyyaml==6.0.2, pytest==8.4.2, ruff==0.14.1
pyproject.toml                 ruff and pytest settings only
common/init.sh                 the one copy of the secret-generating script
scripts/check_configs.py       consistency checks (below), standard library + PyYAML
tests/test_check_configs.py    tests for it; fixtures under tests/fixtures/good/ and tests/fixtures/proxy/
tests/e2e/oidc_signin.py       the scripted localhost sign-in (standard library only)
configs/<name>/compose.yaml    self-contained: an operator copies one folder
configs/<name>/.env.example    every variable the folder uses, image tags pinned
configs/<name>/init.sh         byte-identical copy of common/init.sh (checked)
configs/caddy-*/Caddyfile
configs/caddy-idp/secrets/.gitkeep and README.md
configs/nginx-google/templates/default.conf.template
configs/nginx-google/certs/README.md   which two files to put there
docs/configurations.md         every variable, per configuration
docs/operations.md             upgrade, backup, rotating secrets, removing people, troubleshooting
.github/workflows/ci.yml       lint (below)
.github/workflows/e2e-localhost.yml
```

Each folder is self-contained, because the request asks for "a stack" an operator copies and runs,
and Compose's `extends` across folders would tie every folder to the repository layout. The cost is
duplication, which `scripts/check_configs.py` keeps honest.

`.gitignore`:

```
.env
secrets/*
configs/*/secrets/*
!configs/*/secrets/.gitkeep
!configs/*/secrets/README.md
configs/*/certs/*.pem
__pycache__/
.pytest_cache/
```

### Services and addresses (all configurations)

| Service | Image | Fixed address (proxy configs) | Port inside |
|---|---|---|---|
| `init` | `alpine:${ALPINE_IMAGE_TAG:?pin a version in .env}` | none (`network_mode: none`) | |
| `privacyfence` | `ghcr.io/privacyfence/privacyfence-org:${PRIVACYFENCE_IMAGE_TAG:?pin a version in .env}` | `172.30.87.10` | 8765 |
| `peek` | `ghcr.io/privacyfence/peek:${PEEK_IMAGE_TAG:?pin a version in .env}` | `172.30.87.11` | 7700 |
| `grist` | `ghcr.io/privacyfence/grist-core:${GRIST_IMAGE_TAG:?pin a version in .env}` | `172.30.87.12` | 8484 |
| `grist-provisioner` | `ghcr.io/privacyfence/grist-provisioner:${GRIST_PROVISIONER_IMAGE_TAG:?pin a version in .env}` | `172.30.87.13` | 8485 |
| `caddy` / `nginx` | `caddy:${CADDY_IMAGE_TAG:?pin a version in .env}` / `nginx:${NGINX_IMAGE_TAG:?pin a version in .env}` | `172.30.87.2` | 80, 443 |

- **Images.** `.env.example` pins a version for every image, never `latest`:
  - `PRIVACYFENCE_IMAGE_TAG=7.0.0b1`
  - `PEEK_IMAGE_TAG=0.18.0`
  - `GRIST_IMAGE_TAG=1.7.22-pf.2`
  - `GRIST_PROVISIONER_IMAGE_TAG=0.2.0`
  - `ALPINE_IMAGE_TAG=3.22` (a minor series, which is enough for a busybox script)
  - `CADDY_IMAGE_TAG=2.10.2`
  - `NGINX_IMAGE_TAG=1.28.0`

  The request's `ghcr.io/andras-tkcs/peek` is replaced by `ghcr.io/privacyfence/peek`, where Peek's
  release workflow publishes. The suite moves to a newer release only through a PR that changes these
  tags, so CI runs against it.
- **Compose form.** Every `environment:` block is written in mapping form (`KEY: value`), never as a
  list.
- **Hardening.**
  - `privacyfence`, `peek` and `grist-provisioner` are `read_only: true`, with `cap_drop: [ALL]`,
    `security_opt: [no-new-privileges:true]` and `tmpfs: [/tmp]`.
  - `grist` keeps the image defaults, because its entrypoint chowns `/persist` as root and drops
    privileges itself.
  - Every service except `init` has `restart: unless-stopped`.
- **Network** (proxy configurations).
  - The network is `pf`, with subnet `172.30.87.0/24`.
  - The proxy has the aliases `${PF_HOSTNAME:?…}`, `${PEEK_HOSTNAME:?…}` and `${GRIST_HOSTNAME:?…}`,
    so the containers reach the public `https://` names through the proxy, without hairpin NAT. That
    covers PrivacyFence calling Peek and the provisioner, and Peek and Grist calling PrivacyFence's
    `/oidc` endpoints.
- **`depends_on`** (no cycle):
  - every service except `init`: `init` with `condition: service_completed_successfully`;
  - `grist` also depends on `privacyfence` with `condition: service_healthy`;
  - `grist-provisioner` also depends on `grist` with `condition: service_healthy`;
  - the proxy depends **only** on `init`. Grist reaches PrivacyFence through the proxy, so the proxy
    must not wait for Grist, or start-up deadlocks.
- **Health checks.**
  - `grist`: `["CMD", "node", "-e", "fetch('http://localhost:8484/status').then(r=>process.exit(r.ok?0:1),()=>process.exit(1))"]`,
    interval 10s, retries 60, start period 60s.
  - `grist-provisioner`:
    `["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8485/healthz', timeout=3)"]`.
  - `privacyfence` and `peek`: their images' own `HEALTHCHECK`.
- **Volumes.**
  - `pf-data`, `peek-data`, `provisioner-data`;
  - `grist-data`, which is Grist's `/persist` and is also mounted by the provisioner;
  - the four secret volumes below;
  - and, for Caddy, `caddy-data` and `caddy-config`.

### Secrets: generated once, one volume per consumer

`init` runs `init.sh` as root on every `docker compose up`, through `command: ["/bin/sh", "/init.sh"]`
with no `entrypoint:`, so `docker compose run --rm --no-deps init <cmd>` runs another command
(`docs/operations.md` uses that). It mounts `./init.sh:/init.sh:ro` and
four volumes, read-write:

- `pf-secrets:/out/pf`
- `peek-secrets:/out/peek`
- `grist-secrets:/out/grist`
- `provisioner-secrets:/out/provisioner`

Only `caddy-idp`'s `init` also mounts `./secrets:/user-secrets:ro`. Each app mounts only its own
volume, read-only at `/run/suite`. The proxy mounts none, so no container can read a secret it does
not use.

`init.sh` is POSIX `sh`, busybox only, with `set -eu` and `umask 077`. It runs these steps in order:

1. **Directories.** `chmod 0755` each `/out/*` directory.
2. **Shared values.** For each value below, the first time it runs (no `/out/pf/.<name>` marker
   value, which is the canonical copy and is root-only, `0400`), it generates
   `<prefix>` + 32 random bytes from `/dev/urandom`, base64url without padding (43 characters):
   `head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'`. It prints
   `init: generated <name>`, never the value.
3. **Copies.** It installs each value into every consumer's volume as `<name>`, owned by that
   consumer and mode `0400`. It writes a temp file, `chown`s, `chmod`s, then `mv`s it, on every run,
   so ownership is always right.

| Value | Prefix | Copies (volume: owner) |
|---|---|---|
| `peek_provisioning_key` | `peekprov_` | pf: `10001:10001`, peek: `65532:65532` |
| `grist_provisioning_key` | `gristprov_` | pf: `10001:10001`, provisioner: `1001:1001` |
| `peek_oidc_client_secret` | none | pf: `10001:10001`, peek: `65532:65532` |
| `grist_oidc_client_secret` | none | pf: `10001:10001`, grist: `0:0` |
| `grist_boot_key` | none | grist: `0:0`, provisioner: `1001:1001` |
| `grist_session_secret` | none | grist: `0:0` |

- **Grist's files are root-owned**, because only Grist's root wrapper reads them, before the image
  entrypoint drops to uid 1001. The values do reach the Grist process, because the wrapper exports
  them into its environment, which is how Grist reads them anyway. Root ownership only keeps them
  out of reach of something running as uid 1001 that does not inherit that environment. It is not a
  stronger boundary than upstream's own environment variables.
- **The operator's secret** (`caddy-idp` only). If `/user-secrets/idp_client_secret` exists, it is
  installed on every run as `/out/pf/idp_client_secret`, owned `10001:10001`, mode `0400`, so a
  rotation takes effect at the next `up`. The operator writes that file on the host with
  `install -m 0600 /dev/null secrets/idp_client_secret`, then puts the value in it. Under rootless
  Docker or userns-remap, `init`'s root may not read a `0600` host file; the README says to make it
  readable to the Docker user in that case.
- **Never in config files.** No secret is ever in `.env` or `compose.yaml`.
- **Formats the apps check:**
  - Peek's key must start with `peekprov_` and be at least 40 characters; it is 52.
  - PrivacyFence's OIDC client secrets must be at least 32 characters; they are 43.
- **Read at start.** PrivacyFence and Grist read these values once at start. A new value takes
  effect only when the container is recreated (`docs/operations.md`).
- **Uids.** The uids are fixed: 10001 (PrivacyFence image), 65532 (Peek image), 1001 (Grist's `grist`
  user, checked in CI). There is no knob to change them.

**Rejected:**

- **Compose file secrets.** They cannot set a different owner per consuming container without swarm.
- **One shared secrets volume.** Every container, the proxy included, could read every secret.
- **A `setup.sh` the operator runs once.** It is one more step, and the request is "no provision key
  needed".

### Grist's secrets from files, and waiting for PrivacyFence

Grist reads only environment variables and fetches PrivacyFence's discovery document at start. In the
proxy configurations, that goes through the proxy, which may still be obtaining its first
certificate. So Grist's service wraps the image entrypoint:

```yaml
entrypoint:
  - /bin/sh
  - -c
  - |
    export GRIST_SESSION_SECRET="$$(cat /run/suite/grist_session_secret)"
    export GRIST_BOOT_KEY="$$(cat /run/suite/grist_boot_key)"
    export GRIST_OIDC_IDP_CLIENT_SECRET="$$(cat /run/suite/grist_oidc_client_secret)"
    node -e "const u=process.env.GRIST_OIDC_IDP_ISSUER+'/.well-known/openid-configuration';let n=0;const t=()=>fetch(u).then(r=>{if(!r.ok)throw 0;process.exit(0)}).catch(()=>{if(++n>=60){console.error('grist: PrivacyFence is not reachable at '+u);process.exit(1)}setTimeout(t,5000)});t()"
    exec ./sandbox/docker_entrypoint.sh "$$@"
  - grist
command: ["./sandbox/run.sh"]
```

These are upstream's `ENTRYPOINT ["./sandbox/docker_entrypoint.sh"]` and `CMD ["./sandbox/run.sh"]`,
relative to `WORKDIR /grist`. The `grist-image` CI job (below) checks that
`docker image inspect ghcr.io/privacyfence/grist-core:<GRIST_IMAGE_TAG>` still shows exactly these.

### Sign-in wiring: PrivacyFence as the OIDC provider (all configurations)

`<PF>`, `<PEEK>` and `<GRIST>` are the public origins:

- proxy configurations: `https://${PF_HOSTNAME}`, `https://${PEEK_HOSTNAME}`,
  `https://${GRIST_HOSTNAME}`;
- localhost: `http://localhost:8765`, `http://localhost:7700`, `http://localhost:8484`.

**privacyfence:**

```
PRIVACYFENCE_OIDC_CLIENTS: peek,grist
PRIVACYFENCE_OIDC_CLIENT_PEEK_REDIRECT_URIS: <PEEK>/oauth/oidc/callback
PRIVACYFENCE_OIDC_CLIENT_PEEK_SECRET_FILE: /run/suite/peek_oidc_client_secret
PRIVACYFENCE_OIDC_CLIENT_GRIST_REDIRECT_URIS: <GRIST>/oauth2/callback
PRIVACYFENCE_OIDC_CLIENT_GRIST_SECRET_FILE: /run/suite/grist_oidc_client_secret
```

**peek:**

```
PEEK_OIDC_ISSUER_URL: <PF>/oidc
PEEK_OIDC_CLIENT_ID: peek
PEEK_OIDC_CLIENT_SECRET_FILE: /run/suite/peek_oidc_client_secret
PEEK_OIDC_ALLOW_PRIVATE_ISSUER: "true"
```

The flag is needed because, inside the stack, `${PF_HOSTNAME}` resolves to the proxy's private
address, and on localhost the issuer is `http://localhost`.

**grist** (its client secret comes through the wrapper):

```
GRIST_OIDC_IDP_ISSUER: <PF>/oidc
GRIST_OIDC_IDP_CLIENT_ID: grist
GRIST_OIDC_IDP_SCOPES: openid email profile
GRIST_OIDC_IDP_SKIP_END_SESSION_ENDPOINT: "true"
```

Signing out of Peek or Grist ends only that app's session; the PrivacyFence session stays.

### Admins

- **PrivacyFence admins:** `ADMIN_EMAILS` (`PRIVACYFENCE_ADMIN_EMAILS`).
- **Peek admins: `PEEK_ADMIN_EMAILS`, a separate, optional variable** (empty by default, `.env`).
  - A Peek admin's account is not connected automatically: Peek refuses to provision admins. The
    person connects Peek by hand on PrivacyFence's `/connect`.
  - Each address must be in `ALLOWED_DOMAIN`.
  - The README recommends a dedicated admin address.
  - With it empty, `/setup` is still skipped (sign-in, sign-up and the provisioning key come from the
    environment), and Peek has no admin. Every Peek setting the suite needs comes from the
    environment.
- **Grist install admin: `GRIST_ADMIN_EMAIL`** (required in the proxy configurations).
  - It must be a real address in the organization that can sign in to PrivacyFence, because Grist
    signs people in only through PrivacyFence.
  - That person's automatic Grist key is refused (409, "connect it by hand"); they paste their own key
    on `/connect` if they want PrivacyFence to reach Grist. The README recommends a dedicated admin
    address.
  - On localhost the Grist admin is `grist-admin@privacyfence.localhost`, which nobody can sign in as. The install
    is administered through the boot key only, and the README says so.

### Per-app settings shared by the proxy configurations

`ALLOWED_DOMAIN` takes exactly one domain (`.env.example` says so). It feeds PrivacyFence's,
Peek's and the provisioner's domain settings in every proxy configuration.
- PrivacyFence takes it only at its first start, into Admin → Sign-in, and enforces it there with
  any identity provider.
- A later change of `ALLOWED_DOMAIN` reaches Peek and the provisioner, but PrivacyFence needs it
  changed on the Admin page; the README says so.

**privacyfence** gets these in `environment:`, plus the optional
`env_file: [{path: privacyfence.env, required: false}]` for extras such as an Entra group claim:

```
PRIVACYFENCE_ISSUER_URL: https://${PF_HOSTNAME:?set PF_HOSTNAME in .env}
PRIVACYFENCE_TRUSTED_PROXIES: 172.30.87.2
PRIVACYFENCE_ADMIN_EMAILS: ${ADMIN_EMAILS:?set ADMIN_EMAILS in .env}
PRIVACYFENCE_ALLOWED_DOMAINS: ${ALLOWED_DOMAIN:?set ALLOWED_DOMAIN in .env}
PRIVACYFENCE_PEEK_BASE_URL: https://${PEEK_HOSTNAME:?set PEEK_HOSTNAME in .env}
PRIVACYFENCE_PEEK_PROVISIONING_KEY_FILE: /run/suite/peek_provisioning_key
PRIVACYFENCE_PEEK_AUTO_PROVISION: "true"
PRIVACYFENCE_GRIST_SERVER_URL: https://${GRIST_HOSTNAME:?set GRIST_HOSTNAME in .env}
PRIVACYFENCE_GRIST_PROVISIONER_URL: https://${GRIST_HOSTNAME:?set GRIST_HOSTNAME in .env}
PRIVACYFENCE_GRIST_PROVISIONING_KEY_FILE: /run/suite/grist_provisioning_key
PRIVACYFENCE_GRIST_AUTO_PROVISION: "true"
```

**How PrivacyFence reaches the provisioner.**

- **Through Grist's hostname.** PrivacyFence needs an `https://` address for the provisioner, so the
  provisioner shares Grist's hostname.
- **Only from PrivacyFence.** The proxy sends `/api/provisioning/*` to the provisioner only from
  PrivacyFence's fixed address (`172.30.87.10`) and answers 404 to everyone else. The proxy sees the
  direct peer, and outside clients arrive from the bridge gateway.
- **No clash.** Grist has no `/api/provisioning` route, and no fourth hostname or certificate is
  needed.
- **Why Peek differs.** Peek's own `/api/provisioning/*` stays public behind its key: it is part of
  Peek and needs no proxy rule. The provisioner is a separate service that writes Grist's database,
  so it gets the extra network restriction.

**peek:**

```
PEEK_BASE_URL: https://${PEEK_HOSTNAME:?set PEEK_HOSTNAME in .env}
PEEK_TRUSTED_PROXY: "true"
PEEK_TRUSTED_PROXY_CIDRS: 172.30.87.2/32
PEEK_ADMIN_EMAILS: ${PEEK_ADMIN_EMAILS:-}
PEEK_ALLOWED_EMAIL_DOMAIN: ${ALLOWED_DOMAIN:?set ALLOWED_DOMAIN in .env}
PEEK_OIDC_SIGNUP: "true"
PEEK_PROVISIONING_KEY_FILE: /run/suite/peek_provisioning_key
```

**grist:**

```
APP_HOME_URL: https://${GRIST_HOSTNAME:?set GRIST_HOSTNAME in .env}
GRIST_SINGLE_ORG: ${GRIST_TEAM_SITE:-team}
GRIST_ADMIN_EMAIL: ${GRIST_ADMIN_EMAIL:?set GRIST_ADMIN_EMAIL in .env}
GRIST_IN_SERVICE: "true"
GRIST_ORG_CREATION_ANYONE: "false"
GRIST_PERSONAL_ORGS: "false"
GRIST_FORCE_LOGIN: "true"
```

What these do, as confirmed by research for the request's comment:

- `GRIST_ORG_CREATION_ANYONE=false` lets only admins create team sites.
- `GRIST_PERSONAL_ORGS=false` gives new users no personal site.
- `GRIST_FORCE_LOGIN=true` sends anonymous visitors to sign-in.

**grist-provisioner** runs as `user: "1001:1001"`, with volumes `grist-data:/persist`,
`provisioner-data:/data` and `provisioner-secrets:/run/suite:ro`:

```
GRIST_ADMIN_EMAIL: ${GRIST_ADMIN_EMAIL:?set GRIST_ADMIN_EMAIL in .env}
PROVISIONER_KEY_FILE: /run/suite/grist_provisioning_key
PROVISIONER_GRIST_URL: http://grist:8484
PROVISIONER_GRIST_TEAM_SITE: ${GRIST_TEAM_SITE:-team}
PROVISIONER_GRIST_BOOT_KEY_FILE: /run/suite/grist_boot_key
PROVISIONER_ALLOWED_DOMAINS: ${ALLOWED_DOMAIN:?set ALLOWED_DOMAIN in .env}
```

The boot key stays on the internal network: the provisioner talks to Grist directly, never through
the proxy.

### `caddy-idp`: your identity provider, registered once for PrivacyFence

`.env` holds these, with the host names and emails empty in `.env.example` so that Compose refuses
to start until they are set:

- `PF_HOSTNAME`, `PEEK_HOSTNAME`, `GRIST_HOSTNAME`
- `ADMIN_EMAILS`, `ALLOWED_DOMAIN`, `GRIST_ADMIN_EMAIL`, `PEEK_ADMIN_EMAILS` (optional)
- `IDP_ISSUER`, `IDP_CLIENT_ID`
- the image tags

The secret goes in `secrets/idp_client_secret`.

The operator registers **one** confidential OIDC client for PrivacyFence, with the three redirect
URIs listed in `.env.example` and the README:

- `https://<PF_HOSTNAME>/oauth/idp/callback`
- `https://<PF_HOSTNAME>/oauth/idp/login-callback`
- `https://<PF_HOSTNAME>/oauth/stepup/callback`

The privacyfence service adds:

- `PRIVACYFENCE_IDP_ISSUER: ${IDP_ISSUER:?set IDP_ISSUER in .env}`
- `PRIVACYFENCE_IDP_CLIENT_ID: ${IDP_CLIENT_ID:?set IDP_CLIENT_ID in .env}`
- `PRIVACYFENCE_IDP_CLIENT_SECRET_FILE: /run/suite/idp_client_secret`
- `PRIVACYFENCE_IDP_TRUST_UNVERIFIED_EMAIL: ${IDP_TRUST_UNVERIFIED_EMAIL:-false}`

**`email_verified`.** Peek and Grist refuse a sign-in unless `email_verified` is true, and
PrivacyFence passes on what the identity provider says. Some providers never send the claim,
Microsoft Entra ID among them. For those, the operator sets `IDP_TRUST_UNVERIFIED_EMAIL=true`
in `.env`, and PrivacyFence then treats addresses in `ALLOWED_DOMAIN` as verified. This works
only together with the allowed domain, which every proxy configuration sets.
`.env.example` has the variable, commented, with that explanation; the README's caddy-idp quick
start repeats it.

### `caddy-google` and `nginx-google`: Google Workspace, nothing to register

- **`.env`** is as in `caddy-idp`, without the `IDP_*` variables. There is no secret file, no
  `secrets/` folder and no `./secrets` mount.
- **privacyfence** adds `PRIVACYFENCE_IDP: builtin-google`.
- **Who can sign in.** Only verified Google Workspace accounts can sign in, admins included;
  personal Gmail addresses cannot. The container needs outbound HTTPS to `oauth.privacyfence.eu`.
- **The operator's one step.** They publish the `_privacyfence-relay` DNS TXT records listed by
  `docker compose exec privacyfence privacyfence-app --relay-dns-records`. That is PrivacyFence's
  existing procedure, and the README links to it.

### Caddyfile (both Caddy configurations)

```
{$PF_HOSTNAME} {
	reverse_proxy privacyfence:8765
}

{$PEEK_HOSTNAME} {
	reverse_proxy peek:7700
}

{$GRIST_HOSTNAME} {
	@provisioner {
		path /api/provisioning/*
		remote_ip 172.30.87.10
	}
	handle @provisioner {
		reverse_proxy grist-provisioner:8485
	}
	handle /api/provisioning/* {
		respond 404
	}
	handle {
		reverse_proxy grist:8484
	}
}
```

The caddy service:

- gets `PF_HOSTNAME: ${PF_HOSTNAME:?…}`, `PEEK_HOSTNAME: ${PEEK_HOSTNAME:?…}` and
  `GRIST_HOSTNAME: ${GRIST_HOSTNAME:?…}` in `environment:`;
- publishes `80:80`, `443:443` and `443:443/udp`.

Caddy resolves upstreams per request, so it starts before the apps.

### nginx (`nginx-google`)

- **The nginx service.**
  - `environment:` holds `PF_HOSTNAME`, `PEEK_HOSTNAME` and `GRIST_HOSTNAME`, each `${…:?…}`. The
    image's envsubst replaces only variables that are defined in the container.
  - Mounts: `./templates:/etc/nginx/templates:ro` and `./certs:/etc/nginx/certs:ro`.
  - Ports: `80:80` and `443:443`.
- **Certificate.**
  - The operator supplies `certs/fullchain.pem` and `certs/privkey.pem`, covering all three names (SAN
    or wildcard).
  - Rejected: an ACME companion container. It is a second moving part that Caddy already covers, and
    an operator who wants nginx usually has a certificate process.
- **Upstreams use the fixed addresses**, so nginx starts while an app is still down:
  - `http://172.30.87.10:8765` (PrivacyFence)
  - `http://172.30.87.11:7700` (Peek)
  - `http://172.30.87.12:8484` (Grist)
  - `http://172.30.87.13:8485` (the provisioner)

`default.conf.template`:

```
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 80;
    server_name ${PF_HOSTNAME} ${PEEK_HOSTNAME} ${GRIST_HOSTNAME};
    return 301 https://$host$request_uri;
}

# One block per hostname: <HOST> is ${PF_HOSTNAME}, ${PEEK_HOSTNAME} or ${GRIST_HOSTNAME}.
server {
    listen 443 ssl;
    http2 on;
    server_name <HOST>;
    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    client_max_body_size 100m;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # Grist only: websockets. These stay at server level, next to the three above: an nginx
    # location that sets any proxy_set_header of its own inherits none from the server block.
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    location / {
        proxy_pass <UPSTREAM>;
        # PrivacyFence and Peek: MCP streams and server-sent events
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
    # Grist only:
    location /api/provisioning/ {
        allow 172.30.87.10;
        deny all;
        proxy_pass http://172.30.87.13:8485;
    }
}
```

The three server blocks are written out in full in the file. Each block gets only the lines its
comments assign to it: the buffering lines for PrivacyFence and Peek, and the websocket lines and the
provisioning location for Grist. **No `location` sets a `proxy_set_header`**, so every location,
the provisioner's included, passes `Host`, `X-Forwarded-For` and `X-Forwarded-Proto`. Check 12 in
`scripts/check_configs.py` enforces this.

### `localhost`: one person, no proxy

- **One network namespace.** `privacyfence` owns it and publishes `127.0.0.1:8765:8765`,
  `127.0.0.1:7700:7700` and `127.0.0.1:8484:8484`. `peek`, `grist` and `grist-provisioner` use
  `network_mode: "service:privacyfence"`.
  - Every app reaches the others at `http://localhost:<port>`. That is also what the browser uses, and
    the only `http://` form PrivacyFence accepts.
  - There are no fixed addresses and no `pf` network.
  - Browsers send cookies by host, not by port, so PrivacyFence's session cookie is present for the
    `/oidc/authorize` redirect. The apps' cookie names do not collide.
  - If PrivacyFence's container restarts, the other three lose their network until
    `docker compose up -d` recreates them. `docs/operations.md` says so.
- **privacyfence.** It has no identity provider variables, so it runs in single-user mode at
  `http://localhost:8765`. On top of the sign-in wiring it sets:
  - `PRIVACYFENCE_PEEK_BASE_URL: http://localhost:7700`
  - `PRIVACYFENCE_GRIST_SERVER_URL: http://localhost:8484`
  - `PRIVACYFENCE_GRIST_PROVISIONER_URL: http://localhost:8485`
  - the two key files and both `…_AUTO_PROVISION: "true"`.

  The one person is `admin@privacyfence.localhost`.
- **peek.** On top of the sign-in wiring it sets `PEEK_BASE_URL: http://localhost:7700` and
  `PEEK_PROVISIONING_KEY_FILE`.
  - There are no admin emails and no sign-up. `/setup` is skipped because sign-in and the key file
    come from the environment.
  - PrivacyFence's provisioned account for `admin@privacyfence.localhost` is adopted at the first SSO sign-in.
  - Nobody is a Peek admin, and nobody can become one; the README says so in one line.
- **grist.** On top of the sign-in wiring it sets:
  - `APP_HOME_URL: http://localhost:8484`
  - `GRIST_ADMIN_EMAIL: grist-admin@privacyfence.localhost`
  - `GRIST_SINGLE_ORG: team`
  - `GRIST_IN_SERVICE: "true"`
  - `GRIST_ORG_CREATION_ANYONE: "false"`
  - `GRIST_PERSONAL_ORGS: "false"`
  - `GRIST_FORCE_LOGIN: "true"`
- **grist-provisioner.** It sets:
  - `GRIST_ADMIN_EMAIL: grist-admin@privacyfence.localhost`
  - `PROVISIONER_GRIST_URL: http://localhost:8484`
  - `PROVISIONER_GRIST_TEAM_SITE: team`
  - `PROVISIONER_ALLOWED_DOMAINS: privacyfence.localhost`
  - the key and boot-key files.
- **Exposure.** Everything is published on `127.0.0.1` only. The README repeats PrivacyFence's
  warning that anyone who can run `docker` on the computer controls the install.

### `scripts/check_configs.py`

It reads `configs/*/` using the standard library and PyYAML.

- **Output.** When every check passes it prints `ok: <n> configurations` and exits 0. Otherwise it
  prints one line per problem, `<config>: <message>`, and exits 1.
- **The proxy.** It is the service named `caddy` or `nginx`. A configuration with neither has no
  proxy.

| # | Check | Message |
|---|---|---|
| 1 | `compose.yaml`, `.env.example` and `init.sh` exist | `missing <file>` |
| 1b | `init.sh` is byte-identical to `common/init.sh` | `init.sh differs from common/init.sh` |
| 2 | services include `init`, `privacyfence`, `peek`, `grist`, `grist-provisioner` | `missing service <name>` |
| 3 | every `image:` matches `^[^$]+:\$\{[A-Z0-9_]+_IMAGE_TAG:\?pin a version in \.env\}$` | `<service> image must use ${<NAME>_IMAGE_TAG:?pin a version in .env}` |
| 4 | in `.env.example`, every `*_IMAGE_TAG=` value is non-empty and not `latest` | `<VAR> must pin a version` |
| 5 | every variable referenced as `${VAR` in `compose.yaml` and `templates/*.template`, or as `{$VAR}` in `Caddyfile`, is assigned in `.env.example`, except those with a `:-` default and those preceded by `$$` | `<VAR> is used but not in .env.example` |
| 5b | every `${VAR}` in `templates/*.template` and every `{$VAR}` in `Caddyfile` is a key of the proxy service's `environment:` | `<VAR> is used by the proxy config but not in its environment` |
| 6 | every service except `init` has `depends_on.init.condition == service_completed_successfully` | `<service> must depend on init with service_completed_successfully` |
| 6b | the proxy's `depends_on` keys are exactly `{init}` | `the proxy must depend only on init` |
| 7 | `privacyfence`, `peek`, `grist-provisioner`: `read_only: true`, `cap_drop: [ALL]`, `security_opt` contains `no-new-privileges:true` | `<service> must be read_only with cap_drop ALL and no-new-privileges` |
| 8 | the `image` of `privacyfence`, `peek`, `grist` and `grist-provisioner` is the same string in every configuration | `<service> image differs from configs/<first>` |
| 9 | with a proxy: `PRIVACYFENCE_TRUSTED_PROXIES` equals the proxy's `ipv4_address` | `PRIVACYFENCE_TRUSTED_PROXIES must equal the proxy address` |
| 9b | with a proxy: its `aliases` contain the three `${…_HOSTNAME:?` references | `proxy aliases must list the three hostnames` |
| 10 | every `environment:` is a mapping; no key matching `(?i)(secret\|password\|_key)$` | `<service>.environment must be a mapping` / `<service>.<key> must come from a file` |
| 11 | the secret volumes belong to `pf-secrets`: `privacyfence`, `peek-secrets`: `peek`, `grist-secrets`: `grist`, `provisioner-secrets`: `grist-provisioner` (a constant in the script); a service other than `init` mounts no secret volume but its own, and the proxy mounts none | `<service> mounts <volume>` |
| 12 | in `templates/*.template`, no `proxy_set_header` appears inside a `location` block (nginx inheritance) | `proxy_set_header inside a location in <file>:<line>` |

### CI

`ci.yml` runs on push and pull request, on `ubuntu-latest`, with `permissions: contents: read`, and
every action pinned by full SHA. These jobs block:

- **`check`:** `pip install -r requirements-dev.txt`, `pytest tests -q`,
  `python3 scripts/check_configs.py`, `ruff check .`.
- **`compose`:** for each `configs/*/`:
  - `cp .env.example .env`;
  - for each placeholder in the table below, `sed -i "s|^KEY=.*|KEY=value|" .env`;
  - `docker compose config -q`.
- **`shellcheck`:** `shellcheck -s sh common/init.sh`.
- **`grist-image`** (added in p2), for the `GRIST_IMAGE_TAG` in `configs/localhost/.env.example`:
  - `docker image inspect` gives the `Entrypoint` and `Cmd` arrays, and they must equal
    `["./sandbox/docker_entrypoint.sh"]` and `["./sandbox/run.sh"]`, the values the wrapper in every
    `compose.yaml` uses;
  - `WorkingDir` must be `/grist`;
  - `docker run --rm --entrypoint id ghcr.io/privacyfence/grist-core:<tag> -u grist` must print `1001`;
  - the image's `Env` contains `GRIST_EXT_FULL_EDITION_BASE_URL=` (empty), so the full-edition switch
    is off.
- **`caddy`** (added in p3): for each Caddy configuration,
  `docker run --rm -v ./configs/<c>/Caddyfile:/etc/caddy/Caddyfile:ro -e PF_HOSTNAME=pf.example.com -e PEEK_HOSTNAME=peek.example.com -e GRIST_HOSTNAME=grist.example.com caddy:<tag> caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`.
- **`nginx`** (added in p4):
  1. Make a self-signed certificate for the three placeholder names with `openssl req -x509` into a
     temp `certs/`.
  2. `docker run --rm` the nginx image with the template and the certificate mounted and the same
     three `-e` values, and the command
     `sh -c '/docker-entrypoint.d/20-envsubst-on-templates.sh && nginx -t'`.
  3. `grep -q 'server_name pf.example.com' /etc/nginx/conf.d/default.conf` inside the same run.

**CI placeholders:**

- `PF_HOSTNAME=pf.example.com`, `PEEK_HOSTNAME=peek.example.com`, `GRIST_HOSTNAME=grist.example.com`
- `ADMIN_EMAILS=admin@example.com`, `ALLOWED_DOMAIN=example.com`,
  `GRIST_ADMIN_EMAIL=grist-admin@example.com`
- `IDP_ISSUER=https://idp.example.com`, `IDP_CLIENT_ID=ci`

**`e2e-localhost.yml`** runs on push, pull request and `workflow_dispatch`, with a 20-minute timeout.
Steps, in this order:

1. `cd configs/localhost && cp .env.example .env && docker compose up -d --wait --wait-timeout 300 privacyfence peek grist grist-provisioner`.
   Naming the services keeps the one-shot `init` out of `--wait`; Compose still starts it first,
   because every other service depends on it.
2. `curl -fsS http://127.0.0.1:7700/healthz` and `curl -fsS http://127.0.0.1:8484/status` succeed.
   `curl -fsS http://127.0.0.1:8765/oidc/.well-known/openid-configuration` returns JSON whose
   `issuer` is `http://localhost:8765/oidc`.
3. **Sign in to PrivacyFence.** `python3 tests/e2e/oidc_signin.py pf` uses a cookie jar saved to
   `$RUNNER_TEMP/cookies.txt` (`http.cookiejar.MozillaCookieJar`):
   1. It reads the code from `docker compose logs privacyfence` with
      `Setup code: ([0-9A-F]{4}-[0-9A-F]{4})`.
   2. `GET http://localhost:8765/login` gives the `pf_setup_binding` cookie and the hidden `binding`
      and `next` fields, parsed with `html.parser`.
   3. `POST /login/setup` with `code`, `binding` and `next`, and no `Origin` header.
   4. It expects a 303 to `/security…` and a `pf_org_session` cookie in the jar.

   This sign-in also queues provisioning again, which a start-time attempt may have missed.
4. Poll for up to 180 s, every 5 s, until both of these succeed:
   - `docker compose exec -T privacyfence test -s /var/lib/privacyfence-org/.privacyfence/users/single-user/credentials/peek_token.json`
   - the same for `grist_token.json`.
5. `docker compose exec -T grist-provisioner grist-provisioner check` prints a line matching
   `^ok: [0-9]+ Grist users, 1 linked$`.
6. **The OIDC sign-ins.** `python3 tests/e2e/oidc_signin.py apps` uses the same jar:
   - **Grist:** open `http://localhost:8484/login?next=/` and follow redirects through
     `/oidc/authorize` back to Grist. Then assert that `GET http://localhost:8484/api/profile/user`
     returns 200 with `email == "admin@privacyfence.localhost"`.
   - **Peek:** open `http://localhost:7700/oauth/oidc/start` and follow redirects. Assert that the
     final status is 200 and the final URL path is not `/login`. Then `GET /dashboard` answers 200.
7. `docker compose logs peek` contains `first-run setup is skipped`. Peek prints that line to
   stdout only while its database has no accounts, so this check runs against the first start's
   log and is not repeated after step 9.
8. **No secret in the logs.** For each file in the four secret volumes, read it with
   `docker compose run --rm --no-deps -T --entrypoint cat init /out/<volume>/<name>`, into a shell
   variable that is never echoed. Each value is first registered with `echo "::add-mask::$value"`,
   so a later mistake cannot print it either.
   Fail with `secret <name> appears in the logs` if `docker compose logs --no-color` contains it.
9. `docker compose down`, then the same `up` as step 1. Then:
   - the `init` log has no `init: generated` line;
   - step 5 still passes.
10. On failure it prints `docker compose ps` and `docker compose logs --no-color`. The logs carry no
    secret except the single-user setup code, which is per-run.

`tests/e2e/oidc_signin.py` exits non-zero with a one-line reason on any failed assertion, and never
prints a cookie, code or secret. If `http.cookiejar` refuses a cookie PrivacyFence sets (for example a
`Domain=localhost` attribute), it prints `cookie refused: <name>` and exits 1.

## Manual steps

The steps are in the [step-by-step page](https://claude.ai/artifact/S4o9VWjyncbxGMNUREgaq1), whose
source is `docs/privacyfence-suite-plan-manual-steps.html`.

- **Before:**
  - `mb2-upstream-releases`: Peek 0.18.0, grist-provisioner 0.2.0 and grist-core 1.7.22-pf.2 are
    released. What is left is to merge [privacyfence/privacyfence#1051](https://github.com/privacyfence/privacyfence/pull/1051),
    release PrivacyFence 7.0.0b1, and check that all four images pull anonymously. The repository
    and its access, formerly `mb1`, are done.
- **After:**
  - `ma1-localhost`: run the localhost stack on your own computer.
  - `ma2-caddy-google`: deploy `caddy-google` on a server.
  - `ma3-caddy-idp`: deploy `caddy-idp` with your own identity provider, if you have one.
  - `ma4-nginx-google`: start `nginx-google` with a real certificate.

## Risks and open questions

- **Grist's entrypoint, working directory or uid differs from the research.** The `grist-image` CI
  job fails. The worker stops with `status=blocked` and reports what `docker image inspect` shows.
- **Grist starts before PrivacyFence answers through the proxy,** for example while Caddy obtains its
  first certificate. The wrapper waits up to 300 s. If `ma2` still shows Grist restarting, the fix is
  a longer wait, recorded in `docs/operations.md`.
- **Grist labels OIDC a full-edition feature.** The fork's lock-out check stops a gating release
  before it reaches `ghcr.io/privacyfence/grist-core`. The suite only moves to a new fork release
  through a PR that bumps `GRIST_IMAGE_TAG`, so CI here runs against it too.
- **Peek or Grist rejects PrivacyFence's ID token or userinfo** (a claim, an algorithm, the issuer
  string). e2e step 6 catches it on localhost. The worker stops with `status=blocked` and reports the
  app's log line; the fix belongs in privacyfence's OIDC provider.
- **The scripted single-user sign-in depends on the login form.** The script reads the field names
  from the page. If the flow cannot be followed without JavaScript, the worker stops with
  `status=blocked`, and steps 3 and 6 move to `manual_after` `ma1-localhost`.
- **An upstream release is missing a feature.** p2 checks each pinned tag (below). If one is
  missing, it stops with `status=blocked`. In particular, if `v7.0.0b1`'s
  `src/privacyfence/web/single_user_auth.py` still says `admin@localhost`, privacyfence/privacyfence#1051 did not make it
  into b1, and Grist provisioning on localhost cannot work.
- **Your own IdP sends no `email_verified`.** Peek and Grist refuse the sign-in. `ma3-caddy-idp`
  shows it; the fix is `IDP_TRUST_UNVERIFIED_EMAIL=true` for addresses in `ALLOWED_DOMAIN`, which the
  README already explains.
- **Compose versions.** `env_file` with `required: false` needs Compose 2.24, and `--wait-timeout`
  needs 2.20. The README states Docker Engine 24+ and Compose 2.24+.

## Appendix A: `.claude/toolkit.yaml`

```yaml
project:
  name: PrivacyFence suite
docs:
  must_read:
    - README.md
  plan_dir: docs
  changelog:
    file: CHANGELOG.md
    section: "## [Unreleased]"
git:
  main_branch: main
  branch_pattern: "<type>/<kebab-case>"
  branch_types: [feature, fix, chore, docs]
  merge_style: merge-commit
verify:
  fast:
    - python3 -m pip install -q -r requirements-dev.txt
    - python3 -m pytest tests -q
    - python3 scripts/check_configs.py
  dod:
    - python3 -m pip install -q -r requirements-dev.txt
    - python3 -m pytest tests -q
    - python3 scripts/check_configs.py
    - ruff check .
  dod_manual:
    - "A change to a configuration's compose.yaml, proxy config or .env.example needs the ci.yml run on the pushed branch to be green (docker compose config, caddy validate, nginx -t, shellcheck)."
    - "A change that can affect the localhost stack needs the e2e-localhost.yml run on the pushed branch to be green."
ci:
  dispatchable:
    - workflow: ci.yml
      use_when: "docker compose config for every configuration, caddy validate, nginx -t and shellcheck (the cloud session has no Docker)"
      notes: "Runs by itself on every push and pull request; read that run."
    - workflow: e2e-localhost.yml
      use_when: "The localhost stack started for real: every container healthy and PrivacyFence connected to Peek and Grist"
      notes: "Runs by itself on every push and pull request; workflow_dispatch works once it is on main."
stacks:
  - python
models:
  planner: opus
  orchestrator: sonnet
  worker: sonnet
  reviewer: opus
```

## Implementation manifest

```yaml
plan_slug: privacyfence-suite
feature_branch: feature/privacyfence-suite
max_parallel: 1
manual_steps_artifact: https://claude.ai/artifact/S4o9VWjyncbxGMNUREgaq1
manual_steps_source: docs/privacyfence-suite-plan-manual-steps.html
manual_before:
  - id: mb2-upstream-releases
    title: Merge privacyfence/privacyfence#1051 and release PrivacyFence 7.0.0b1; check that all four pinned images are public
    why: p2 to p4 pin privacyfence-org 7.0.0b1, peek 0.18.0, grist-core 1.7.22-pf.2 and grist-provisioner 0.2.0 in .env.example, and e2e-localhost.yml pulls them; without b1 (and #1051 in it) every container check fails, and Grist provisioning of the single-user person fails
    done_when: The tag v7.0.0b1 exists on privacyfence/privacyfence and its src/privacyfence/web/single_user_auth.py has email="admin@privacyfence.localhost"; and docker pull of ghcr.io/privacyfence/privacyfence-org:7.0.0b1, ghcr.io/privacyfence/peek:0.18.0, ghcr.io/privacyfence/grist-core:1.7.22-pf.2 and ghcr.io/privacyfence/grist-provisioner:0.2.0 each works without signing in
manual_after:
  - id: ma1-localhost
    title: Run configs/localhost on your own computer and use all three apps
    why: The e2e scripts the sign-in; only a person can check the passkey, the Sign in with SSO buttons in a real browser, and an AI client using the connected Peek and Grist
  - id: ma2-caddy-google
    title: Deploy configs/caddy-google on a server with real DNS
    why: CI cannot get public certificates, use Google sign-in or the PrivacyFence relay, or exercise the OIDC flow through a proxy
  - id: ma3-caddy-idp
    title: Deploy configs/caddy-idp with your own identity provider (skip if you have none)
    why: Checks PrivacyFence against a real identity provider and that the identity reaches Peek and Grist
  - id: ma4-nginx-google
    title: Start configs/nginx-google with a real certificate
    why: Checks websockets (Grist), server-sent events (Peek) and MCP streaming (PrivacyFence) through nginx
verify_after_merge:
  - python3 -m pip install -q -r requirements-dev.txt && python3 -m pytest tests -q && python3 scripts/check_configs.py
final_checks:
  - docs/privacyfence-suite-plan.md and docs/privacyfence-suite-plan-manual-steps.html are deleted and nothing links to them
  - CHANGELOG.md has entries under "## [Unreleased]" and no version heading
  - the ci.yml and e2e-localhost.yml runs on the feature branch's head are green
phases:
  - id: p1-skeleton
    title: Consistency checker, init script, base CI and repository basics
    depends_on: []
    complexity: M
    touches:
      - .gitignore
      - requirements-dev.txt
      - pyproject.toml
      - common/init.sh
      - scripts/check_configs.py
      - tests/test_check_configs.py
      - tests/fixtures/**
      - .github/workflows/ci.yml
      - CHANGELOG.md
    brief: |
      Read docs/privacyfence-suite-plan.md: "Repository layout", "Secrets", "scripts/check_configs.py" and "CI". There are no configs/ folders yet; later phases add them.
      1. .gitignore exactly as in the Design. requirements-dev.txt with the three pins. pyproject.toml with only [tool.ruff] (line-length = 120, target-version = "py312") and [tool.pytest.ini_options] testpaths = ["tests"].
      2. common/init.sh exactly as "Secrets" specifies: the four /out directories, the canonical root-only copies, the six values with prefixes and their per-volume owners, the temp-chown-chmod-mv order, the idp_client_secret copy, and the log lines. POSIX sh only (busybox ash): no bash arrays, no [[ ]], no `local`.
      3. scripts/check_configs.py with every check and message in the table, a `main(root: Path) -> int`, and `if __name__ == "__main__": sys.exit(main(Path(__file__).resolve().parent.parent))`. With no configs/ folders it prints "ok: 0 configurations" and exits 0.
      4. tests/test_check_configs.py, with two fixture trees:
         - tests/fixtures/good/: common/init.sh, and configs/a/ with no proxy (the five services, .env.example, init.sh);
         - tests/fixtures/proxy/: the same plus a caddy service with the fixed address and aliases, and a Caddyfile.

         One test per check (test_check_<number>, for example test_check_6b; test_check_12 writes a templates/default.conf.template into the copied proxy tree, with a proxy_set_header inside a location and no ${…} reference, so checks 5 and 5b stay quiet) copies the right tree to tmp_path, breaks one thing, and asserts the exact message and exit code 1. test_good_tree_ok and test_proxy_tree_ok check that both pass.
      5. .github/workflows/ci.yml with the jobs check, compose and shellcheck. The compose job iterates over configs/*/ and is green with none. Pin every action by full commit SHA with a version comment, copying actions/checkout and actions/setup-python from privacyfence/grist-provisioner's .github/workflows/real-grist.yml.
      6. CHANGELOG.md with "# Changelog" and an empty "## [Unreleased]".
      7. Run `python3 -m pytest tests -q`, `python3 scripts/check_configs.py` and `ruff check .`. Push and read the ci.yml run on the branch (it runs by itself); it must be green.
    acceptance:
      - python3 -m pytest tests -q passes, including a test_check_<n> for every row of the checks table
      - python3 scripts/check_configs.py prints "ok: 0 configurations"
      - shellcheck is green in the ci.yml run on the pushed branch, and the whole run is green

  - id: p2-localhost
    title: The localhost configuration, the Grist image check and the end-to-end workflow
    depends_on: [p1-skeleton]
    complexity: M
    touches:
      - configs/localhost/**
      - .github/workflows/ci.yml
      - .github/workflows/e2e-localhost.yml
      - tests/e2e/oidc_signin.py
    brief: |
      Read docs/privacyfence-suite-plan.md: "Services and addresses", "Secrets", "Grist's secrets from files, and waiting for PrivacyFence", "Sign-in wiring", "Admins", "localhost", "CI" and "Risks".
      1. Versions are fixed: PRIVACYFENCE_IMAGE_TAG=7.0.0b1, PEEK_IMAGE_TAG=0.18.0, GRIST_IMAGE_TAG=1.7.22-pf.2, GRIST_PROVISIONER_IMAGE_TAG=0.2.0, ALPINE_IMAGE_TAG=3.22. Do not use get_latest_release: it skips pre-releases, and 7.0.0b1 is one. Check each with the GitHub MCP tools:
         - privacyfence/privacyfence: get_file_contents at ref v7.0.0b1 of CHANGELOG.md contains PRIVACYFENCE_PEEK_AUTO_PROVISION and PRIVACYFENCE_OIDC_CLIENTS, and of src/privacyfence/web/single_user_auth.py contains email="admin@privacyfence.localhost";
         - privacyfence/peek: get_release_by_tag v0.18.0 exists, and CHANGELOG.md at v0.18.0 contains PEEK_OIDC_ISSUER_URL, PEEK_OIDC_SIGNUP, PEEK_ADMIN_EMAILS and PEEK_PROVISIONING_KEY_FILE;
         - privacyfence/grist-provisioner: get_release_by_tag v0.2.0 exists, and CHANGELOG.md at v0.2.0 contains PROVISIONER_KEY_FILE and PROVISIONER_GRIST_BOOT_KEY_FILE;
         - privacyfence/grist-core: get_release_by_tag v1.7.22-pf.2 exists.
         Stop condition: if any check fails, stop with status=blocked naming it.
      2. Add the grist-image job to ci.yml as designed: it compares the image's Entrypoint with ["./sandbox/docker_entrypoint.sh"], its Cmd with ["./sandbox/run.sh"] and its WorkingDir with /grist, and checks the uid and the empty GRIST_EXT_FULL_EDITION_BASE_URL. The wrapper in compose.yaml uses those values verbatim (Design, "Grist's secrets from files"). Stop condition: see Risks (Grist image).
      3. configs/localhost/compose.yaml: `name: privacyfence-localhost`, with the services as specified:
         - init with network_mode: none and the four secret volumes;
         - privacyfence owning the namespace and publishing the three 127.0.0.1 ports;
         - the other three with network_mode: "service:privacyfence";
         - the Grist wrapper verbatim, plus the health checks, depends_on and volumes. No caddy volumes and no pf network.

         Add a three-line header comment saying what the folder is and pointing to docs/configurations.md.
      4. configs/localhost/.env.example: the image tags, each with a one-line comment. configs/localhost/init.sh: copy common/init.sh byte for byte.
      5. tests/e2e/oidc_signin.py, with two subcommands, pf and apps, exactly as e2e steps 3 and 6 describe. Use only the standard library: urllib.request with HTTPCookieProcessor, http.cookiejar.MozillaCookieJar and html.parser.
      6. .github/workflows/e2e-localhost.yml with the steps exactly as listed, and pinned actions as in ci.yml.
      7. Run python3 scripts/check_configs.py; it must print "ok: 1 configurations". Push and read the ci.yml and e2e-localhost.yml runs. Each of these stop conditions means stopping with status=blocked and putting the relevant log lines in the report, never changing upstream behaviour from here:
         - grist-image fails;
         - e2e fails waiting for the token files (include the privacyfence and grist-provisioner provisioning lines);
         - e2e step 6 fails (include the grist, peek and privacyfence lines around the sign-in).
    acceptance:
      - python3 scripts/check_configs.py prints "ok: 1 configurations"
      - cmp common/init.sh configs/localhost/init.sh exits 0
      - the e2e-localhost.yml run on the pushed branch is green, including the scripted OIDC sign-ins and the secrets-in-logs check
      - the ci.yml run on the pushed branch is green, including grist-image

  - id: p3-caddy
    title: The caddy-idp and caddy-google configurations
    depends_on: [p2-localhost]
    complexity: M
    touches:
      - configs/caddy-idp/**
      - configs/caddy-google/**
      - .github/workflows/ci.yml
    brief: |
      Read docs/privacyfence-suite-plan.md: "Services and addresses", "Secrets", "Grist's secrets from files, and waiting for PrivacyFence", "Sign-in wiring", "Admins", "Per-app settings shared by the proxy configurations", "caddy-idp", "caddy-google and nginx-google" and "Caddyfile".
      1. Use the image tags from configs/localhost/.env.example so that check 8 passes, and the Grist wrapper from configs/localhost/compose.yaml. Add CADDY_IMAGE_TAG=2.10.2.
      2. configs/caddy-idp/compose.yaml (`name: privacyfence-caddy-idp`) and configs/caddy-google/compose.yaml (`name: privacyfence-caddy-google`): the five services plus caddy, with:
         - the fixed addresses, the pf network and the `:?` aliases;
         - the shared per-app settings and the configuration's own settings, verbatim;
         - the proxy depending only on init;
         - privacyfence keeping the optional `env_file: [{path: privacyfence.env, required: false}]`;
         - the `./secrets:/user-secrets:ro` mount on init in caddy-idp only.
      3. In each folder:
         - the Caddyfile verbatim;
         - init.sh copied from common/init.sh;
         - .env.example with every variable, each with a one-line comment. The host names and emails are empty; ALLOWED_DOMAIN says it takes exactly one domain; PEEK_ADMIN_EMAILS and GRIST_ADMIN_EMAIL get the meanings from "Admins".

         For caddy-idp also:
         - list PrivacyFence's three redirect URIs in a comment block;
         - add `# IDP_TRUST_UNVERIFIED_EMAIL=true` commented out, with the comment from the Design's "email_verified" paragraph;
         - add `secrets/.gitkeep`, and a two-line `secrets/README.md` naming idp_client_secret and the `install -m 0600 /dev/null secrets/idp_client_secret` command.

         For caddy-google, add a comment that nothing is registered and that the relay DNS records come from `privacyfence-app --relay-dns-records`.
      4. ci.yml: the caddy job as specified, and add the IDP placeholders to the compose job.
      5. Run python3 scripts/check_configs.py; it must print "ok: 3 configurations". Push and read ci.yml: compose and caddy must be green for both folders.
    acceptance:
      - python3 scripts/check_configs.py prints "ok: 3 configurations"
      - cmp common/init.sh configs/caddy-idp/init.sh and cmp common/init.sh configs/caddy-google/init.sh exit 0
      - grep -n "remote_ip 172.30.87.10" configs/caddy-idp/Caddyfile configs/caddy-google/Caddyfile finds both
      - git ls-files configs/caddy-idp/secrets lists .gitkeep and README.md
      - the ci.yml run on the pushed branch is green

  - id: p4-nginx
    title: The nginx-google configuration
    depends_on: [p3-caddy]
    complexity: S
    touches:
      - configs/nginx-google/**
      - .github/workflows/ci.yml
    brief: |
      Read docs/privacyfence-suite-plan.md: "nginx (nginx-google)" and "caddy-google and nginx-google".
      1. Copy configs/caddy-google/compose.yaml to configs/nginx-google/compose.yaml and rename the project to privacyfence-nginx-google. Replace the caddy service with an nginx service:
         - image `nginx:${NGINX_IMAGE_TAG:?pin a version in .env}`;
         - the same fixed address 172.30.87.2 and aliases;
         - the three hostname variables in environment:;
         - the two mounts and ports 80 and 443;
         - depends only on init; no caddy volumes.

         .env.example: copy caddy-google's, replace CADDY_IMAGE_TAG with NGINX_IMAGE_TAG=1.28.0.
      2. configs/nginx-google/templates/default.conf.template: the map, the port-80 server and the three server blocks written out in full, as the Design specifies, with the fixed-address upstreams.
      3. configs/nginx-google/certs/README.md: the two file names, that they must cover all three names, and that the key must be readable by the nginx container. Copy init.sh from common/init.sh. No secrets/ folder.
      4. ci.yml: the nginx job as specified, including the server_name grep.
      5. Run python3 scripts/check_configs.py; it must print "ok: 4 configurations". Push and read ci.yml: the nginx job must be green.
    acceptance:
      - python3 scripts/check_configs.py prints "ok: 4 configurations"
      - grep -n "allow 172.30.87.10" configs/nginx-google/templates/default.conf.template finds the line
      - grep -c "proxy_pass http://172.30.87." configs/nginx-google/templates/default.conf.template prints 4
      - grep -c "proxy_set_header Upgrade" configs/nginx-google/templates/default.conf.template prints 1
      - the ci.yml run on the pushed branch is green

  - id: p5-docs-retire
    title: README, configuration and operations docs, changelog, delete the plan
    depends_on: [p4-nginx]
    complexity: M
    touches:
      - README.md
      - docs/configurations.md
      - docs/operations.md
      - CHANGELOG.md
      - docs/privacyfence-suite-plan.md
      - docs/privacyfence-suite-plan-manual-steps.html
    brief: |
      1. README.md:
         - what the suite is, and the table of the four configurations from the Goal;
         - prerequisites: Docker Engine 24+ and Compose 2.24+; DNS and ports 80/443 for the proxy configurations;
         - a quick start per configuration: copy the folder, `cp .env.example .env`, edit it, write the secret file (caddy-idp only), then `docker compose up -d`, then the first sign-in. For localhost, the setup code is in `docker compose logs privacyfence`;
         - a section "What is already connected", saying that:
           - Peek and Grist sign people in through PrivacyFence (Sign in with SSO), so whatever PrivacyFence uses upstream applies to all three;
           - each person who signs in to PrivacyFence gets their Peek account and Grist key connected;
           - Grist users are created and added to the team site;
           - signing out of Peek or Grist leaves the PrivacyFence session;
         - sign-in notes: caddy-google and nginx-google admit only verified Google Workspace accounts (no personal Gmail) and need outbound HTTPS to oauth.privacyfence.eu; ALLOWED_DOMAIN limits who signs in to all three apps, and PrivacyFence takes it only at its first start (later changes go through its Admin page); with caddy-idp, an IdP that sends no email_verified (for example Entra ID) needs IDP_TRUST_UNVERIFIED_EMAIL=true, which trusts addresses in ALLOWED_DOMAIN;
         - a section "Admins", from the Design's "Admins": PEEK_ADMIN_EMAILS and GRIST_ADMIN_EMAIL are dedicated addresses that are not auto-connected, localhost has no Peek admin, and Grist on localhost is administered by the boot key only;
         - that Grist comes from PrivacyFence's grist-core fork (open-source build, full-edition switch off, lock-out check on every release), with a link to the fork's pf/README.md; the rootless-Docker note for secrets/idp_client_secret;
         - links to PrivacyFence's docs/org-mode-docker.md, docs/org-mode-setup-guide.md (built-in Google sign-in, relay DNS records) and docs/oidc-provider.md, to Peek's auth docs, and to grist-provisioner's README.
      2. docs/configurations.md: one table per configuration listing every .env variable, its meaning and where it ends up (which container variable), plus a table of the generated values with the volumes and owners of their copies.
      3. docs/operations.md:
         - Upgrade: change the tags, then `docker compose pull && docker compose up -d`.
         - Backup: stop, then archive each volume with a `docker run --rm -v <volume>:/v alpine tar` command, then start.
         - Rotating a generated value: remove its canonical copy with `docker compose run --rm --no-deps init rm /out/pf/.<name>`, then `docker compose up -d --force-recreate`.
         - Rotating the IdP secret: replace secrets/idp_client_secret, then `docker compose up -d` and `docker compose restart privacyfence`. PrivacyFence and Grist read every secret once at start, so a rotation always ends with a restart or recreate.
         - Removing a person: PrivacyFence's `--peek-release` and `--grist-release` through `docker compose exec`.
         - Troubleshooting: the init log lines; where each app logs provisioning; on localhost, a PrivacyFence restart needs `docker compose up -d` to bring the other three back; Grist restarting while waiting for PrivacyFence.
      4. CHANGELOG.md under "## [Unreleased]", "### Added": "- The four configurations: caddy-idp, caddy-google, nginx-google and localhost, with generated provisioning keys and OIDC client secrets, Peek and Grist signing in through PrivacyFence, and connected at sign-in."
      5. Delete docs/privacyfence-suite-plan.md and docs/privacyfence-suite-plan-manual-steps.html; `grep -rn --exclude-dir=.git "privacyfence-suite-plan" .` must find nothing.
    acceptance:
      - test ! -e docs/privacyfence-suite-plan.md && test ! -e docs/privacyfence-suite-plan-manual-steps.html
      - grep -rn --exclude-dir=.git "privacyfence-suite-plan" . finds nothing
      - grep -n "What is already connected" README.md finds the section
      - grep -n "^## Admins" README.md finds the section
```
