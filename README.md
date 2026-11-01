# privacyfence-suite

[PrivacyFence](https://github.com/privacyfence/privacyfence), [Peek](https://github.com/privacyfence/peek) and [Grist](https://github.com/privacyfence/grist-core) in one Docker stack, already connected. One `docker compose up -d` starts all three. Everybody who signs in to PrivacyFence finds Peek and Grist connected, and signs in to Peek and Grist **through PrivacyFence**. Nobody creates a provisioning key, registers Peek or Grist with an identity provider, or turns a switch on the Admin page.

The repository ships four configurations, each a self-contained folder:

| Configuration | Proxy | PrivacyFence signs people in with | Peek and Grist sign in with |
|---|---|---|---|
| `caddy-idp` | Caddy container (automatic HTTPS) | your organization's OIDC identity provider (one client registration, for PrivacyFence only) | PrivacyFence |
| `caddy-google` | Caddy container (automatic HTTPS) | PrivacyFence's built-in Google sign-in (nothing to register) | PrivacyFence |
| `nginx-google` | the nginx already running on your host, with your certificate (an example site configuration is included, no nginx container) | the same as `caddy-google` | PrivacyFence |
| `localhost` | none | single-user mode: setup code, then passkey | PrivacyFence |

Every variable is explained in [docs/configurations.md](https://github.com/privacyfence/privacyfence-suite/blob/main/docs/configurations.md). Upgrades, backups, rotating secrets and troubleshooting are in [docs/operations.md](https://github.com/privacyfence/privacyfence-suite/blob/main/docs/operations.md).

## Prerequisites

- Docker Engine 24 or later with Compose 2.24 or later.
- Proxy configurations (`caddy-idp`, `caddy-google`, `nginx-google`): three DNS names pointing at the server (one each for PrivacyFence, Peek and Grist), and ports 80 and 443 reachable from the internet.
- `nginx-google` only: nginx 1.25.1 or later already running on a Linux host with rootful Docker. Docker Desktop and rootless Docker do not route the stack's addresses to the host; use `caddy-google` there.
- `caddy-idp` only: an OIDC identity provider where you can register one confidential client.

## Install

Install one configuration with one command (no `git clone`). The installer downloads that configuration's archive, checks it against `SHA256SUMS`, unpacks it into `./privacyfence-<config>` and copies `.env.example` to `.env`.

```sh
# the newest release
curl -fsSL https://github.com/privacyfence/privacyfence-suite/releases/latest/download/install.sh | sh -s -- caddy-google

# a pinned release
curl -fsSL https://github.com/privacyfence/privacyfence-suite/releases/download/vX.Y.Z/install.sh | sh -s -- caddy-google

# localhost can start right away
curl -fsSL https://github.com/privacyfence/privacyfence-suite/releases/latest/download/install.sh | sh -s -- localhost --start
```

Options: `--dir DIR` (default `./privacyfence-<config>`), `--upgrade` (see [operations](https://github.com/privacyfence/privacyfence-suite/blob/main/docs/operations.md#upgrade)) and `--start` (runs `docker compose up -d` afterwards; only useful at once for `localhost`, because the other configurations need `.env` filled in first).

**Or download an archive** (`.zip` or `.tar.gz`) from the [releases page](https://github.com/privacyfence/privacyfence-suite/releases) and unpack it yourself:

```sh
curl -fsSLO https://github.com/privacyfence/privacyfence-suite/releases/latest/download/privacyfence-suite-caddy-google.zip
unzip privacyfence-suite-caddy-google.zip && cd privacyfence-caddy-google && cp .env.example .env
```

**The verified path.** Piping to `sh` is a convenience. To check what you run, download `install.sh` and `SHA256SUMS`, check them, then run the script:

```sh
base=https://github.com/privacyfence/privacyfence-suite/releases/latest/download
curl -fsSLO $base/install.sh && curl -fsSLO $base/SHA256SUMS
sha256sum -c --ignore-missing SHA256SUMS      # prints "install.sh: OK"
gh attestation verify install.sh --repo privacyfence/privacyfence-suite
sh install.sh caddy-google
```

The release assets carry GitHub build provenance, so `gh attestation verify <file> --repo privacyfence/privacyfence-suite` works for the archives too.

## Quick start

After installing, `cd privacyfence-<config>`.

### caddy-idp

1. Register **one** confidential OIDC client with your identity provider for PrivacyFence, with these redirect URIs:
   - `https://<PF_HOSTNAME>/oauth/idp/callback`
   - `https://<PF_HOSTNAME>/oauth/idp/login-callback`
   - `https://<PF_HOSTNAME>/oauth/stepup/callback`
2. Edit `.env`: the three host names, `ADMIN_EMAILS`, `ALLOWED_DOMAIN`, `GRIST_ADMIN_EMAIL`, `IDP_ISSUER` and `IDP_CLIENT_ID`. If your identity provider sends no `email_verified` claim (Microsoft Entra ID, for example), also set `IDP_TRUST_UNVERIFIED_EMAIL=true`; PrivacyFence then treats addresses in `ALLOWED_DOMAIN` as verified.
3. Write the client secret to `secrets/idp_client_secret`:
   ```sh
   install -m 0600 /dev/null secrets/idp_client_secret
   # then paste the secret into that file
   ```
   Under rootless Docker (or userns-remap) the `init` container's root may not be able to read a `0600` host file; make the file readable to the Docker user in that case.
4. `docker compose up -d`.
5. Open `https://<PF_HOSTNAME>` and sign in.

### caddy-google

1. Edit `.env`: the three host names, `ADMIN_EMAILS`, `ALLOWED_DOMAIN` and `GRIST_ADMIN_EMAIL`.
2. `docker compose up -d`.
3. Publish the `_privacyfence-relay` DNS TXT records once. They are printed by `docker compose exec privacyfence privacyfence-app --relay-dns-records`; see the [setup guide](https://github.com/privacyfence/privacyfence/blob/main/docs/org-mode-setup-guide.md).
4. Open `https://<PF_HOSTNAME>` and sign in with a Google Workspace account.

### nginx-google

1. Edit `.env` as for `caddy-google`.
2. Set up the host's nginx from [`nginx/README.md`](https://github.com/privacyfence/privacyfence-suite/blob/main/configs/nginx-google/nginx/README.md): render the example site configuration, point it at your certificate, and open the firewall for the `pf-suite` interface (TCP 443). The stack needs these from the host:
   - Linux with rootful Docker;
   - nginx 1.25.1 or later listening on all addresses for 80 and 443, so it also answers on `172.30.87.1`;
   - a certificate covering the three names;
   - a firewall that lets the `pf-suite` interface reach the host on TCP 443.
3. `docker compose up -d`.
4. Publish the relay DNS records as for `caddy-google`, then sign in at `https://<PF_HOSTNAME>`.

### localhost

One person, one computer, everything published on `127.0.0.1` only. No `.env` editing is needed.

1. `docker compose up -d` (or install with `--start`).
2. `docker compose logs privacyfence | grep "Setup code"` prints the setup code.
3. Open <http://localhost:8765>, enter the code and set up your passkey.

Peek is at <http://localhost:7700> and Grist at <http://localhost:8484>. Anyone who can run `docker` on the computer controls the install.

## What is already connected

- Peek and Grist sign people in through PrivacyFence ("Sign in with SSO"), so whatever PrivacyFence uses upstream (your identity provider, Google, or the single-user passkey) applies to all three apps.
- Each person who signs in to PrivacyFence gets their Peek account and Grist key connected automatically.
- Grist users are created and added to the team site (`team` by default) by the provisioner.
- Signing out of Peek or Grist ends only that app's session; the PrivacyFence session stays.

## Sign-in notes

- **`caddy-google` and `nginx-google`** admit only verified Google Workspace accounts, admins included; personal Gmail addresses cannot sign in. The PrivacyFence container needs outbound HTTPS to `oauth.privacyfence.eu`.
- **`ALLOWED_DOMAIN`** (exactly one domain) limits who signs in to all three apps. PrivacyFence reads it only at its **first start**; to change it later, use its Admin page. Peek and the provisioner pick up a changed value at their next start.
- **`caddy-idp`:** Peek and Grist refuse a sign-in unless `email_verified` is true. An identity provider that never sends the claim (for example Microsoft Entra ID) needs `IDP_TRUST_UNVERIFIED_EMAIL=true`, which trusts addresses in `ALLOWED_DOMAIN`.

## Admins

- **PrivacyFence admins** are `ADMIN_EMAILS`.
- **Peek admins** are `PEEK_ADMIN_EMAILS` (optional, empty by default). Peek refuses to provision an admin's account, so a Peek admin is **not** connected automatically: they connect Peek by hand on PrivacyFence's `/connect`. Each address must be in `ALLOWED_DOMAIN`. Use a dedicated admin address. With the variable empty, Peek simply has no admin; everything the suite needs comes from the environment.
- **Grist install admin** is `GRIST_ADMIN_EMAIL`. It must be a real address that can sign in to PrivacyFence, because Grist signs people in only through PrivacyFence. Their automatic Grist key is refused too; they paste their own key on `/connect` if they want PrivacyFence to reach Grist. Use a dedicated admin address.
- **`localhost`** has no Peek admin and nobody can become one. Grist's admin there is `grist-admin@privacyfence.localhost`, which nobody can sign in as, so that Grist is administered by the boot key only.

## Versions

This release pins the following; `.env` holds the tags.

| Image | Tag |
|---|---|
| Peek | `0.18.0` |
| Grist (from PrivacyFence's grist-core fork) | `1.7.22-pf.4` |
| grist-provisioner | `0.2.0` |
| PrivacyFence | `latest` (floats on purpose) |
| Alpine (the one-shot `init`) | `3.22` |
| Caddy (Caddy configurations) | `2.10.2` |

**PrivacyFence follows `latest`, and the suite needs PrivacyFence 7.0.0 or later.** Earlier versions lack the OIDC clients for Peek and Grist and the automatic provisioning. Update PrivacyFence with no suite update:

```sh
docker compose pull privacyfence && docker compose up -d
```

To hold an update back, set `PRIVACYFENCE_IMAGE_TAG` in `.env` to an exact version, for example `7.0.0`.

Grist comes from PrivacyFence's [grist-core fork](https://github.com/privacyfence/grist-core/blob/main/pf/README.md): the open-source build with the full-edition switch off, and a check on every release that OIDC sign-in, API keys, the boot key, the team-site access API and the free plan's limits are not locked out.

## More documentation

- PrivacyFence: [Docker deployment](https://github.com/privacyfence/privacyfence/blob/main/docs/org-mode-docker.md), [setup guide](https://github.com/privacyfence/privacyfence/blob/main/docs/org-mode-setup-guide.md) (built-in Google sign-in, relay DNS records) and [OIDC provider](https://github.com/privacyfence/privacyfence/blob/main/docs/oidc-provider.md).
- [Peek's authentication docs](https://github.com/privacyfence/peek/tree/main/docs).
- [grist-provisioner](https://github.com/privacyfence/grist-provisioner#readme).
- This repository: [configurations](https://github.com/privacyfence/privacyfence-suite/blob/main/docs/configurations.md), [operations](https://github.com/privacyfence/privacyfence-suite/blob/main/docs/operations.md), [releasing](https://github.com/privacyfence/privacyfence-suite/blob/main/docs/releasing.md), [changelog](https://github.com/privacyfence/privacyfence-suite/blob/main/CHANGELOG.md).

## License

Apache-2.0, see [LICENSE](LICENSE).
