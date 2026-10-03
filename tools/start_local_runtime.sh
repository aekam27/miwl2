#!/bin/sh
set -eu
miwl_project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$miwl_project_dir/.runtime/models"
export OLLAMA_NO_CLOUD=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_CONTEXT_LENGTH=4096
exec "$miwl_project_dir/.runtime/Ollama.app/Contents/Resources/ollama" serve
