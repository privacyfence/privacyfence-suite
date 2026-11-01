# Moving an existing PrivacyFence, Peek and Grist server onto the suite

Use this for a server that already runs:

- **PrivacyFence 6.x from pip**: the venv in `/opt/privacyfence/venv`, the systemd unit
  `privacyfence-org`, data in `/var/lib/privacyfence-org/.privacyfence`, and a 6.x organization bundle
  (`org/org_config.json`);
- **Peek** and **Grist** as their own Docker containers, Grist with SQLite (the default);
- **the host's nginx** in front of all three, proxying to `127.0.0.1:8765`, `:7700` and `:8484`.

Afterwards one Compose stack (`compose.yaml`) runs PrivacyFence, Peek, Grist and the new
grist-provisioner. The apps keep the same `127.0.0.1` ports, so nginx keeps its upstreams. Peek and
Grist sign people in **through PrivacyFence** (OIDC), and each person's Peek account and Grist key are
connected automatically. **All existing data is kept:**

| App | What is kept | How people find their data again |
|---|---|---|
| PrivacyFence | the whole data directory (connections, passkeys, policies, AI clients, audit logs) | it is the same directory, copied into the `pf-data` volume |
| Peek | the whole `/data` (accounts, uploads, links, provisioning) | an SSO sign-in finds the existing account by email; the 6.11 provisioner's key is rotated in place (`PEEK_PROVISIONING_KEY_NAME`), so its links stay |
| Grist | the whole `/persist` (home database, documents) | an SSO sign-in finds the existing Grist user by email, so the htpasswd user names must be those email addresses; the documents must be in the team site |

