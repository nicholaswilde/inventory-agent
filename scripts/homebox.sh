#!/bin/bash

# Source environment variables if .env exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if ! command -v jq &> /dev/null; then
  echo "Error: jq is not installed. Please install jq to use this script."
  exit 1
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
    FILTER=${2:-"."}
    curl -s -H "$AUTH_HEADER" "${BASE_URL}/entities/${ID}" | jq "$FILTER"
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
  update-field)
    ID=$1
    FIELD_NAME=$2
    FIELD_VALUE=$3
    # Get current entity
    CURRENT=$(curl -s -H "$AUTH_HEADER" "${BASE_URL}/entities/${ID}")
    # Update or add the field using jq
    MERGED=$(echo "$CURRENT" | jq --arg name "$FIELD_NAME" --arg value "$FIELD_VALUE" '
      .fields = (.fields // []) |
      if any(.fields[]; .name == $name) then
        .fields |= map(if .name == $name then .value = $value | .textValue = $value else . end)
      else
        .fields += [{"name": $name, "type": "text", "value": $value}]
      end
    ')
    # Update entity
    curl -s -X PUT -H "$AUTH_HEADER" -H "$CONTENT_TYPE" -d "$MERGED" "${BASE_URL}/entities/${ID}"
    echo "Updated field '$FIELD_NAME' on entity $ID"
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
  delete)
    ID=$1
    curl -s -X DELETE -H "$AUTH_HEADER" "${BASE_URL}/entities/${ID}"
    echo "Deleted entity $ID"
    ;;
  attach)
    ID=$1
    FILE_PATH=$2
    FILE_NAME=$(basename "$FILE_PATH")
    curl -s -X POST -H "$AUTH_HEADER" -F "file=@${FILE_PATH}" -F "name=${FILE_NAME}" "${BASE_URL}/entities/${ID}/attachments"
    ;;
  search)
    QUERY=$1
    curl -s -H "$AUTH_HEADER" "${BASE_URL}/entities" | jq -r --arg q "$QUERY" '.items[] | select(.name | ascii_downcase | contains($q | ascii_downcase)) | "ID: \(.id) | Name: \(.name)"'
    ;;
  entity-types)
    curl -s -H "$AUTH_HEADER" "${BASE_URL}/entity-types" | jq -r '.[] | "ID: \(.id) | Name: \(.name)\(if .isLocation then " (Location)" else "" end)"'
    ;;
  *)
    echo "Usage: ./homebox.sh <list|get <id> [jq_filter]|update <id> <json_data>|update-field <id> <field_name> <field_value>|create <json_data>|delete <id>|attach <id> <file_path>|search <query>|entity-types>"
    exit 1
    ;;
esac
