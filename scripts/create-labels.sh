#!/usr/bin/env bash
# Create the gxy-tool-bot labels in a repository.
#
# Usage: scripts/create-labels.sh [owner/repo]
#   Defaults to the repo containing the current directory (gh repo view).
#
# Idempotent: --force updates existing labels, so re-running is safe and can
# be used to fix colors/descriptions after edits.
#
# The workflow templates dual-match these prefixed names and the original
# unprefixed names, so deployments that already have the old labels do not
# need to recreate them. If you want the old names too, create them via the
# GitHub UI or uncomment the LEGACY block at the bottom.
set -euo pipefail

REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
echo "Creating tool-bot:* labels in $REPO"

create() {
    gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force
}

create "tool-bot:tool-request"       "0075ca" "Applied automatically by issue template; triggers planning"
create "tool-bot:tool-update"        "0075ca" "Applied automatically by the Tool Update issue template; triggers update planning"
create "tool-bot:plan-ready"         "a2eeef" "Applied by bot after plan is posted"
create "tool-bot:ready-to-implement" "0e8a16" "Applied by maintainer to approve plan; triggers generation"
create "tool-bot:pr-opened"          "1d76db" "Applied by bot after PR is created"
create "tool-bot:generation-failed"  "b60205" "Applied by bot if generation or planning fails"
create "tool-bot:retry-plan"         "fbca04" "Applied by user/maintainer to re-trigger planning after a failure"
create "tool-bot:retry-generate"     "fbca04" "Applied by user/maintainer to re-trigger generation after a failure"
create "tool-bot:address-feedback"   "5319e7" "Applied to a PR to have the bot address review comments and CI failures"
create "tool-bot:review"             "bfd4f2" "Applied to a PR to have the bot review tool files and post findings"

# Legacy unprefixed names (still matched by the workflow templates) — uncomment
# if you're migrating an existing deployment rather than starting fresh:
# create "tool-request"       "0075ca" "Legacy alias of tool-bot:tool-request"
# create "tool-update"        "0075ca" "Legacy alias of tool-bot:tool-update"
# create "plan-ready"         "a2eeef" "Legacy alias of tool-bot:plan-ready"
# create "ready-to-implement" "0e8a16" "Legacy alias of tool-bot:ready-to-implement"
# create "pr-opened"          "1d76db" "Legacy alias of tool-bot:pr-opened"
# create "generation-failed"  "b60205" "Legacy alias of tool-bot:generation-failed"
# create "retry-plan"         "fbca04" "Legacy alias of tool-bot:retry-plan"
# create "retry-generate"     "fbca04" "Legacy alias of tool-bot:retry-generate"
# create "address-feedback"   "5319e7" "Legacy alias of tool-bot:address-feedback"
# create "review"             "bfd4f2" "Legacy alias of tool-bot:review"

echo "Done — labels created/updated in $REPO"
