# Jenkins with the Docker CLI baked in, so pipeline stages can run
# `docker build` / `docker compose` against the host's daemon via the
# mounted socket (docker-compose.jenkins.yml). The stock jenkins/jenkins
# image has no Docker CLI at all — without this, every pipeline run would
# need to reinstall it, which is slow and fragile.
FROM jenkins/jenkins:lts-jdk17

USER root

# Docker CLI + compose plugin only — NOT a nested dockerd (Docker-in-Docker).
# This container talks to the HOST's Docker daemon via the socket mounted
# in docker-compose.jenkins.yml, which means Jenkins effectively has
# root-equivalent control of the host. That is unavoidable for a Jenkins
# instance whose job is to build/test Docker images — the tradeoff to
# manage is keeping Jenkins itself authenticated and not exposed publicly,
# not avoiding the socket mount.
# python3/pip3 run lint+test stages directly in this image rather than via
# nested `docker run` containers: Jenkins only has the HOST's docker.sock
# (Docker-outside-of-Docker), so any runtime bind-mount issued from inside
# a nested container would resolve against the wrong filesystem. `docker
# build`/`docker compose build` are fine to run via the socket (a build
# context is streamed to the daemon, not bind-mounted) — only running
# containers with volume mounts hits this problem, so lint/test stay native.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg lsb-release python3 python3-pip python3-venv \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Pre-install the plugins the Jenkinsfile needs so the first pipeline run
# doesn't stall on a plugin-install prompt.
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

USER jenkins
