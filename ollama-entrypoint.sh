#!/bin/bash

echo "Starting Ollama server..."
ollama serve &

# Wait until the server is ready
echo "Waiting for Ollama API to be available..."
until curl -s http://localhost:11434/api/tags > /dev/null; do
  sleep 1
done

echo "Pulling model 'mistral'..."
ollama pull mistral

echo "Ollama is ready with model 'mistral'. Keeping container alive."
tail -f /dev/null
