#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGES_DIR="${REPO_ROOT}/terraform/packages"

echo "Creating Lambda deployment packages..."
mkdir -p "${PACKAGES_DIR}"

# Package Slack notifier
cd "${REPO_ROOT}/src/slack_notifier"
zip -FS "${PACKAGES_DIR}/slack_notifier.zip" lambda_function.py

# Package sample application
cd "${REPO_ROOT}/src/sample_app"
zip -FS "${PACKAGES_DIR}/sample_app.zip" lambda_function.py

echo "Done. Packages written to ${PACKAGES_DIR}"
