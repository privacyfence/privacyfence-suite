# Configurations

One table per configuration lists every `.env` variable, what it means and where it ends up. No secret is ever in `.env` or `compose.yaml`; the generated values are listed [at the end](#generated-values).

All proxy configurations share these variables. In the tables, "ends up in" names the container variable that Compose sets from it.

## Shared by `caddy-idp`, `caddy-google` and `nginx-google`

| Variable | Meaning | Ends up in |
|---|---|---|
| `PRIVACYFENCE_IMAGE_TAG` | PrivacyFence image tag. `latest` on purpose (needs 7.0.0 or later); set an exact version such as `7.0.0` to hold back an update | `image` of `privacyfence` |
| `PEEK_IMAGE_TAG` | Peek image tag (pinned) | `image` of `peek` |
| `GRIST_IMAGE_TAG` | Grist image tag, from PrivacyFence's grist-core fork (pinned) | `image` of `grist` |
| `GRIST_PROVISIONER_IMAGE_TAG` | grist-provisioner image tag (pinned) | `image` of `grist-provisioner` |
| `ALPINE_IMAGE_TAG` | Alpine tag for the one-shot `init` service | `image` of `init` |
| `PF_HOSTNAME` | Public host name of PrivacyFence; DNS must point at the server | `privacyfence`: `PRIVACYFENCE_ISSUER_URL` (`https://<name>`); `peek`: `PEEK_OIDC_ISSUER_URL` and `grist`: `GRIST_OIDC_IDP_ISSUER` (both `https://<name>/oidc`); `caddy`: `PF_HOSTNAME`, a network alias and the Caddyfile site; `nginx-google`: an `extra_hosts` entry on `privacyfence`, `peek` and `grist` |
| `PEEK_HOSTNAME` | Public host name of Peek | `privacyfence`: `PRIVACYFENCE_PEEK_BASE_URL` and `PRIVACYFENCE_OIDC_CLIENT_PEEK_REDIRECT_URIS` (`https://<name>/oauth/oidc/callback`); `peek`: `PEEK_BASE_URL`; `caddy` / `extra_hosts` as above |
| `GRIST_HOSTNAME` | Public host name of Grist; PrivacyFence reaches the provisioner through the same name | `privacyfence`: `PRIVACYFENCE_GRIST_SERVER_URL`, `PRIVACYFENCE_GRIST_PROVISIONER_URL` and `PRIVACYFENCE_OIDC_CLIENT_GRIST_REDIRECT_URIS` (`https://<name>/oauth2/callback`); `grist`: `APP_HOME_URL`; `caddy` / `extra_hosts` as above |
| `ADMIN_EMAILS` | PrivacyFence admins, comma-separated, each in `ALLOWED_DOMAIN` | `privacyfence`: `PRIVACYFENCE_ADMIN_EMAILS` |
| `ALLOWED_DOMAIN` | The one domain whose people may sign in to all three apps. PrivacyFence reads it only at its first start (later changes go through its Admin page) | `privacyfence`: `PRIVACYFENCE_ALLOWED_DOMAINS`; `peek`: `PEEK_ALLOWED_EMAIL_DOMAIN`; `grist-provisioner`: `PROVISIONER_ALLOWED_DOMAINS` |
| `GRIST_ADMIN_EMAIL` | Grist install admin: a real address that can sign in to PrivacyFence (a dedicated address is recommended). Its automatic Grist key is refused | `grist` and `grist-provisioner`: `GRIST_ADMIN_EMAIL` |
| `PEEK_ADMIN_EMAILS` | Optional. Peek admins, comma-separated, each in `ALLOWED_DOMAIN`. They connect Peek by hand on `/connect` | `peek`: `PEEK_ADMIN_EMAILS` |
| `GRIST_TEAM_SITE` | Optional, default `team`. Grist's single organization (team site) | `grist`: `GRIST_SINGLE_ORG`; `grist-provisioner`: `PROVISIONER_GRIST_TEAM_SITE` |

Not variables in `.env`, but the same in all three: `PRIVACYFENCE_PEEK_AUTO_PROVISION` and `PRIVACYFENCE_GRIST_AUTO_PROVISION` are `"true"`; `PRIVACYFENCE_OIDC_CLIENTS` is `peek,grist`; the OIDC client IDs are `peek` and `grist`; `PEEK_OIDC_SIGNUP` is `"true"`; Grist runs with `GRIST_IN_SERVICE`, `GRIST_FORCE_LOGIN`, and with `GRIST_ORG_CREATION_ANYONE` and `GRIST_PERSONAL_ORGS` off. An optional `privacyfence.env` file next to `compose.yaml` is read by PrivacyFence for extra settings (for example an Entra group claim).

## `caddy-idp`

Everything in the shared table, plus:

| Variable | Meaning | Ends up in |
|---|---|---|
| `CADDY_IMAGE_TAG` | Caddy image tag (pinned) | `image` of `caddy` |
| `IDP_ISSUER` | OIDC issuer URL of your identity provider | `PRIVACYFENCE_IDP_ISSUER` |
| `IDP_CLIENT_ID` | Client ID of the confidential client registered for PrivacyFence | `PRIVACYFENCE_IDP_CLIENT_ID` |
| `IDP_TRUST_UNVERIFIED_EMAIL` | Optional, default `false`. Set `true` if the identity provider sends no `email_verified` claim (Microsoft Entra ID): PrivacyFence then treats addresses in `ALLOWED_DOMAIN` as verified | `PRIVACYFENCE_IDP_TRUST_UNVERIFIED_EMAIL` |
| `secrets/idp_client_secret` (a file, not a variable) | The client secret | installed by `init` as `/run/suite/idp_client_secret`, read through `PRIVACYFENCE_IDP_CLIENT_SECRET_FILE` |

Register one confidential client with the redirect URIs `https://<PF_HOSTNAME>/oauth/idp/callback`, `/oauth/idp/login-callback` and `/oauth/stepup/callback`.

## `caddy-google`

The shared table plus `CADDY_IMAGE_TAG` (as above). There is no secret file and no `secrets/` folder. `PRIVACYFENCE_IDP` is fixed to `builtin-google`; only verified Google Workspace accounts can sign in, and the container needs outbound HTTPS to `oauth.privacyfence.eu`. Publish the `_privacyfence-relay` DNS TXT records once (`docker compose exec privacyfence privacyfence-app --relay-dns-records`).

## `nginx-google`

The shared table, with no `CADDY_IMAGE_TAG` (there is no proxy container) and `PRIVACYFENCE_IDP: builtin-google` as in `caddy-google`.

The network facts:

| Fact | Value |
|---|---|
| Network | `pf`, driver `bridge`, subnet `172.30.87.0/24` |
| Bridge name | `pf-suite` (one firewall rule for it) |
| Gateway | `172.30.87.1`, which is where the host's nginx appears to the containers |
| Fixed addresses | `privacyfence` `.10` (8765), `peek` `.11` (7700), `grist` `.12` (8484), `grist-provisioner` `.13` (8485) |
| `extra_hosts` | on `privacyfence`, `peek` and `grist`: the three host names map to `172.30.87.1`, so calls to the public names reach the host's nginx over the bridge |
| Trusted proxy | `PRIVACYFENCE_TRUSTED_PROXIES: 172.30.87.1` and `PEEK_TRUSTED_PROXY_CIDRS: 172.30.87.1/32` |
| Published ports | none; the host's nginx connects to the fixed addresses |
| Provisioner access | the example nginx configuration answers `/api/provisioning/` with 404 unless the source is `172.30.87.10` (PrivacyFence) |

The Caddy configurations use the same subnet with Caddy at `172.30.87.2` (trusted proxy `172.30.87.2`) and the three host names as network aliases of the `caddy` service.

## `localhost`

`.env` holds only the image tags (`PRIVACYFENCE_IMAGE_TAG`, `PEEK_IMAGE_TAG`, `GRIST_IMAGE_TAG`, `GRIST_PROVISIONER_IMAGE_TAG`, `ALPINE_IMAGE_TAG`, meaning as above). Everything else is fixed in `compose.yaml`:

| Fact | Value |
|---|---|
| Network | `privacyfence` owns the network namespace; `peek`, `grist` and `grist-provisioner` use `network_mode: "service:privacyfence"` |
| Published | `127.0.0.1:8765` (PrivacyFence), `127.0.0.1:7700` (Peek), `127.0.0.1:8484` (Grist) |
| Mode | PrivacyFence single-user mode; the person is `admin@privacyfence.localhost` |
| Issuer | `http://localhost:8765/oidc` |
| Grist admin | `grist-admin@privacyfence.localhost` (nobody can sign in as it; the boot key administers Grist) |
| Peek admin | none |
| Team site | `team`; provisioner domain `privacyfence.localhost` |

## Peek page backends

Optional, in every configuration (and in `deploy/nginx-host-migration`), off by default. A [page backend](https://github.com/privacyfence/peek/blob/main/docs/operations.md#page-backends) is a Docker image that Peek runs as a container next to a page version; the page calls it with `peek.fetch`. Each configuration ships `compose.backends.yaml`, which Compose reads only when `.env` names it:

```sh
COMPOSE_FILE=compose.yaml:compose.backends.yaml
DOCKER_GID=999        # stat -c %g /var/run/docker.sock
```

Then `docker compose up -d`. If peekd cannot reach the engine it stops with `docker is not reachable at ...`, which almost always means `DOCKER_GID` is wrong. On Peek's **Admin** page, **Backends** tab, set the allowed backend images (a short registry prefix such as `ghcr.io/acme/`, or exact repositories); while it is empty no page can have a backend. The same tab sets memory, CPU, idle stop, the cap on running backends and registry credentials.

| Variable | Meaning | Ends up in |
|---|---|---|
| `COMPOSE_FILE` | `compose.yaml:compose.backends.yaml` turns page backends on; unset (the default) leaves them off | Compose itself |
| `DOCKER_GID` | Group id of the Docker socket on the host, so Peek (uid 65532) can use it. Required when backends are on. Usually `0` on Docker Desktop | `group_add` of `peek` |

What `compose.backends.yaml` changes:

- `peek` gets `PEEK_BACKENDS=docker`, `PEEK_DOCKER_HOST=unix:///var/run/docker.sock`, `PEEK_BACKEND_NETWORK=peek-backends`, the socket mounted and the socket's group. Its hardening (`read_only`, `cap_drop: ALL`, `no-new-privileges`) stays.
- A bridge network named `peek-backends`, where peekd starts the backend containers. In the proxy configurations `peek` joins it and keeps its `pf` address; backends are not on `pf`, so they cannot reach PrivacyFence, Grist or the provisioner on their internal addresses. They have outbound internet and reach PrivacyFence through its public host name.
- `localhost`: `peek` shares `privacyfence`'s network namespace, so the network is attached to `privacyfence`, and backends can reach the address where PrivacyFence, Peek and Grist listen. Because only a Peek admin can allow images, the file also makes `admin@privacyfence.localhost` the Peek admin; Peek does not provision an admin, so that person connects Peek once by hand on `/connect` with a Peek API token.

**The Docker socket is root on the host.** Anyone who controls Peek, or can make it start an image you allowed, controls the server. Keep the allowed images short, and prefer a dedicated VM, rootless Docker or a socket proxy (point `PEEK_DOCKER_HOST` at it and drop the socket mount in a `compose.override.yaml`). Backend data volumes (`peek-<instance>-data-u<id>`) live in the engine, outside `peek-data`; see [Backup](operations.md#backup). Turning backends off again: remove `COMPOSE_FILE` from `.env` and run `docker compose up -d`; peekd removes its backend containers when it stops, and the volumes stay.

## Generated values

`init` runs on every `docker compose up -d`. The first time it generates each value (`<prefix>` plus 43 base64url characters from `/dev/urandom`; it logs `init: generated <name>` and never the value). The root-only canonical copy is `/out/pf/.<name>` in the `pf-secrets` volume; on every run `init` installs a copy into each consumer's volume, mode `0400`.

| Value | Prefix | Copies: volume (owner) |
|---|---|---|
| `peek_provisioning_key` | `peekprov_` | `pf-secrets` (10001:10001), `peek-secrets` (65532:65532) |
| `grist_provisioning_key` | `gristprov_` | `pf-secrets` (10001:10001), `provisioner-secrets` (1001:1001) |
| `peek_oidc_client_secret` | none | `pf-secrets` (10001:10001), `peek-secrets` (65532:65532) |
| `grist_oidc_client_secret` | none | `pf-secrets` (10001:10001), `grist-secrets` (0:0) |
| `grist_boot_key` | none | `grist-secrets` (0:0), `provisioner-secrets` (1001:1001) |
| `grist_session_secret` | none | `grist-secrets` (0:0) |
| `idp_client_secret` (`caddy-idp` only, from `secrets/idp_client_secret`) | n/a | `pf-secrets` (10001:10001), refreshed on every run |

Each app mounts only its own volume, read-only at `/run/suite`; the proxy mounts none. The uids are those of the images: 10001 (PrivacyFence), 65532 (Peek), 1001 (Grist's `grist` user and the provisioner). Grist's files are root-owned because Grist's wrapper entrypoint reads them as root and exports them into its environment before dropping privileges. PrivacyFence and Grist read every secret once at start, so a rotation always ends with a restart or recreate ([operations](operations.md#rotating-a-generated-value)).

Volumes: `pf-data`, `peek-data`, `grist-data` (Grist's `/persist`, also mounted by the provisioner), `provisioner-data`, the four secret volumes `pf-secrets`, `peek-secrets`, `grist-secrets`, `provisioner-secrets`, and for Caddy `caddy-data` and `caddy-config`. Compose prefixes each volume with the project name (`privacyfence-<config>`).
