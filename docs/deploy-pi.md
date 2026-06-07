# Deploying to Raspberry Pi 4 (MicroK8s)

The Garmin sync runs as an hourly CronJob in the `garmin` namespace and stores data
in the shared Postgres instance that already serves the ticket-tracker
(`mercadona` namespace, data on the USB drive at `/mnt/mercadona-data/postgres`).
Backups of the `garmin` database ride along with the existing ticket-tracker
backup script (Google Drive + secondary USB).

## Prerequisites

- MicroK8s running on the Pi (same cluster as ticket-tracker)
- Shared Postgres deployed in the `mercadona` namespace with the service renamed
  to `personal-data-db` (see the ticket-tracker repo, `k8s/postgres/service.yaml`)
- `kubectl` aliased to `microk8s kubectl` on the Pi (or use `microk8s kubectl` directly)
- DockerHub image `mimove/garmin-data-db:latest` built for `linux/arm64`
  (pushed automatically by the CD workflow on every push to `main`)

## 1. Rename the shared Postgres service (one-time, ticket-tracker repo)

The Postgres service is renamed from `postgres` to `personal-data-db` so it can
serve multiple data projects. From the ticket-tracker repo on the Pi:

```bash
# Delete the old service first — both claim NodePort 30432
microk8s kubectl delete svc postgres -n mercadona
microk8s kubectl apply -f k8s/postgres/service.yaml   # creates personal-data-db
microk8s kubectl apply -f k8s/ingestion/configmap.yaml  # POSTGRES_HOST updated

# Verify ticket-tracker still works after the rename
microk8s kubectl create job --from=cronjob/ticket-ingestion rename-check-$(date +%s) -n mercadona
```

## 2. Create the garmin database and user (one-time)

```bash
microk8s kubectl exec -it deployment/postgres -n mercadona -- \
  psql -U mercadona -c "CREATE USER garmin WITH PASSWORD '<strong-password>';" \
       -c "CREATE DATABASE garmin OWNER garmin;"
```

The sync applies `sql/schema.sql` on every run (all DDL is `IF NOT EXISTS`),
so no manual schema setup is needed.

## 3. Apply manifests

From this repo:

```bash
microk8s kubectl apply -f k8s/namespace.yaml

# Copy the example secret, fill in real values, then apply.
# NEVER commit the file with real credentials.
cp k8s/secret.example.yaml k8s/secret.yaml
# Edit k8s/secret.yaml:
#   GARMIN_EMAIL / GARMIN_PASSWORD — Garmin Connect credentials
#   POSTGRES_PASSWORD — the password chosen in step 2
microk8s kubectl apply -f k8s/secret.yaml

microk8s kubectl apply -f k8s/pvc.yaml
microk8s kubectl apply -f k8s/cronjob.yaml
```

## 4. Seed Garmin OAuth tokens

The first authentication may require MFA, which a headless CronJob cannot
answer. Seed tokens from your laptop (recommended):

```bash
# Run once locally to generate tokens (answers MFA interactively)
GARMINTOKENS=/tmp/garmin-tokens python -m src.main

# Copy tokens into the PVC via a temporary pod
microk8s kubectl run seed --image=busybox --restart=Never \
  --overrides='{"spec":{"volumes":[{"name":"t","persistentVolumeClaim":{"claimName":"garmin-tokens"}}],"containers":[{"name":"seed","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"t","mountPath":"/tokens"}]}]}}' \
  -n garmin
microk8s kubectl cp /tmp/garmin-tokens/. garmin/seed:/tokens/
microk8s kubectl delete pod seed -n garmin
```

If your account does not require MFA you can skip this — the first job
authenticates with `GARMIN_EMAIL`/`GARMIN_PASSWORD` and saves tokens to the
PVC automatically.

## 5. First run and the 2023 backfill

The CronJob runs hourly (`15 * * * *`, minute 15 to avoid the ticket-ingestion
job at minute 0). Each run:

- always re-syncs today, then
- backfills up to `MAX_DAYS_PER_RUN` (50) unsynced past days, newest-first,
  down to `BACKFILL_START` (2023-01-01).

The full backfill (~1,250 days) completes in ~25 hourly runs, i.e. about a day
of wall-clock time. Progress is tracked in the `sync_log` table, so runs are
resumable and idempotent. On a Garmin 429 rate limit the job exits cleanly and
the next hourly run resumes where it left off.

Trigger the first run immediately instead of waiting for the schedule:

```bash
microk8s kubectl create job --from=cronjob/garmin-sync manual-first-run -n garmin
microk8s kubectl logs -f job/manual-first-run -n garmin
```

## 6. Verify data is landing

```bash
microk8s kubectl exec -it deployment/postgres -n mercadona -- \
  psql -U garmin -d garmin -c \
  "SELECT count(*) AS days_synced, min(calendar_date), max(calendar_date) FROM sync_log;"

microk8s kubectl exec -it deployment/postgres -n mercadona -- \
  psql -U garmin -d garmin -c \
  "SELECT calendar_date, steps, resting_hr FROM daily_summary ORDER BY calendar_date DESC LIMIT 5;"
```

Re-run the `sync_log` query after a few hours — `days_synced` should grow by
~50 per run until the backfill reaches 2023-01-01.

## 7. Backups

The `garmin` database is dumped by the ticket-tracker backup script
(`scripts/backup.sh` in that repo), which already runs on the Pi host cron:

- Google Drive: `mimove14:garmin-backups/db/` (gzipped dumps, 5-week retention)
- Secondary USB: `/mnt/backup-usb/garmin-backups/db/` (rsync, same retention)

No additional setup needed beyond the updated script being in place.

## Scheduled operation

```bash
microk8s kubectl get cronjob -n garmin
microk8s kubectl get jobs -n garmin --sort-by=.metadata.creationTimestamp
```

## Troubleshooting

**Job fails with auth error:** tokens expired or PVC empty — re-seed (step 4).

**Job exits with code 1 mentioning 429:** Garmin rate limit. Expected during
backfill; the next hourly run resumes automatically.

**Cannot reach Postgres:** check the service rename (step 1) and that
`POSTGRES_HOST` in the secret is `personal-data-db.mercadona.svc.cluster.local`.
