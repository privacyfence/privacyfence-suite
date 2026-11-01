# Changelog

## [Unreleased]

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
