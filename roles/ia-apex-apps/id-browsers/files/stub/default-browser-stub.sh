#!/usr/bin/env bash

if [[ -n "$WAYLAND_SOCKET" ]] && [[ -n "$WAYLAND_DISPLAY" ]]; then
	wl-copy "$1"
else
	echo -n "$1" | xsel -b
fi

notify-send \
	--appname="Default Application Stub" \
	--icon=applications-internet \
	--urgency=low \
	"Clicked link has been copied to the clipboard" \
	"$1"
