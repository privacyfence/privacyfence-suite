# nginx-host: the site configuration for the nginx on your host

This configuration starts no proxy container. The nginx that already runs on your host terminates
TLS and proxies to the apps on `127.0.0.1`: PrivacyFence `8765`, Peek `7700`, Grist `8484`, and the
Grist provisioner `8485` (for PrivacyFence's container only).

## Requirements

- Linux with rootful Docker (Engine 24+) and Docker Compose 2.24+. Docker Desktop and rootless Docker
  do not route the stack's `172.30.87.x` addresses to the host.
- nginx with plain `listen 80;` and `listen 443 ssl;` on all addresses, so it also answers the
  containers on `172.30.87.1`.
- A certificate from a public CA for each name: the containers call the public names through this
  nginx and check the certificate like a browser does.

## Render and install

`render.sh` fills the template from `../.env` and prints the site. It writes nothing.

```sh
sh nginx/render.sh > /tmp/privacyfence-suite.conf
less /tmp/privacyfence-suite.conf
sudo install -m 644 /tmp/privacyfence-suite.conf /etc/nginx/conf.d/privacyfence-suite.conf
sudo nginx -t && sudo systemctl reload nginx
```

- **Certificates** default to `/etc/ssl/certs/<host>/fullchain.pem` and `privkey.pem`. Set
  `CERT_ROOT`, or `PF_CERT`/`PF_KEY`, `PEEK_CERT`/`PEEK_KEY`, `GRIST_CERT`/`GRIST_KEY`, in `.env` or in
  the environment to change that.
- **More Peek names:** every name in `PEEK_REDIRECT_HOSTNAMES` gets a server that redirects to
  `PEEK_HOSTNAME`, with the certificate at `<CERT_ROOT>/<name>/`.
- **Rate limit:** the PrivacyFence server limits `/register`, `/authorize` and `/token` with the
  `pf_oauth` zone. If another file of your nginx already defines that zone, `render.sh` uses it and
  says so, because nginx refuses a zone defined twice.
- **Old site files** for the same names must go: nginx serves only one server per name. To find
  them, symlinks in `sites-enabled` included:

  ```sh
  sudo nginx -T 2>/dev/null | awk '/^# configuration file /{f=$4; sub(/:$/,"",f)} $1 == "server_name" {print f": "$0}'
  ```

## Firewall

The containers call the three public names, which resolve to `172.30.87.1`, so the `pf-suite`
interface must reach the host on TCP 443:

```sh
sudo ufw allow in on pf-suite to any port 443 proto tcp
```

The same for firewalld: allow the `pf-suite` interface to reach TCP 443.

## Which names the internet reaches

The site adds no IP rules. If some names should be reachable only from your VPN, keep doing that in
DNS or at the network edge, or add `allow`/`deny` to their server blocks (allow `172.16.0.0/12` too,
so the containers on `pf-suite` keep reaching them).

## After an upgrade

If the release notes say `nginx/privacyfence-suite.conf.template` changed, render and install it again
as above.

## Check

From outside the host, this prints `404` (the provisioner answers PrivacyFence only):

```sh
curl -s -o /dev/null -w "%{http_code}\n" https://<GRIST_HOSTNAME>/api/provisioning/self
```
