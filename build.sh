#!/bin/sh

export APP_ID="$(jq -r '.applications.gecko.id' ./manifest.json)"
export NAME="tab_control"
export DESC="Host for tab control"
export BIN_PATH="/usr/local/bin/tab_control.py"
export TYPE="stdio"

# build extension
7z a \
    "$APP_ID.xpi" \
    -tzip \
    ./manifest.json \
    ./bg

# build native messaging host
jq -Rn '{
    name: env.NAME,
    description: env.DESC,
    path: env.BIN_PATH,
    type: env.TYPE,
    allowed_extensions: [env.APP_ID]
}' > "$NAME.json"
