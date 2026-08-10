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

## File mapping

| Local path | VPS path |
|---|---|
| `homepage/config/settings.yaml` | `/srv/control-plane/homepage/config/settings.yaml` |

## What NOT to change here

- Do not add any Caddy site block on port `20128`.
- Do not change `9router` networking or port mapping.
- The HTTPS 9router endpoint is on `:8443`, reverse-proxied to the
  container's internal IP: `9router:20128`.
