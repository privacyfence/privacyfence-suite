# Changelog

## [Unreleased]

### Fixed

- `deploy/nginx-host-migration/migrate.sh copy` no longer stops halfway with "not empty; refusing to overwrite" after the old services are stopped. Creating the stack let Docker put the images' default folders into the new volumes; the volumes are now checked before the stack is created and cleared right before each copy.
- `copy` switches Peek's own Google org sign-up off in the copied database. Peek refuses to start with it next to sign-up through PrivacyFence (`auth_oidc_signup cannot be used with auth_google_org_signup`); `preflight` reports it beforehand. The old Peek's database is not changed.
- `migrate.sh nginx` uses a `pf_oauth` rate-limit zone that another nginx file already defines, instead of defining it again (`limit_req_zone "pf_oauth" is already bound`).

### Added

- `migrate.sh nginx-files` lists the nginx files that serve the three names (and `OLD_EXTRA_HOSTNAMES`) from `nginx -T`, so symlinks in `sites-enabled` are found; `preflight` shows the list.
- `copy` renames the Compose files the old Peek and Grist containers were started from to `….migrated`, so they cannot be started beside the stack; `rollback` renames them back.
- The README covers Compose v2 on Ubuntu, a Grist without a team site (create one and move the documents), a `GRIST_ADMIN_EMAIL` nobody signs in with, and a full clean-up with an archive first.
- Peek page backends, optional in every configuration and in `deploy/nginx-host-migration`: a new `compose.backends.yaml` gives Peek the Docker socket and a separate `peek-backends` network, and is read only when `.env` sets `COMPOSE_FILE=compose.yaml:compose.backends.yaml` and `DOCKER_GID`. Off by default, because the socket is root on the host. In `localhost` it also makes `admin@privacyfence.localhost` the Peek admin, who then connects Peek by hand on `/connect`. New `.env` variables (add them to an existing `.env` to turn backends on): `COMPOSE_FILE`, `DOCKER_GID`. `scripts/check_configs.py` checks that only this file mounts the socket, and CI runs `docker compose config` with it.

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
