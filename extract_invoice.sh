#!/bin/bash
# Quick & dirty invoice extraction script using Ollama

MODEL="ministral-3:14b"

PROMPT_VAR='Extract invoice data from this image. Be precise with:
- Dates: use ISO format YYYY-MM-DD
- Amounts: numeric value only (no currency symbols)
- If a field cannot be determined, use "UNKNOWN" for text fields.

Return JSON with these fields:
- party: Name of the invoicing party/company
- invoice_id: Unique invoice identifier
- issue_date: Date the invoice was issued (YYYY-MM-DD)
- due_date: Payment due date (YYYY-MM-DD)
- amount: Total amount to pay (numeric only)
- currency: Currency code (default EUR if not specified)
- recipient: Person/entity the invoice is addressed to'

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
    '{
        model: $model,
        messages: [{
            role: "user",
            content: $prompt,
            images: [$img]
        }],
        stream: false,
        format: "json"
    }')

# Call Ollama API and extract formatted JSON result
curl -s -X POST http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" | jq -r '.message.content' | jq . 

