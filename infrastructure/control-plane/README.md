# Control Plane Configuration

Source-of-truth configs for the services deployed at `/srv/control-plane` on
VPS `166.88.227.177`.

## Scope

This directory holds the configs that live on the VPS and are mounted into
the `control-plane` Docker Compose stack. It does **not** include 9router
(`0.0.0.0:20128`) — that is a separate deployment and must never bind host
port `20128`.

## Deploying a Homepage fix

If the portal loads infinitely after Authelia login until manually
refreshed, the most likely cause is a missing `base` URL in Homepage
settings.

1. Copy the fixed config to the VPS:

   ```bash
   scp -P <ssh-port> homepage/settings.yaml root@166.88.227.177:/srv/control-plane/homepage/settings.yaml
   ```

2. Restart the Homepage container so it regenerates its static HTML:

   ```bash
   ssh -p <ssh-port> root@166.88.227.177 'docker restart control-homepage'
   ```

3. Hard-refresh the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`) and test a
   fresh Authelia login flow.

## Viewing Caddy logs

> **2026-08-11 incident:** the Homepage `logview` widget does not exist
> (docs 404), and widget-only groups (`- Name: widget: ...`) crash the
> Homepage 1.13.2 services parser (`TypeError: b[c].forEach is not a
> function`), failing the whole `services.yaml`. See the comment header in
> `homepage/config/services.yaml`.

Caddy writes access logs to stdout inside the main site block of
`/srv/control-plane/caddy/Caddyfile`:

```
https://166.88.227.177 {
    log {
        output stdout
    }
    ...
}
```

Restart Caddy (the container has `admin off`, so `reload` is not
available) and read the logs:

```bash
ssh -p <ssh-port> root@166.88.227.177 'docker restart control-caddy'
ssh -p <ssh-port> root@166.88.227.177 'docker logs control-caddy'
```

If an interactive log viewer UI is wanted later, run a separate container
(e.g. Dozzle) behind a new Authelia-protected Caddy route — do not touch
`services.yaml`.

Notes:

- `docker.sock` in the homepage container is root-equivalent on the host.
  Keep the portal behind Authelia; do not expose it elsewhere.
- Logs are kept only as long as Docker retains the container output
  (`docker logs`). Add `logging: { driver: json-file, options: { max-size:
  "10m", max-file: "3" } }` to the caddy service in
  `/srv/control-plane/docker-compose.yml` to cap disk usage.

## File mapping

| Local path | VPS path | Container target |
|---|---|---|
| `docker-compose.yml` | `/srv/control-plane/docker-compose.yml` | — |
| `caddy/Caddyfile` | `/srv/control-plane/caddy/Caddyfile` | `/etc/caddy/Caddyfile` (ro) |
| `authelia/configuration.yml` | `/srv/control-plane/authelia/configuration.yml` | `/config/configuration.yml` |
| `authelia/users_database.yml` | `/srv/control-plane/authelia/users_database.yml` | `/config/users_database.yml` |
| `authelia/custom-css/theme.css` | `/srv/control-plane/authelia/custom-css/theme.css` | `/config/custom-css/theme.css` |
| `homepage/*.yaml` | `/srv/control-plane/homepage/*.yaml` | `/app/config/*.yaml` |
| `homepage/custom.{js,css}` | `/srv/control-plane/homepage/custom.{js,css}` | `/app/config/custom.{js,css}` |
| `landing/nginx.conf` | `/srv/control-plane/landing/nginx.conf` | `/etc/nginx/conf.d/default.conf` (ro) |

Note: the homepage container mounts the host `homepage/` dir to `/app/config`
inside the container. So `homepage/services.yaml` on host becomes
`/app/config/services.yaml` in the container. There is no `homepage/config/`
subdirectory on the host.

## First-time deployment

Secrets are NOT committed. Before `docker compose up`:

1. Copy the template:

   ```bash
   cp .env.example .env
   ```

2. Generate three 64-char hex secrets and paste into `.env`:

   ```bash
   openssl rand -hex 32  # → AUTHELIA_JWT_SECRET
   openssl rand -hex 32  # → AUTHELIA_SESSION_SECRET
   openssl rand -hex 32  # → AUTHELIA_STORAGE_ENCRYPTION_KEY
   ```

3. Set the admin password in `authelia/users_database.yml`. Generate an
   argon2id hash and replace the placeholder:

   ```bash
   docker run --rm -it authelia/authelia:4.39 authelia hash-password 'yourpassword'
   # paste the output (including $argon2id$...) into users_database.yml
   ```

4. Sync to the VPS and start:

   ```bash
   rsync -avz --exclude='.env' --exclude='authelia/db.sqlite3*' \
     ./ root@166.88.227.177:/srv/control-plane/
   ssh root@166.88.227.177 'cd /srv/control-plane && docker compose up -d'
   ```

> **Warning:** `AUTHELIA_STORAGE_ENCRYPTION_KEY` must be stable across
> restarts. Changing it invalidates all stored TOTP/2FA enrollments —
> users would need to re-enroll.

## What NOT to change here

- Do not add any Caddy site block on port `20128`.
- Do not change `9router` networking or port mapping.
- The HTTPS 9router endpoint is on `:8443`, reverse-proxied to the
  container's internal IP: `9router:20128`.
