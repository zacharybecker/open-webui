#!/bin/bash

# Simple Confluence to Open WebUI Sync Runner

set -e

echo "🚀 Starting Confluence sync..."

# Check if required arguments are provided
if [ $# -lt 3 ]; then
    echo "Usage:"
    echo "  List spaces: $0 --list-spaces <confluence-url> <username> <token>"
    echo "  Sync space:  $0 <space-key> <openwebui-url> <api-key> <confluence-url> <username> <token> [knowledge-base-name] [description] [force-refresh]"
    echo "  Sync spaces: $0 --spaces \"SPACE1,SPACE2\" <openwebui-url> <api-key> <confluence-url> <username> <token>"
    echo ""
    echo "Examples:"
    echo "  $0 --list-spaces https://company.atlassian.net user@company.com token123"
    echo "  $0 MYSPACE http://localhost:3000 my-api-key https://company.atlassian.net user@company.com token123"
    echo "  $0 --spaces \"DOCS,PROJ\" http://localhost:3000 my-api-key https://company.atlassian.net user@company.com token123"
    exit 1
fi

# Handle list-spaces command
if [ "$1" = "--list-spaces" ]; then
    if [ $# -ne 4 ]; then
        echo "Usage: $0 --list-spaces <confluence-url> <username> <token>"
        exit 1
    fi

    CONFLUENCE_URL=$2
    USERNAME=$3
    TOKEN=$4

    python confluence_sync.py \
        --list-spaces \
        --confluence-url "$CONFLUENCE_URL" \
        --confluence-username "$USERNAME" \
        --confluence-token "$TOKEN"
    exit 0
fi

# Handle spaces command
if [ "$1" = "--spaces" ]; then
    if [ $# -lt 7 ]; then
        echo "Usage: $0 --spaces \"SPACE1,SPACE2\" <openwebui-url> <api-key> <confluence-url> <username> <token>"
        exit 1
    fi

    SPACES=$2
    OPENWEBUI_URL=$3
    API_KEY=$4
    CONFLUENCE_URL=$5
    USERNAME=$6
    TOKEN=$7
    KB_NAME=${8:-"Confluence-Multiple"}
    DESCRIPTION=${9:-"Synced from multiple Confluence spaces"}
    FORCE_REFRESH=${10:-false}

    CMD="python confluence_sync.py \
        --spaces \"$SPACES\" \
        --openwebui-url \"$OPENWEBUI_URL\" \
        --api-key \"$API_KEY\" \
        --confluence-url \"$CONFLUENCE_URL\" \
        --confluence-username \"$USERNAME\" \
        --confluence-token \"$TOKEN\" \
        --knowledge-base-name \"$KB_NAME\" \
        --description \"$DESCRIPTION\""

    if [ "$FORCE_REFRESH" = "true" ]; then
        CMD="$CMD --force-refresh"
    fi

    echo "📋 Configuration:"
    echo "  Spaces: $SPACES"
    echo "  Open WebUI: $OPENWEBUI_URL"
    echo "  Knowledge Base: $KB_NAME"
    echo ""

    eval $CMD
    exit 0
fi

# Handle single space sync (original format)
if [ $# -lt 6 ]; then
    echo "Usage: $0 <space-key> <openwebui-url> <api-key> <confluence-url> <username> <token> [knowledge-base-name] [description] [force-refresh]"
    exit 1
fi

SPACE_KEY=$1
OPENWEBUI_URL=$2
API_KEY=$3
CONFLUENCE_URL=$4
USERNAME=$5
TOKEN=$6
KB_NAME=${7:-"Confluence-$SPACE_KEY"}
DESCRIPTION=${8:-"Synced from Confluence space $SPACE_KEY"}
FORCE_REFRESH=${9:-false}

CMD="python confluence_sync.py \
    --space-key \"$SPACE_KEY\" \
    --openwebui-url \"$OPENWEBUI_URL\" \
    --api-key \"$API_KEY\" \
    --confluence-url \"$CONFLUENCE_URL\" \
    --confluence-username \"$USERNAME\" \
    --confluence-token \"$TOKEN\" \
    --knowledge-base-name \"$KB_NAME\" \
    --description \"$DESCRIPTION\""

if [ "$FORCE_REFRESH" = "true" ]; then
    CMD="$CMD --force-refresh"
fi

echo "📋 Configuration:"
echo "  Space: $SPACE_KEY"
echo "  Open WebUI: $OPENWEBUI_URL"
echo "  Knowledge Base: $KB_NAME"
echo ""

eval $CMD