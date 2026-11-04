# Changelog

## [Unreleased]

## [0.1.4] - 2026-11-04

No image tag changed and no file is dropped (`deploy/` was never in an archive). Every configuration gains `compose.backends.yaml`, which stays off unless `.env` turns it on; `nginx-host` is new. PrivacyFence follows `latest`, 7.0.0 or later.

### Added

- The `nginx-host` configuration: PrivacyFence, Peek and Grist behind an nginx that already runs on the host, with each app published on `127.0.0.1` (PrivacyFence 8765, Peek 7700, Grist 8484, the provisioner 8485), so the host's nginx proxies to `127.0.0.1` as it would to apps installed on the host. PrivacyFence signs people in with whatever `privacyfence.env` names: your own OIDC provider (Microsoft Entra ID included), your own Google app, or the built-in Google sign-in. `nginx/render.sh` prints the site from `.env`: it adds a redirect server for each name in `PEEK_REDIRECT_HOSTNAMES`, and uses a `pf_oauth` rate-limit zone that another nginx file already defines instead of defining it again. `install.sh nginx-host` installs it and `--upgrade` updates it like the other configurations.
- Peek page backends, optional in every configuration: a new `compose.backends.yaml` gives Peek the Docker socket and a separate `peek-backends` network, and is read only when `.env` sets `COMPOSE_FILE=compose.yaml:compose.backends.yaml` and `DOCKER_GID`. Off by default, because the socket is root on the host. In `localhost` it also makes `admin@privacyfence.localhost` the Peek admin, who then connects Peek by hand on `/connect`. New `.env` variables (add them to an existing `.env` to turn backends on): `COMPOSE_FILE`, `DOCKER_GID`. `scripts/check_configs.py` checks that only this file mounts the socket, and CI runs `docker compose config` with it.
- `check_configs.py` accepts a host-nginx configuration whose services publish only their own port on `127.0.0.1`, with nginx proxying to exactly those ports, and checks `nginx/*.conf.template` files too.

### Removed

- `deploy/`: the Hetzner + Cloudflare bootstrap and the migration kit (`deploy/nginx-host-migration`, including the unreleased fixes from privacyfence/privacyfence-suite#15). Both fitted particular servers. They were never part of the release archives, so no installed folder loses a file.

## [0.1.3] - 2026-11-01

No image tag changed and no file is dropped; the configurations are the same as in 0.1.2 (PrivacyFence follows `latest`, 7.0.0 or later).

### Added

- `deploy/nginx-host-migration/`: moves a server that runs PrivacyFence from pip (systemd), Peek and Grist as separate containers and the host's nginx into one stack, keeping every app's data. Peek and Grist then sign in through PrivacyFence and the new grist-provisioner gives each person their Grist user and key. The apps keep their `127.0.0.1` ports, so nginx keeps its upstreams. `migrate.sh` runs a read-only preflight (versions, bundle retired, Grist sites and owners, htpasswd names against Grist logins), copies the data with the old services stopped, renders the nginx site and rolls back. It lives in the repository only and is not part of the release archives.

### Changed

- `deploy/hetzner-cloudflare/`: the README clones `main` instead of a feature branch, explains the Tailscale policy a tagged auth key needs for Tailscale SSH, and says that `all` is safe to run again after a failure.

### Fixed

- `deploy/hetzner-cloudflare/bootstrap.sh`: the firewall step no longer exits silently, before enabling ufw, when there are no earlier Cloudflare or SSH rules to replace (the first run).

## [0.1.2] - 2026-11-01

No image tag changed and no file is dropped; the configurations are the same as in 0.1.1 (PrivacyFence follows `latest`, 7.0.0 or later).

### Changed

- `deploy/hetzner-cloudflare/`: the README and `pf-deploy.env.example` use `example.com` as the placeholder domain.

## [0.1.1] - 2026-11-01

No image tag changed and no file is dropped; the configurations are the same as in 0.1.0 (PrivacyFence follows `latest`, 7.0.0 or later).

### Added

- `deploy/hetzner-cloudflare/`: a bootstrap for a fresh Ubuntu or Debian VM that runs `nginx-google` behind the Cloudflare proxy with SSH over Tailscale only (Docker, nginx from nginx.org, a Let's Encrypt certificate through the Cloudflare DNS-01 challenge, real client IPs from Cloudflare, ufw, then the suite). It lives in the repository only and is not part of the release archives.

## [0.1.0] - 2026-11-01

First release.

### Image tags

PrivacyFence follows `latest` (7.0.0 or later; `PRIVACYFENCE_IMAGE_TAG` in `.env` pins an exact version). Everything else is pinned: Peek 0.18.0, grist-provisioner 0.2.0, Grist 1.7.22-pf.4 (PrivacyFence's grist-core fork), Alpine 3.22 and, in the Caddy configurations, Caddy 2.10.2.

### Added

- The `localhost` configuration (PrivacyFence, Peek and Grist for one person, signing in through PrivacyFence, with generated provisioning keys and OIDC client secrets and Peek and Grist connected at sign-in), its end-to-end workflow and a CI check of the Grist image. PrivacyFence floats on `latest` in `.env.example`; the end-to-end workflow runs against it on every push and weekly.
- The `caddy-idp` and `caddy-google` configurations (PrivacyFence, Peek, Grist and Caddy with automatic certificates), and a CI check that validates their Caddyfiles.
- The `nginx-google` configuration for an nginx already running on the host: the stack without a proxy container, an example nginx site configuration, and CI checks for both.
- The release workflow (.zip and .tar.gz archives per configuration, `SHA256SUMS` and build provenance) and the `install.sh` one-line installer (checksum-verified, with `--upgrade` and `--start`).
