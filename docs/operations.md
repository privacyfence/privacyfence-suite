# Operations

Commands run in the configuration's folder (`privacyfence-<config>`). The Compose project is named `privacyfence-<config>`, so its volumes are `privacyfence-<config>_<volume>`; `docker volume ls` lists them.

## Install

```sh
curl -fsSL https://github.com/privacyfence/privacyfence-suite/releases/latest/download/install.sh | sh -s -- <config>
```

or download `privacyfence-suite-<config>.zip` / `.tar.gz` from a release and unpack it. See the [README](../README.md#install) for the pinned and verified forms.

## Upgrade

From the new release, run the installer on the existing folder, or unpack the new archive over it. `.env`, `privacyfence.env` and your secret files are never in an archive, so they are kept:

```sh
curl -fsSL https://github.com/privacyfence/privacyfence-suite/releases/latest/download/install.sh | sh -s -- <config> --dir <dir> --upgrade
cd <dir> && docker compose pull && docker compose up -d
```

Files that a release dropped stay in place; the release notes name them. Read the release notes for changed image tags and new `.env` variables. For `nginx-google`, if the notes say `nginx/privacyfence-suite.conf` changed, render it again as in `nginx/README.md` and reload nginx.

PrivacyFence floats on `latest`, so updating only PrivacyFence needs no suite upgrade: `docker compose pull privacyfence && docker compose up -d`.

## Backup

Stop the stack, archive each volume, start it again. The volumes hold all state (including the generated secrets), so keep the backup private.

```sh
project=privacyfence-<config>        # the Compose project name
docker compose stop
mkdir -p backup
for v in pf-data peek-data grist-data provisioner-data pf-secrets peek-secrets grist-secrets provisioner-secrets; do
  docker run --rm -v "${project}_$v:/v:ro" -v "$PWD/backup:/b" alpine:3.22 tar czf "/b/$v.tar.gz" -C /v .
done
docker compose start
```

The Caddy configurations also have `caddy-data` (the certificates) and `caddy-config`; add them to the list. With [Peek page backends](configurations.md#peek-page-backends) on, each page with a backend has its own volume, `peek-<instance>-data-u<id>` (`docker volume ls --filter name=peek-`), which is not part of the project's volumes; archive those the same way. Each archive is one `docker run --rm -v <volume>:/v alpine tar` command. To restore, create the volume and unpack with `tar xzf` the same way, with the stack stopped.

## Rotating a generated value

Remove the canonical copy; `init` then generates a new value and installs it everywhere on the next `up`. `<name>` is one of `peek_provisioning_key`, `grist_provisioning_key`, `peek_oidc_client_secret`, `grist_oidc_client_secret`, `grist_boot_key`, `grist_session_secret`:

```sh
docker compose run --rm --no-deps init rm /out/pf/.<name>
docker compose up -d --force-recreate
```

PrivacyFence and Grist read every secret once at start, so a rotation always ends with a restart or recreate. Rotating `grist_session_secret` signs everyone out of Grist.

## Rotating the IdP secret (`caddy-idp`)

Replace `secrets/idp_client_secret` with the new value, then:

```sh
docker compose up -d                 # init installs the new copy
docker compose restart privacyfence  # PrivacyFence reads it once at start
```

## Removing a person

First remove the person from your identity provider or Google Workspace (or change the allowed domain on PrivacyFence's Admin page), because anyone who can still sign in is provisioned again.

Then disconnect the person's Peek account and Grist key with PrivacyFence's `--peek-release` and `--grist-release` options. They take the person's `PRINCIPAL_ID`: the id that is their folder name under `users/` in PrivacyFence's data volume.

```sh
docker compose exec privacyfence privacyfence-app --peek-release PRINCIPAL_ID
docker compose exec privacyfence privacyfence-app --grist-release PRINCIPAL_ID
```

To find the id from an email address, look for the person's provisioning state; the id is the folder name after `users/`:

```sh
docker compose exec privacyfence sh -c 'grep -l -F person@example.com /var/lib/privacyfence-org/.privacyfence/users/*/credentials/*_provisioning.json'
```

The provisioning keys reach the command through the `*_FILE` variables already in the container's environment.

## Troubleshooting

- **Init log.** `docker compose logs init` shows `init: generated <name>` on the first start only (never the value) and `init: installed idp_client_secret` on every start of `caddy-idp`. Seeing `generated` lines again means a volume was lost or a value was removed on purpose.
- **Where provisioning is logged.** PrivacyFence logs connecting a person (`docker compose logs privacyfence`); Peek logs the account it creates (`docker compose logs peek`); the provisioner logs Grist users and team-site membership (`docker compose logs grist-provisioner`). `docker compose exec grist-provisioner grist-provisioner check` prints `ok: N Grist users, M linked` and `team site: <site>`. Provisioning that failed because an app was not up yet is retried at the person's next sign-in and by PrivacyFence's six-hourly sweep.
- **Grist keeps restarting at first start.** Grist waits up to 5 minutes for PrivacyFence's `/oidc/.well-known/openid-configuration` through the proxy (Caddy may still be getting its first certificate) and exits with `grist: PrivacyFence is not reachable at <url>` if it never answers. Check the DNS names and ports 80/443, and `docker compose logs caddy`. It starts by itself once the proxy answers.
- **`localhost`: PrivacyFence restarted.** Peek, Grist and the provisioner share PrivacyFence's network namespace and lose it when PrivacyFence's container restarts. Run `docker compose up -d` to recreate them.
- **`localhost`: no setup code.** `docker compose logs privacyfence | grep "Setup code"`. Five wrong codes use a code up; restart PrivacyFence (and then `docker compose up -d`) for a new one.
- **Compose refuses to start with "set X in .env".** A required variable is empty; see [configurations](configurations.md).
- **`nginx-google`: the apps cannot reach the public names.** The containers resolve the three names to `172.30.87.1` and call the host's nginx there. Causes:
  - the firewall blocks the `pf-suite` interface from TCP 443 (see `nginx/README.md`);
  - nginx listens only on a public address, not on all addresses (`listen 443 ssl;`, not `listen <ip>:443`), so it does not answer on `172.30.87.1`;
  - nginx is not running or `nginx -t` failed on the site file.

  From the Grist container, which has Node (the suite's health check for Grist uses it), test each name:

  ```sh
  docker compose exec grist node -e "fetch('https://<PF_HOSTNAME>/oidc/.well-known/openid-configuration').then(r=>console.log(r.status),e=>console.log(e.cause||e))"
  docker compose exec grist node -e "fetch('https://<PEEK_HOSTNAME>/healthz').then(r=>console.log(r.status),e=>console.log(e.cause||e))"
  ```

  While Grist's wrapper is restarting, `exec` can fail. This form works then; it needs no secrets because `--entrypoint node` skips the wrapper:

  ```sh
  docker compose run --rm --no-deps --entrypoint node grist -e "fetch('https://<PF_HOSTNAME>/oidc/.well-known/openid-configuration').then(r=>console.log(r.status),e=>console.log(e.cause||e))"
  ```

  If this reports that the address is in use, Grist is up: use the `exec` form above.

  `200` means the path works; a timeout points at the firewall, a refusal at the listen address, a certificate error at the certificate (it must cover all three names). From outside, `curl -s -o /dev/null -w "%{http_code}" https://<GRIST_HOSTNAME>/api/provisioning/self` must print `404`.
- **Peek says first-run setup is skipped.** Expected: the suite configures Peek from the environment. The line appears only while Peek's database has no accounts.
