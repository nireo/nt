#!/bin/bash

SOURCE_PATH="$(pwd)/nt.py"
DEST_PATH="$HOME/.local/bin/nt"

rm -f "$DEST_PATH"
ln -s "$SOURCE_PATH" "$DEST_PATH"
chmod +x "$SOURCE_PATH"

echo "symlink created: $DEST_PATH -> $SOURCE_PATH"
