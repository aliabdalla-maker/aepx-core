# One-off database setup for the hosted IDE: creates the runtime and Keycloak roles and
# applies backend/migrations in order, once each. Build context: platform/saas-ide.
FROM pgvector/pgvector:pg16
COPY backend/migrations /migrations
COPY infra/production/migrate.sh /usr/local/bin/aepx-migrate
RUN chmod 0755 /usr/local/bin/aepx-migrate
ENTRYPOINT ["/usr/local/bin/aepx-migrate"]
