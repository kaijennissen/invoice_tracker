#!/bin/bash
# Quick & dirty invoice extraction script using Ollama

MODEL="ministral-3:14b"

PROMPT_VAR='Extract invoice data from this image. Be precise with dates (YYYY-MM-DD) and amounts (numeric only).'

# JSON schema for structured output (simplified - no anyOf patterns)
SCHEMA='{
    "type": "object",
    "properties": {
        "party": {"type": "string", "description": "Name of the invoicing party/company"},
        "invoice_id": {"type": "string", "description": "Unique invoice identifier"},
        "issue_date": {"type": "string", "format": "date", "description": "Date issued (YYYY-MM-DD)"},
        "due_date": {"type": "string", "format": "date", "description": "Payment due date (YYYY-MM-DD)"},
        "amount": {"type": "number", "description": "Total amount to pay"},
        "currency": {"type": "string", "description": "Currency code (EUR, USD, etc.)"},
        "recipient": {"type": "string", "description": "Person/entity being billed"}
    },
    "required": ["party", "invoice_id", "issue_date", "due_date", "amount", "currency", "recipient"]
}'

# Check for argument
if [ -z "$1" ]; then
    echo "Usage: $0 <image_file>"
    exit 1
fi

IMAGE_FILE="$1"

# Check if file exists
if [ ! -f "$IMAGE_FILE" ]; then
    echo "Error: File '$IMAGE_FILE' not found"
    exit 1
fi

# Convert image to base64
IMG=$(base64 < "$IMAGE_FILE" | tr -d '\n')

# Build JSON payload with jq (properly escapes newlines and special chars)
JSON_PAYLOAD=$(jq -n \
    --arg model "$MODEL" \
    --arg prompt "$PROMPT_VAR" \
    --arg img "$IMG" \
    --argjson schema "$SCHEMA" \
    '{
        model: $model,
        messages: [{
            role: "user",
            content: $prompt,
            images: [$img]
        }],
        stream: false,
        format: $schema
    }')

# Call Ollama API and extract formatted JSON result
curl -s -X POST http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" | jq -r '.message.content' | jq . 

