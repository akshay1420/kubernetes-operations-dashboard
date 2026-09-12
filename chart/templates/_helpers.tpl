{{- define "kubernetes-operations-dashboard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "kubernetes-operations-dashboard.fullname" -}}
{{- if .Values.fullnameOverride -}}{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if contains (include "kubernetes-operations-dashboard.name" .) .Release.Name -}}{{ .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else -}}{{ printf "%s-%s" .Release.Name (include "kubernetes-operations-dashboard.name" .) | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- end }}
{{- define "kubernetes-operations-dashboard.serviceAccountName" -}}{{ default (include "kubernetes-operations-dashboard.fullname" .) .Values.serviceAccount.name }}{{- end }}
{{- define "kubernetes-operations-dashboard.authSecretName" -}}{{ default .Values.auth.secretName .Values.auth.existingSecret }}{{- end }}
