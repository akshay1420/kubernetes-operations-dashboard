# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected security problem. Report it privately to the repository maintainers, including reproduction steps, affected version, and any relevant logs with credentials removed.

## Deployment guidance

Deploy behind HTTPS and an organization-approved identity provider or authentication proxy. Keep built-in credentials in a Secret or external secret manager, scope `rbac.allowedNamespaces` to the smallest required set, and review the rendered RBAC before each installation.

The dashboard deliberately does not provide shell access, secret viewing, arbitrary YAML editing, or uncontrolled deletion. Treat users with the `write` role and the dashboard ServiceAccount as operationally privileged.
