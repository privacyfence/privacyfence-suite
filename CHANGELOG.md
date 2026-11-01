# Changelog

## [Unreleased]

### Added

- The four configurations: caddy-idp, caddy-google, nginx-google (for an nginx already on the host, with an example site configuration) and localhost, with generated provisioning keys and OIDC client secrets, Peek and Grist signing in through PrivacyFence, and connected at sign-in.
- One-command install: per-configuration .zip and .tar.gz release assets, an install.sh for curl | sh, SHA256SUMS and build provenance.
- The `localhost` configuration (PrivacyFence, Peek and Grist for one person, signing in through PrivacyFence), its end-to-end workflow and a CI check of the Grist image. PrivacyFence floats on `latest` in `.env.example`; the end-to-end workflow pins 7.0.0b1 and also runs weekly.
- The `caddy-idp` and `caddy-google` configurations (PrivacyFence, Peek, Grist and Caddy with automatic certificates), and a CI check that validates their Caddyfiles.
- The `nginx-google` configuration for an nginx already running on the host: the stack without a proxy container, an example nginx site configuration, and CI checks for both.
- The release workflow, per-configuration archives and the `install.sh` one-line installer (checksum-verified, with `--upgrade` and `--start`).
