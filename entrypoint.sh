#!/bin/sh
set -eu

# kubectl does not reliably select in-cluster configuration without an explicit
# kubeconfig. The tokenFile reference keeps using the projected, rotating token.
if [ -n "${KUBERNETES_SERVICE_HOST:-}" ] && [ -f /var/run/secrets/kubernetes.io/serviceaccount/token ]; then
  printf '%s\n' \
    'apiVersion: v1' \
    'kind: Config' \
    'clusters:' \
    '- name: in-cluster' \
    '  cluster:' \
    "    server: https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT_HTTPS:-443}" \
    '    certificate-authority: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt' \
    'users:' \
    '- name: dashboard' \
    '  user:' \
    '    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token' \
    'contexts:' \
    '- name: dashboard' \
    '  context:' \
    '    cluster: in-cluster' \
    '    user: dashboard' \
    'current-context: dashboard' > /tmp/kubeconfig
  export KUBECONFIG=/tmp/kubeconfig
fi
exec python server.py