The old data is only read. Until you delete them, the old directory, containers and nginx file are a
complete way back ([Rollback](#rollback)).

Nothing here is specific to one organization: host names, domains and certificate paths live in `.env`.

## Files

| File | Purpose |
|---|---|
| `compose.yaml` | The stack: `init` (generated secrets, as in every suite configuration), `privacyfence`, `peek`, `grist`, `grist-provisioner` on the `pf-suite` bridge `172.30.87.0/24`, each published on `127.0.0.1` |
| `.env.example` | Image tags, host names, domain, Grist team site and admin, plus the old locations `migrate.sh` reads |
| `privacyfence.env.example` | PrivacyFence's mode, identity provider and admins (from the retired bundle) |
| `secrets/` | `idp_client_secret`, if PrivacyFence uses your own identity provider |
| `migrate.sh` | `preflight` (read-only checks), `copy` (stop the old services, copy the data), `nginx` (render the site), `rollback` |
| `preflight_grist.py` | The read-only report on Grist's home database that `preflight` runs in the old Grist container |
| `nginx/privacyfence-suite.conf.template` | The nginx site afterwards |
| `init.sh` | The same file as `common/init.sh` |

## Step 0: back up

With PrivacyFence stopped, archive its data directory, and archive Peek's `/data` and Grist's
`/persist` with the containers stopped. Keep a copy of `/etc/systemd/system/privacyfence-org.service`,
`/etc/privacyfence-org.env` and the files it names, and the current nginx site files.

```bash
sudo systemctl stop privacyfence-org
sudo tar -C /var/lib/privacyfence-org -czf /root/pf-data-$(date +%F).tar.gz .privacyfence
sudo systemctl start privacyfence-org
```

## Step 1: upgrade the pip install to 7.x and retire the bundle

The suite needs PrivacyFence 7.0.0 or later. Upgrade in place first: this is PrivacyFence's documented
upgrade, it converts the data and the bundle on the same install, and it can be undone (6.10.0 or newer
reads the 6.x files 7.x leaves untouched). Read the
[7.0.0 changelog](https://github.com/privacyfence/privacyfence/blob/main/CHANGELOG.md) first.

> **Microsoft Entra ID** (or any identity provider without `email_verified`): 7.x refuses
> everyone in the allowed domains until `PRIVACYFENCE_IDP_TRUST_UNVERIFIED_EMAIL=true` is set, and
> the bundle's `idp` section wins over the environment. Do the bundle retirement below right after
> the restart, adding that variable to `/etc/privacyfence-org.env`, before people sign in.

```bash
sudo /opt/privacyfence/venv/bin/pip install privacyfence==7.0.0
sudo systemctl restart privacyfence-org
journalctl -u privacyfence-org -f        # look for "Org mode active"
```

The first start copies `org/org_config.json` to `org/org_bundle.json`, imports the bundle's apps as
signed connector configs and its settings into `org/admin_config.json`. Then move the server and
identity-provider settings out of the bundle
([guide](https://github.com/privacyfence/privacyfence/blob/main/docs/org-mode-setup-guide.md#a-6x-bundle-on-an-upgraded-server)):

```bash
sudo -H -u privacyfence-org /opt/privacyfence/venv/bin/privacyfence-app --print-env-from-bundle \
  --idp-secret-file /var/lib/privacyfence-org/idp_client_secret
```

Put the printed lines in `/etc/privacyfence-org.env`, restart, and retire the bundle:

```bash
sudo systemctl restart privacyfence-org
sudo sh -c 'set -a; . /etc/privacyfence-org.env; set +a; exec sudo -H -u privacyfence-org --preserve-env /opt/privacyfence/venv/bin/privacyfence-app --retire-bundle'
```

Check before going on: people sign in as before, the connectors work, and **Admin → Services** shows
the Peek row with the variable the server reads its key from. If that is not
`PRIVACYFENCE_PEEK_PROVISIONING_KEY`, note the name: the stack needs `<that name>_FILE` (step 2).

## Step 2: prepare the folder

Copy this folder to the server (for example `/opt/privacyfence-host`), then:

```bash
cd /opt/privacyfence-host
cp .env.example .env && chmod 600 .env
install -m 600 privacyfence.env.example privacyfence.env
```

- **`.env`**: the three host names as nginx serves them; `PEEK_HOSTNAME` is the name PrivacyFence
  6.11 already connects Peek with. `ALLOWED_DOMAIN`, `GRIST_TEAM_SITE` (the existing team site's
  domain), `GRIST_ADMIN_EMAIL` (an owner of that site), `PEEK_PROVISIONING_KEY_NAME` (Peek's Admin
  page lists the provisioning keys; use the one PrivacyFence uses), `OLD_GRIST_HTPASSWD`.
  `PRIVACYFENCE_IMAGE_TAG` is the version step 1 installed.
- **`privacyfence.env`**: the lines from `/etc/privacyfence-org.env` that step 1 added (mode,
  identity provider, admins), with `PRIVACYFENCE_IDP_CLIENT_SECRET_FILE=/run/suite/idp_client_secret`.
  Leave out the old Peek and Grist provisioning keys. If step 1 showed a different key variable for
  Peek, add `<that name>_FILE=/run/suite/peek_provisioning_key`.
- **`secrets/idp_client_secret`**: `sudo install -m 600 /var/lib/privacyfence-org/idp_client_secret secrets/`
  (own identity provider only).

## Step 3: preflight

```bash
sudo ./migrate.sh preflight
```

It changes nothing. It checks the pip version and that the bundle is retired, the old containers and
their mounts, that the old Grist is not newer than the fork image (a database cannot move back to an
older Grist) and uses SQLite, and the network and ports. From Grist's home database it lists every site
with its document count and tells you about:

- **documents in personal sites**: the stack runs Grist with one team site (`GRIST_SINGLE_ORG`), so
  move those documents to the team site in the old Grist (document menu, *Move*) first;
- **`GRIST_ADMIN_EMAIL` not owning the team site**: add it as an owner in the old Grist, or use an
  existing owner's address;
- **htpasswd names that are not email addresses**: Grist matches the PrivacyFence sign-in by email, so
  that person's old Grist login must be renamed to their email first, or they get a new, empty user;
- **logins outside `ALLOWED_DOMAIN`**: they can no longer sign in.

Fix every `FAIL` and decide on every `WARN` before step 4.

## Step 4: stop the old services and copy the data (downtime starts)

```bash
sudo ./migrate.sh copy
```

It pulls the images and creates the stack while the old services still run, then (after you type
`yes`) disables and stops `privacyfence-org`, stops the old `peek` and `grist` containers with their
restart policy set to `no` (the old policy is saved in `.migrate-state` for rollback), and copies:

- the pip data directory into `privacyfence-host_pf-data`, owned by the image's user `10001`;
- the old Peek's `/data` into `privacyfence-host_peek-data`;
- the old Grist's `/persist` into `privacyfence-host_grist-data`.

It refuses to copy into a volume that already holds data.

## Step 5: switch nginx and start the stack

Render the new site and look at it. Certificates default to `/etc/ssl/certs/<host>/fullchain.pem` and
`privkey.pem`; set `CERT_ROOT`, or `PF_CERT`/`PF_KEY`, `PEEK_CERT`/`PEEK_KEY`, `GRIST_CERT`/`GRIST_KEY`
in the environment to change that.

```bash
sudo ./migrate.sh nginx > /tmp/privacyfence-suite.conf
```

Replace the old PrivacyFence, Peek and Grist server blocks with it (keep the old files outside nginx's
include directory for rollback; other sites stay as they are). Any second Peek name gets a
`return 301 https://<PEEK_HOSTNAME>$request_uri;` server of its own. Then:

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow in on pf-suite to any port 443 proto tcp     # if the host runs a firewall
sudo docker compose up -d
sudo docker compose ps
```

The containers call the three public names on `172.30.87.1` (the `pf-suite` bridge), so:

- nginx must listen on all addresses (`listen 443 ssl`, not `listen <ip>:443`);
- the firewall must let the `pf-suite` interface reach TCP 443;
- the certificates must be trusted by the containers: a public CA works, a private CA does not.

## Step 6: check

- `docker compose logs init` shows `init: generated …` lines; `docker compose logs privacyfence` shows
  `Org mode active`.
- Sign in at `https://<PF_HOSTNAME>`: connectors and AI clients work as before.
- Open Peek and Grist: **Sign in with SSO** goes through PrivacyFence, and you see your existing uploads
  and documents.
- `docker compose logs peek | grep provision` shows `provisioning key "<name>" rotated`, not
  `registered` (registered means `PEEK_PROVISIONING_KEY_NAME` did not match: fix it and restart Peek).
- `docker compose exec grist-provisioner grist-provisioner check` prints the user counts and the team site.
- From outside: `curl -s -o /dev/null -w "%{http_code}\n" https://<GRIST_HOSTNAME>/api/provisioning/self`
  prints `404`.

From now on the [suite's operations guide](../../docs/operations.md) applies (backup, rotating
generated values, upgrades), with the project name `privacyfence-host`.

## Rollback

```bash
sudo ./migrate.sh rollback
```

It stops the stack, gives the old containers their restart policy back, starts them and
`privacyfence-org`. Put the old nginx site files back and reload nginx. Everything done in the stack
since step 4 is lost; the old data is as step 4 left it. Going further back, to 6.x, is in
[PrivacyFence's guide](https://github.com/privacyfence/privacyfence/blob/main/docs/org-mode-setup-guide.md#going-back-to-6x).

## Clean up (after a few weeks)

When you will not roll back any more: `docker rm peek grist` (their volumes or bind directories stay
until you remove them), `sudo /opt/privacyfence/venv/bin/pip uninstall privacyfence`, remove the unit
file, and delete the htpasswd file. Keep the step 0 backup.
