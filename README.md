# Langgraph project
Runs a langgraph project
uses a AWS agent core runner
but
- uses langgraph short term memory (checkpointer) with an AWS postgres implementation
- uses langgraph long term memory with an AWS postgres implementation
- Human in the loop with langgraph interrupts in branch feature/human_in_the_loop

the repo is in tutorial style
- step 1: initial - 101 agent
- step 2: feature/human_in_the_loop - added human in the loop interrupt resume or cancel
  step 3: feature/long_term_memory - added long term memory
- step 4: feature/realy_long_term_memory / master use postgres for store checkpoints and memory store
## Install

```bash
poetry shell
poetry install
```

## Observability with datadog
bring up datadog agent and postgres for stores
```bash
docker-compose up
```

## Run
```bash
poetry run ddtrace-run python langgraph_bedrock.py
```

## Invoke the agent
```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "book me an excursion",
        "thread_id": "fc6faede-87f7-4e91-a172-eacd7230d405",
        "user_id": "darthShana"
      }'
```

## Resume after interrupt
Confirm booking
```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
        "command": "confirm",
        "thread_id": "fc6faede-87f7-4e91-a172-eacd7230d405",
        "user_id": "darthShana"
      }'
```
Abort booking
```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
        "command": "cancel",
        "thread_id": "fc6faede-87f7-4e91-a172-eacd7230d405",
        "user_id": "darthShana"
      }'
```
Feedback to booking Agent
```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
        "command": "feedback",
        "feedback": "i have a cold and i dont want to go diving",
        "thread_id": "fc6faede-87f7-4e91-a172-eacd7230d405",
        "user_id": "darthShana"
      }'
```