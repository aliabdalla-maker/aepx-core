# PostgreSQL backup restore rehearsal

**Never test restoration against the live production database.** First use `deploy/oci/backup-postgres.sh` on the OCI VM, then transfer the backup to encrypted off-host storage.

On a separate isolated test host, start a **new, empty** PostgreSQL 16 + pgvector database and restore the SQL dump:

```bash
gzip -t aepx-YYYYMMDDTHHMMSSZ.sql.gz
sha256sum -c aepx-YYYYMMDDTHHMMSSZ.sql.gz.sha256
# Use a dedicated test container and unique port; never the production volume.
docker run -d --name aepx-restore-test -e POSTGRES_PASSWORD=temporary_restore_password -e POSTGRES_DB=aepx -e POSTGRES_USER=aepx pgvector/pgvector:pg16
until docker exec aepx-restore-test pg_isready -U aepx; do sleep 2; done
gzip -dc aepx-YYYYMMDDTHHMMSSZ.sql.gz | docker exec -i aepx-restore-test psql -v ON_ERROR_STOP=1 -U aepx -d aepx
docker exec aepx-restore-test psql -U aepx -d aepx -c '\\dt'
docker rm -f aepx-restore-test
```

Check application-specific row counts, extensions, schema version and expected data integrity before declaring the backup verified. This example uses a temporary password only on an isolated test host. Delete any temporary credentials and restore artifacts after the rehearsal.
