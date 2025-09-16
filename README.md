# Langgraph project
Runs a langgraph project
uses a AWS agent core runner
but
- uses langgraph short term memory (checkpointer) with an AWS postgres implementation
- uses langgraph long term memory with an AWS postgres implementation
- Human in the loop with langgraph interrupts

## Install

```bash
poetry shell
poetry install
```

## Observability with datadog

```bash
docker run -d --name dd-agent \                   
  -e DD_API_KEY=DD_API_KEY \
  -e DD_SITE="ap2.datadoghq.com" \
  -e DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true \
  -e DD_APM_ENABLED=true \
  -e DD_APM_NON_LOCAL_TRAFFIC=true \
  -e DD_APM_RECEIVER_SOCKET=/var/run/datadog/apm.socket \
  -e DD_DOGSTATSD_SOCKET=/var/run/datadog/dsd.socket \
  -v /var/run/datadog:/var/run/datadog \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /proc/:/host/proc/:ro \
  -v /sys/fs/cgroup/:/host/sys/fs/cgroup:ro \
  -v /var/lib/docker/containers:/var/lib/docker/containers:ro \
  -p 8126:8126 \
  -p 8125:8125/udp \
  gcr.io/datadoghq/agent:7
```

## Run
```bash
poetry run ddtrace-run python langgraph_bedrock.py
```
