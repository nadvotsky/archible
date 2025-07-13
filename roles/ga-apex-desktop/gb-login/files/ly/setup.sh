#!/bin/sh

[ -f /etc/profile ] && . /etc/profile

exec "$@" >/dev/null
