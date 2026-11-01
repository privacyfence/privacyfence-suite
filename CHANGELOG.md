# Changelog

## [Unreleased]

### Added

- The `localhost` configuration (PrivacyFence, Peek and Grist for one person, signing in through PrivacyFence), its end-to-end workflow and a CI check of the Grist image. PrivacyFence floats on `latest` in `.env.example`; the end-to-end workflow pins 7.0.0b1 and also runs weekly.
- The `caddy-idp` and `caddy-google` configurations (PrivacyFence, Peek, Grist and Caddy with automatic certificates), and a CI check that validates their Caddyfiles.
- The `nginx-google` configuration for an nginx already running on the host: the stack without a proxy container, an example nginx site configuration, and CI checks for both.
