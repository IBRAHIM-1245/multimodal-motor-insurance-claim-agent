#!/bin/bash
# Start n8n inside GitHub Codespaces
# WEBHOOK_URL: public Codespaces address, so forms and webhooks get the right links
# N8N_PROXY_HOPS=1: tells n8n it runs behind the Codespaces proxy
export WEBHOOK_URL="https://${CODESPACE_NAME}-5678.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/"
export N8N_PROXY_HOPS=1
n8n start
