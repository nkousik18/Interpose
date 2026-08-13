{{/*
Naming and labeling helpers -- the standard Helm chart pattern (`helm create`
scaffolds the same shape), plus this chart's Postgres/Redis embedded-vs-external DSN
assembly. See charts/interpose/README.md for the reasoning behind the embedded
defaults.
*/}}

{{- define "interpose.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "interpose.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "interpose.labels" -}}
app.kubernetes.io/name: {{ include "interpose.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "interpose.selectorLabels" -}}
app.kubernetes.io/name: {{ include "interpose.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "interpose.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "interpose.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "interpose.appSecretName" -}}
{{- if .Values.secrets.existingSecretName -}}
{{- .Values.secrets.existingSecretName -}}
{{- else -}}
{{- printf "%s-app" (include "interpose.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "interpose.postgresHost" -}}
{{- if .Values.postgres.embedded -}}
{{- printf "%s-postgres" (include "interpose.fullname" .) -}}
{{- else -}}
{{- required "postgres.host is required when postgres.embedded=false" .Values.postgres.host -}}
{{- end -}}
{{- end -}}

{{- define "interpose.postgresPort" -}}
{{- if .Values.postgres.embedded -}}
5432
{{- else -}}
{{- .Values.postgres.port | default 5432 -}}
{{- end -}}
{{- end -}}

{{- define "interpose.databaseUrl" -}}
{{- printf "postgresql+psycopg://%s:%s@%s:%s/%s" .Values.postgres.user .Values.postgres.password (include "interpose.postgresHost" .) (include "interpose.postgresPort" .) .Values.postgres.database -}}
{{- end -}}

{{- define "interpose.redisHost" -}}
{{- if .Values.redis.embedded -}}
{{- printf "%s-redis" (include "interpose.fullname" .) -}}
{{- else -}}
{{- required "redis.host is required when redis.embedded=false" .Values.redis.host -}}
{{- end -}}
{{- end -}}

{{- define "interpose.redisPort" -}}
{{- .Values.redis.port | default 6379 -}}
{{- end -}}

{{- define "interpose.redisUrl" -}}
{{- printf "redis://%s:%s/0" (include "interpose.redisHost" .) (include "interpose.redisPort" .) -}}
{{- end -}}

{{/*
OTel Collector OTLP gRPC endpoint the gateway's OTEL_EXPORTER_ENDPOINT points at.
otelCollector.enabled (in-cluster, chart-deployed collector) takes precedence over
otelExporterEndpoint (an operator-supplied external collector, e.g. a real production
deploy per Section 11.8's "bring your own backend") -- see values.yaml's comments on
both for the full embedded-vs-external reasoning, same pattern as Postgres/Redis.
Empty string (not used as an env var at all -- configmap-app.yaml only sets
OTEL_EXPORTER_ENDPOINT when this resolves non-empty) when neither is configured,
matching the app's own "unset means tracing/metrics setup is skipped entirely"
default (interpose.config.Settings.otel_exporter_endpoint).
*/}}
{{- define "interpose.otelExporterEndpoint" -}}
{{- if .Values.otelCollector.enabled -}}
{{- printf "http://%s-otel-collector:4317" (include "interpose.fullname" .) -}}
{{- else -}}
{{- .Values.otelExporterEndpoint -}}
{{- end -}}
{{- end -}}
