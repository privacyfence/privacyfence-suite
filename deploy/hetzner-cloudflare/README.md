# Hetzner VM + Cloudflare proxy + nginx + Google sign-in

Runs the `nginx-google` configuration of the suite on a fresh Ubuntu/Debian VM, behind Cloudflare
(orange cloud), for `pf.tkcs.name`, `peek.tkcs.name` and `grist.tkcs.name`. SSH only over Tailscale.

## Why a Let's Encrypt certificate and not a Cloudflare Origin CA certificate

The suite's containers call the public names (`extra_hosts` maps them to the host's nginx at
`172.30.87.1`). That traffic does not go through Cloudflare, so the certificate nginx presents must be
trusted by the containers. A Cloudflare Origin CA certificate is trusted only by Cloudflare, so Peek,
Grist and PrivacyFence would fail TLS verification. `bootstrap.sh` issues one publicly trusted Let's
Encrypt certificate for the three names with the DNS-01 challenge through the Cloudflare API, which works
with the proxy on. Cloudflare SSL/TLS mode **Full (strict)** accepts it.

## Before you start (about 10 minutes)

1. **Cloudflare DNS**: `A` (and `AAAA` if the VM has IPv6) records for the three names to the VM, proxied.
2. **Cloudflare SSL/TLS mode**: Full (strict). Leave "Always Use HTTPS" on.
3. **Cloudflare API token**: My Profile → API Tokens → Edit zone DNS template, limited to the `tkcs.name` zone
   (needs Zone:DNS:Edit and Zone:Zone:Read). Used only by certbot.
4. **Tailscale auth key**: https://login.tailscale.com/admin/settings/keys (one-off, not reusable).
5. **Google Workspace**: nothing to register. `ALLOWED_DOMAIN` must be a Workspace domain whose people can sign in; personal Gmail is refused.
   `ADMIN_EMAILS` and `GRIST_ADMIN_EMAIL` must be real addresses in that domain.
6. **Hetzner Cloud Firewall** (optional, extra layer): inbound TCP 443 from Cloudflare ranges, TCP 22 until Tailscale works, ICMP.

## Run

On the VM, as root, with SSH keys you already have:

```sh
apt-get update && apt-get install -y git
git clone -b claude/pf-suite-google-idp-cloudflare-h1ppym https://github.com/privacyfence/privacyfence-suite.git /root/pf-src
cd /root/pf-src/deploy/hetzner-cloudflare
install -m 600 pf-deploy.env.example /root/pf-deploy.env
nano /root/pf-deploy.env
./bootstrap.sh all
```

`all` runs: base packages, Tailscale (`--ssh`), Docker, nginx from nginx.org (distro nginx is older than the
suite's 1.25.1 minimum), the certificate, Cloudflare IP ranges (real client IP + firewall), ufw, then
downloads the suite release (checksum verified), fills `.env`, installs the nginx site and starts the stack
in `/opt/privacyfence-nginx-google`. Each step can be re-run alone (`./bootstrap.sh cert`, ...).

## Afterwards

1. **Publish the relay DNS records** (built-in Google sign-in needs them once):
   ```sh
   cd /opt/privacyfence-nginx-google && docker compose exec privacyfence privacyfence-app --relay-dns-records
   ```
   Add the printed `_privacyfence-relay` TXT records in Cloudflare (TXT records are never proxied).
2. Open `https://pf.tkcs.name` and sign in with a Workspace admin from `ADMIN_EMAILS`. Peek and Grist appear connected.
3. **Lock SSH**: from another terminal confirm `ssh root@pf-suite` (Tailscale name/IP) works, then on the VM:
   ```sh
   /root/pf-src/deploy/hetzner-cloudflare/bootstrap.sh lock-ssh
   ```
4. Check: `curl -s -o /dev/null -w "%{http_code}\n" https://grist.tkcs.name/api/provisioning/self` prints `404`.

## What differs from the stock `nginx-google` site file

- Real client IP from `CF-Connecting-IP`, trusted only from Cloudflare's published ranges
  (refreshed weekly by `/etc/cron.weekly/pf-cf-refresh`); `X-Forwarded-For` is set to that single address.
  The provisioner's `$remote_addr` check cannot be spoofed through the header.
- ufw: default deny; 443 from Cloudflare ranges and from the `pf-suite` bridge only (the containers call nginx on it);
  everything on `tailscale0`; port 22 open until `lock-ssh`.

## Known limits behind Cloudflare

- Non-Enterprise plans cut a proxied request after 100 s without response bytes; long-idle MCP/SSE streams
  need keep-alives, or set that hostname to DNS-only (grey cloud) for testing.
- 100 MB upload cap on Free/Pro (matches `client_max_body_size`).
- Optional hardening: Cloudflare Authenticated Origin Pulls.
