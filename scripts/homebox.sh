#!/bin/bash

# Source environment variables if .env exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ -z "$HOMEBOX_IP" ] || [ -z "$HOMEBOX_API_KEY" ]; then
  echo "Error: HOMEBOX_IP or HOMEBOX_API_KEY not set"
  exit 1
fi

BASE_URL="http://${HOMEBOX_IP}:7745/api/v1"
AUTH_HEADER="Authorization: Bearer ${HOMEBOX_API_KEY}"
CONTENT_TYPE="Content-Type: application/json"

CMD=$1
shift

case "$CMD" in
  list)
    curl -s -H "$AUTH_HEADER" "${BASE_URL}/entities" | jq -r '.items[] | "ID: \(.id) | Name: \(.name)"'
    ;;
  get)
    ID=$1
    curl -s -H "$AUTH_HEADER" "${BASE_URL}/entities/${ID}" | jq .
    ;;
  update)
    ID=$1
    DATA=$2
    # Get current entity
    CURRENT=$(curl -s -H "$AUTH_HEADER" "${BASE_URL}/entities/${ID}")
    # Merge DATA into CURRENT using jq
    MERGED=$(echo "$CURRENT" | jq --argjson patch "$DATA" '. + $patch')
    # Update entity
    curl -s -X PUT -H "$AUTH_HEADER" -H "$CONTENT_TYPE" -d "$MERGED" "${BASE_URL}/entities/${ID}"
    echo "Updated entity $ID"
    ;;
  create)
    RAW_DATA=$1
    DATA=$(echo "$RAW_DATA" | jq '
      .fields = (.fields // [])
      | if .manufacturer then .fields += [{"name": "Manufacturer", "type": "text", "value": .manufacturer}] | del(.manufacturer) else . end
      | if .Manufacturer then .fields += [{"name": "Manufacturer", "type": "text", "value": .Manufacturer}] | del(.Manufacturer) else . end
      | if .modelNumber then .fields += [{"name": "Model Number", "type": "text", "value": .modelNumber}] | del(.modelNumber) else . end
      | if .model_number then .fields += [{"name": "Model Number", "type": "text", "value": .model_number}] | del(.model_number) else . end
      | if ."Model Number" then .fields += [{"name": "Model Number", "type": "text", "value": ."Model Number"}] | del(."Model Number") else . end
      | if .notes then .fields += [{"name": "Notes", "type": "text", "value": .notes}] | del(.notes) else . end
      | if .Notes then .fields += [{"name": "Notes", "type": "text", "value": .Notes}] | del(.Notes) else . end
    ')
    curl -s -X POST -H "$AUTH_HEADER" -H "$CONTENT_TYPE" -d "$DATA" "${BASE_URL}/entities"
    ;;
  attach)
    ID=$1
    FILE_PATH=$2
    FILE_NAME=$(basename "$FILE_PATH")
    curl -s -X POST -H "$AUTH_HEADER" -F "file=@${FILE_PATH}" -F "name=${FILE_NAME}" "${BASE_URL}/entities/${ID}/attachments"
    ;;
  *)
    echo "Usage: ./homebox.sh <list|get <id>|update <id> <json_data>|create <json_data>|attach <id> <file_path>>"
    exit 1
    ;;
esac
