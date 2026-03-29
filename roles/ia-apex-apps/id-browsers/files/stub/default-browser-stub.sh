#!/usr/bin/env bash

if [[ -n "$WAYLAND_DISPLAY" ]]; then
	wl-copy "$1"
else
	printf '%s' "$1" | xsel -b
fi

notify-send \
	--app-name="Default Browser Stub" \
	--icon=applications-internet \
	--urgency=low \
	"The clicked link has been copied to the clipboard" \
	"$1"
