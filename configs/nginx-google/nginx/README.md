# nginx-google: the example site configuration for the nginx on your host

This configuration starts no proxy container. The nginx that already runs on your host terminates
TLS and forwards to the stack's fixed addresses on the `pf-suite` bridge (`172.30.87.10` to `.13`).

## Requirements

- Linux with rootful Docker (Engine 24+). Docker Desktop and rootless Docker do not route
  `172.30.87.x` to the host; use `caddy-google` there.
- nginx 1.25.1 or later (for `http2 on;`), with plain `listen 80;` and `listen 443 ssl;` on all
  addresses, so it also answers on `172.30.87.1`.
- A public certificate that covers the three names (SAN or wildcard).

## Install and reload

After `.env` is filled in, run in the `nginx-google` folder:

```sh
. ./.env && sed -e "s/pf\.example\.com/$PF_HOSTNAME/g" \
  -e "s/peek\.example\.com/$PEEK_HOSTNAME/g" -e "s/grist\.example\.com/$GRIST_HOSTNAME/g" \
  nginx/privacyfence-suite.conf | sudo tee /etc/nginx/conf.d/privacyfence-suite.conf >/dev/null
sudo nginx -t && sudo systemctl reload nginx
```

## Certificate paths

Edit `ssl_certificate` and `ssl_certificate_key` in each of the three `443` server blocks of
`/etc/nginx/conf.d/privacyfence-suite.conf` (shipped as `/etc/ssl/privacyfence-suite/fullchain.pem`
and `privkey.pem`), then reload nginx.

## Firewall

The containers call the three public names, which resolve to `172.30.87.1`, so the `pf-suite`
interface must reach the host on TCP 443:

```sh
sudo ufw allow in on pf-suite to any port 443 proto tcp
```

The same for firewalld: allow the `pf-suite` interface to reach TCP 443.

## certbot

A certbot `http-01` webroot challenge needs its own `location /.well-known/acme-challenge/` in the
port-80 server block, ahead of the redirect.

## Check

From outside the host, this prints `404` (the provisioner is reachable from PrivacyFence only):

```sh
curl -s -o /dev/null -w "%{http_code}" https://<grist host>/api/provisioning/self
```
