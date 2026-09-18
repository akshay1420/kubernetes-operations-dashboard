# Download kubectl in a separate stage.  Build-only tools never enter the
# runtime image.
ARG KUBECTL_VERSION=v1.37.0
ARG TARGETARCH
FROM python:3.11-slim-bookworm AS kubectl-download
ARG KUBECTL_VERSION
ARG TARGETARCH
WORKDIR /download
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && arch="${TARGETARCH:-amd64}" \
    && curl --fail --show-error --silent --location -o kubectl \
       "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl" \
    && curl --fail --show-error --silent --location -o kubectl.sha256 \
       "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl.sha256" \
    && echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check --strict \
    && chmod 0755 kubectl \
    && rm -rf /var/lib/apt/lists/*

# Pin the Debian family explicitly.  This avoids silently switching to a new
# Debian release when the floating python:3.11-slim tag changes.
FROM python:3.11-slim-bookworm
WORKDIR /app

COPY --from=kubectl-download /download/kubectl /usr/local/bin/kubectl
COPY server.py app.js auth.js overview.js resources.js applications.js capacity.js index.html login.html login.js styles.css entrypoint.sh ./
COPY history.py history.js experience.css ./
COPY changes.py changes.js ./
COPY namespace-scope.js ./
COPY view-preferences.js live-updates.js ./
COPY design-system.css ui-v4.js ./
COPY node-describe.js ./

# This application only uses the Python standard library. pip, setuptools,
# and wheel are build-time installers, so remove them from the runtime image.
RUN rm -rf /usr/local/lib/python3.11/site-packages/pip* \
           /usr/local/lib/python3.11/site-packages/setuptools* \
           /usr/local/lib/python3.11/site-packages/wheel* \
    && useradd --system --uid 10001 --no-create-home dashboard \
    && chmod 0755 /app/entrypoint.sh \
    && chown -R dashboard:dashboard /app

USER 10001
EXPOSE 8787
ENV K8S_DASHBOARD_HOST=0.0.0.0 \
    K8S_DASHBOARD_PORT=8787 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["./entrypoint.sh"]
