#!/bin/bash
# Open the LOCAL ChatGPT-style sidebar mock (an offline HTML file, NOT chatgpt.com)
# in a Chrome/Chromium --app window titled "ChatGPT" on $DISPLAY.
# Usage: demo/open-mock.sh            -> normal page
#        demo/open-mock.sh drift      -> confirmation button renamed/moved (drift test)
set -e
export DISPLAY="${DISPLAY:-:0}"
DIR="$(cd "$(dirname "$0")/chatgpt-sidebar" && pwd)"
URL="file://${DIR}/index.html"
[[ "${1:-}" == drift ]] && URL="${URL}?drift=1"
PROFILE="${AFTERIMAGE_MOCK_PROFILE:-/tmp/afterimage-mock-profile}"
BROWSER="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
pkill -f "user-data-dir=${PROFILE}" 2>/dev/null || true
sleep 0.5; rm -rf "$PROFILE"; mkdir -p "$PROFILE"
nohup "$BROWSER" --user-data-dir="$PROFILE" --no-first-run --no-default-browser-check \
  --app="$URL" --window-position=280,70 --window-size=1320,900 >/dev/null 2>&1 &
for _ in $(seq 1 25); do
  if xdotool search --name '^ChatGPT$' >/dev/null 2>&1; then
    WID=$(xdotool search --name '^ChatGPT$' | head -1)
    echo "pid=$(xdotool getwindowpid "$WID") window_id=$WID"
    exit 0
  fi
  sleep 0.3
done
echo "mock window did not open" >&2; exit 1
