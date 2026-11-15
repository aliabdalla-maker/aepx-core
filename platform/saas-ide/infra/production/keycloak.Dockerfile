# Keycloak for the hosted IDE: the aepx realm (email sign-up, browser client with PKCE)
# is imported on first start and left alone afterwards, so users and settings survive
# restarts. Build context: platform/saas-ide.
FROM quay.io/keycloak/keycloak:26.0.7 AS builder
ENV KC_DB=postgres KC_HEALTH_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.0.7
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY --chown=keycloak:keycloak infra/production/aepx-realm.json /opt/keycloak/data/import/aepx-realm.json
COPY --chown=keycloak:keycloak --chmod=0755 infra/production/keycloak-setup.sh /opt/keycloak/bin/aepx-keycloak-setup.sh
COPY --chown=keycloak:keycloak --chmod=0755 infra/production/keycloak-start.sh /opt/keycloak/bin/aepx-keycloak-start.sh
ENTRYPOINT ["/opt/keycloak/bin/aepx-keycloak-start.sh"]
