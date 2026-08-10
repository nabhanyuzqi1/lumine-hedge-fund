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
   scp -P <ssh-port> homepage/config/settings.yaml root@166.88.227.177:/srv/control-plane/homepage/config/settings.yaml
   ```

2. Restart the Homepage container so it regenerates its static HTML:

   ```bash
   ssh -p <ssh-port> root@166.88.227.177 'docker restart control-plane-homepage-1'
   ```

3. Hard-refresh the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`) and test a
   fresh Authelia login flow.

## Viewing Caddy logs in the portal

The portal shows live Caddy access logs via the Homepage `logview` widget
(docker source). Two configs are needed:

1. **Caddy writes access logs to stdout** — add inside the main site block
   of `/srv/control-plane/caddy/Caddyfile`:

   ```
   https://166.88.227.177 {
       log {
           output stdout
       }
       ...
   }
   ```

   Then restart Caddy (the container has `admin off`, so `reload` is not
   available):

   ```bash
   ssh -p <ssh-port> root@166.88.227.177 'docker restart control-plane-caddy-1'
   ```

   Verify: `docker logs control-plane-caddy-1` shows access lines.

2. **Homepage widget** — copy the config to the VPS and restart Homepage:

   ```bash
   scp -P <ssh-port> homepage/config/services.yaml root@166.88.227.177:/srv/control-plane/homepage/config/services.yaml
   ssh -p <ssh-port> root@166.88.227.177 'docker restart control-plane-homepage-1'
   ```

   The widget reads container logs through the docker socket that is
   already mounted `ro` into the homepage container. If the Caddy container
   name differs on the VPS, check it with `docker ps` and update
   `container:` in `services.yaml`.

Notes:

- No route or auth change is needed — the widget reads logs server-side via
  the docker API; nothing new is exposed publicly.
- `docker.sock` in the homepage container is root-equivalent on the host.
  Keep the portal behind Authelia; do not expose it elsewhere.
- Logs are kept only as long as Docker retains the container output
  (`docker logs`). Add `logging: { driver: json-file, options: { max-size:
  "10m", max-file: "3" } }` to the caddy service in
  `/srv/control-plane/docker-compose.yml` to cap disk usage.

## File mapping

| Local path | VPS path |
|---|---|
| `homepage/config/settings.yaml` | `/srv/control-plane/homepage/config/settings.yaml` |
| `homepage/config/services.yaml` | `/srv/control-plane/homepage/config/services.yaml` |

## What NOT to change here

- Do not add any Caddy site block on port `20128`.
- Do not change `9router` networking or port mapping.
- The HTTPS 9router endpoint is on `:8443`, reverse-proxied to the
  container's internal IP: `9router:20128`.
