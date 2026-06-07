# Raspberry Pi Deployment Design — Garmin Sync

Date: 2026-06-07

## Goal

Deploy the Garmin sync to the existing Raspberry Pi 4 (MicroK8s), mirroring the
ticket-tracker setup: data on USB, backups to Google Drive + secondary USB.
First run backfills everything from 2023; afterwards each run only syncs
missing data. Hourly cron so no run has to download whole days at once.

## Decisions

- **Same Pi, same USB drives** as ticket-tracker.
- **Shared Postgres instance** (ticket-tracker pod in `mercadona` namespace),
  new `garmin` database + `garmin` user. Low data volume now; full migration
  to a dedicated `personal-data` setup deferred.
- **Service rename only**: k8s Service `postgres` → `personal-data-db`
  (NodePort 30432 kept). Namespace `mercadona` stays for supermarket data;
  `garmin` namespace holds the sync CronJob. Future namespaces (consum, etc.)
  added later.
- **Backups**: extend ticket-tracker `scripts/backup.sh` to also dump the
  `garmin` DB → `mimove14:garmin-backups/db/` on Drive + `/mnt/backup-usb/garmin-backups/db/`
  on secondary USB, 5-week retention. Backup script migrates to a future
  merged-data repo.
- **CronJob**: hourly at minute 15 (`15 * * * *`) to avoid ticket-ingestion at
  minute 0. `BACKFILL_START=2023-01-01`, `MAX_DAYS_PER_RUN=50` →
  ~25 runs (~1 day) for the full backfill, tracked in `sync_log`, resumable on
  429 rate limits. No code changes needed — backfill logic already exists.

## Changes

### garmin-data-db
- `k8s/cronjob.yaml`: hourly schedule, `BACKFILL_START=2023-01-01`
- `k8s/secret.example.yaml`: `POSTGRES_HOST=personal-data-db.mercadona.svc.cluster.local`
- `docs/deploy-pi.md`: full Pi deployment guide
- `README.md`: schedule references updated

### ticket-tracker-claude
- `k8s/postgres/service.yaml`: rename `postgres` → `personal-data-db`
- `k8s/ingestion/configmap.yaml`: `POSTGRES_HOST=personal-data-db`
- `scripts/backup.sh`: garmin DB dump + upload + retention; fixed pre-existing
  bug where `rsync --delete` wiped older USB dumps (USB retention never worked)

## Out of scope

- Full namespace refactor (`personal-data` namespace, Postgres migration)
- Dedicated Postgres instance for garmin
- Merged-data repo (notebooks + backups) — future work
