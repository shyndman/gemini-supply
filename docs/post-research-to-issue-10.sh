#!/bin/bash
# Script to post the research findings as a comment on Issue #10
# This script requires GITHUB_TOKEN to be set in the environment

set -e

OWNER="shyndman"
REPO="generative-supply"
ISSUE_NUMBER="10"
COMMENT_FILE="docs/telegram-image-display-research.md"

echo "Posting research findings to Issue #10..."
echo ""

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Error: GITHUB_TOKEN environment variable is not set"
  echo ""
  echo "To post this comment, you can either:"
  echo "1. Set GITHUB_TOKEN and run this script:"
  echo "   export GITHUB_TOKEN=your_token_here"
  echo "   ./docs/post-research-to-issue-10.sh"
  echo ""
  echo "2. Use GitHub CLI directly:"
  echo "   gh issue comment 10 --body-file $COMMENT_FILE"
  echo ""
  echo "3. Manually copy the content from $COMMENT_FILE"
  echo "   and post it as a comment on:"
  echo "   https://github.com/$OWNER/$REPO/issues/$ISSUE_NUMBER"
  exit 1
fi

# Create JSON payload
COMMENT_JSON=$(jq -Rs '{"body": .}' < "$COMMENT_FILE")

# Post the comment using GitHub API
API_URL="https://api.github.com/repos/$OWNER/$REPO/issues/$ISSUE_NUMBER/comments"

RESPONSE=$(curl -s -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "$API_URL" \
  -d "$COMMENT_JSON")

# Check if successful
if echo "$RESPONSE" | jq -e '.id' > /dev/null 2>&1; then
  COMMENT_URL=$(echo "$RESPONSE" | jq -r '.html_url')
  echo "✅ Comment posted successfully!"
  echo "View at: $COMMENT_URL"
else
  echo "❌ Failed to post comment"
  echo "Response: $RESPONSE"
  exit 1
fi
