# Cloud telemetry into the local Grafana

The Cloud Run service sends OpenTelemetry (traces, metrics, logs) over HTTPS to a free
Cloudflare quick tunnel, which forwards to the local OTel Collector. Dashboards are the same
ones as for local runs: filter by `deployment_environment = gcp`.

```
Cloud Run (4 containers) ──OTLP/HTTP + bearer token──► https://<random>.trycloudflare.com
   ──► cloudflared (your PC) ──► collector :4319 (token required) ──► Tempo / Prometheus / Loki ──► Grafana :3000
```

## Each time you want cloud telemetry

1. Start the stack: `docker compose -f observability/docker-compose.yml up -d`
2. Start the tunnel (prints a new URL each time):
   `cloudflared tunnel --url http://127.0.0.1:4319`
3. Redeploy so the service points at that URL:
   `TUNNEL_URL=https://<random>.trycloudflare.com bash deploy/gcp/deploy.sh`
4. Open Grafana at http://localhost:3000, set `deployment_environment = gcp`.

While the PC, Docker or the tunnel is off, the service keeps working; telemetry is dropped and
the export errors show in its logs.

## Notes

- The token is `OTEL_INGEST_TOKEN` in `observability/.env` (gitignored). Only the `:4319`
  receiver requires it; `:4318` stays open for local runs. Rotate it by changing the file,
  restarting the collector, and redeploying.
- `OTEL_TRACES_SAMPLER=always_on` is required on Cloud Run. Its front end sends a "not sampled"
  trace header, and the default sampler would then drop nearly all spans.
- The trace root shows "root span not yet received" in Tempo: the parent span lives at Google's
  front end. The trace itself is complete.
- Quick tunnels are for testing: no uptime guarantee, and the URL changes on restart.
