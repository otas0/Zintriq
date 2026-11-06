#!/bin/sh
# Local test signing only. This is not a Developer ID or notarized signature.
set -e
APP="$1"
if [ -z "$APP" ]; then
  echo "usage: sign_macos_adhoc.sh /path/to/Zintriq Studio.app" >&2
  exit 2
fi
codesign --force --deep --sign - "$APP"
codesign --verify --verbose=2 "$APP"
echo "ad-hoc signature verified for local testing: $APP"
