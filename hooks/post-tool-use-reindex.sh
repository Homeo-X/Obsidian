#!/usr/bin/env bash
# PostToolUse hook: re-index a file immediately after the agent writes it (opt-in).
# Wire this in .claude/settings.json:
#   "hooks": { "PostToolUse": [{ "matcher": "Edit|Write", "hooks": [{ "type": "command", "command": "bash hooks/post-tool-use-reindex.sh" }] }] }
#
# The hook receives the tool result on stdin as JSON.
# It extracts the file path and re-indexes it via `brain reindex <path>`.

set -euo pipefail

INPUT=$(cat)
# Extract file_path from the tool result JSON
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
path = data.get('file_path') or data.get('path') or ''
print(path)
" 2>/dev/null || true)

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Only re-index Markdown files inside the vault
if [[ "$FILE_PATH" != *.md ]]; then
    exit 0
fi

if command -v brain &>/dev/null; then
    brain reindex "$FILE_PATH" 2>&1 | head -5 || true
else
    uv run brain reindex "$FILE_PATH" 2>&1 | head -5 || true
fi
