# Kubernetes Operations Dashboard

A lightweight, dependency-free dashboard for operating an existing Kubernetes cluster. It uses the Kubernetes API through `kubectl` and the dashboard ServiceAccount; it does not depend on Prometheus, a database, or any cloud-provider API.

It works with conformant Kubernetes clusters. The cluster needs the Metrics API (`metrics-server`) only for live node and pod CPU/memory figures. All other pages work without it.

## Features

- Cluster namespaces and nodes, workload readiness, pod health, events, and live metrics.
- Sortable pods by name, phase, containers, age, CPU, memory, and restart count.
- Per-container logs, previous-container logs, time-range selection, and in-browser log search.
- Download the selected container log view as a timestamped `.log` file.
- Pod, workload, and node diagnostics, plus namespace quota/HPA/CronJob, PVC, Service, Ingress, and EndpointSlice views.
- Confirmation-gated rollout restarts for Deployments, StatefulSets, and DaemonSets; controller-managed pod restart.
- Local application login with `read` and `write` roles, plus Kubernetes RBAC restrictions.

## Security model

The dashboard is intentionally not an admin console: it has no shell/exec, YAML editor, secret access, or arbitrary deletion capability. Its ServiceAccount gets cluster-wide **read-only** access to node and namespace metadata. Workload reads and restart actions are granted only to explicitly selected namespaces unless `rbac.clusterWideActions` is enabled.

For production, put an internal HTTPS Ingress with your SSO/OIDC proxy in front of it. The optional built-in login is suitable for a controlled internal environment, but it is not a substitute for corporate identity management or per-user Kubernetes audit identities.

## Build

```bash
docker build --pull --no-cache --build-arg KUBECTL_VERSION=v1.37.0 -t ghcr.io/<your-org>/kubernetes-operations-dashboard:0.1.29 .
docker push ghcr.io/<your-org>/kubernetes-operations-dashboard:0.1.29
```

The image includes the `kubectl` version declared in the Dockerfile. Build with a client version compatible with the target cluster:

```bash
docker build --pull --no-cache --build-arg KUBECTL_VERSION=v<matching-cluster-version> -t <registry>/kubernetes-operations-dashboard:<tag> .
```

See [`chart/README.md`](chart/README.md) for Helm installation, RBAC, image-pull secrets, authentication, and ingress configuration.

## Local development

Run it only from a trusted machine with a restricted active kubeconfig:

```bash
python3 server.py
```

Then open `http://127.0.0.1:8787`. To use a non-default kubeconfig, set `KUBECONFIG`; do not expose this development server to a network.

## Before publishing

Do not commit private values files, kubeconfigs, registry credentials, passwords, or certificates. Review the RBAC permissions for your organization and select an appropriate open-source license before creating the public repository.
