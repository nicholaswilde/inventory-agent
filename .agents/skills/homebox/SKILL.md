---
name: homebox
description: Interacts with the Homebox API using a local bash script to list, get, create, and update items/entities without using an MCP server.
---

# Homebox Skill

This skill allows agents to interact with the Homebox API using local bash scripts instead of an MCP server.

## Overview

The Homebox API provides endpoints to manage inventory items (entities). We use a bash script located at `scripts/homebox.sh` in the user's workspace to handle these interactions. 

## Requirements

1. **Credentials**: `HOMEBOX_IP` and `HOMEBOX_API_KEY` must be defined in the local `.env` file at the root of the workspace.
2. **Dependencies**: `curl` and `jq` must be installed on the system.

## Script Usage

The script is located at `scripts/homebox.sh` and supports the following commands:

### List Entities
Lists all entities, outputting their ID and Name.
```bash
./scripts/homebox.sh list
```

### Get Entity
Retrieves the full JSON object for a given entity ID.
```bash
./scripts/homebox.sh get <entity_id>
```

### Update Entity
Updates an entity with new data. The data should be provided as a JSON string. The script will fetch the current entity, merge the new fields, and send a PUT request to update it.
```bash
./scripts/homebox.sh update <entity_id> '{"name": "New Name", "quantity": 5}'
```

### Create Entity
Creates a new entity. The data should be provided as a JSON string.
```bash
./scripts/homebox.sh create '{"name": "New Entity", "description": "A description"}'
```

### Delete Entity
Deletes an entity by its ID.
```bash
./scripts/homebox.sh delete <entity_id>
```

### Attach File
Uploads a file (such as a photo) and attaches it to the specified entity.
```bash
./scripts/homebox.sh attach <entity_id> <file_path>
```

### List Entity Types
Lists all available entity types (e.g., Location, Asset), which is useful when creating a new entity to find the correct `entityTypeId`.
```bash
./scripts/homebox.sh entity-types
```

## Usage Guidelines for Agents

- **Querying**: Use the `list` command to find the ID of the entity you need to interact with.
- **Reading Data**: Use the `get` command to read current values (e.g., description, quantity) before making edits.
- **Editing**: Use the `update` command and provide only the fields you wish to update in the JSON string. The script handles merging.
- **API Information**: The Homebox service runs on port `7745` and uses standard Bearer token authentication. The script abstracts this connection logic away.
