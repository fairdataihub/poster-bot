# posterbot — portable local deploy convenience targets.
# Config is read from .env by docker compose automatically.
MODEL ?= llama3.2:3b
DUMP  ?= backup/posters.dump

.PHONY: up down logs restore pull-model health rebuild

up:                       ## build + start the stack, then pull the chat model
	docker compose up -d --build
	docker compose exec -T ollama ollama pull $(MODEL)
	@echo "stack up. Load data once with:  make restore DUMP=path/to/posters.dump"

restore:                  ## restore a transferred DB dump (DUMP=path)
	scripts/restore.sh $(DUMP)

pull-model:               ## pull a different chat model (MODEL=llama3.2:1b)
	docker compose exec -T ollama ollama pull $(MODEL)

health:                   ## check all three services
	@curl -s http://127.0.0.1:$${POSTERBOT_API_PORT:-8722}/healthz; echo

logs:                     ## tail logs
	docker compose logs -f --tail=50

down:                     ## stop the stack (data volumes persist)
	docker compose down

rebuild:                  ## rebuild the api image after code changes
	docker compose up -d --build api
