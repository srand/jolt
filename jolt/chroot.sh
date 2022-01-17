#!/bin/sh

die() {
    echo "error: $@" > /dev/stderr
    exit 1
}

export JOLTCHROOT=$1
shift

[ -z "$JOLTCHROOT" ] && die "root directory argument is missing"
[ -z "$JOLTDIR" ] && die "JOLTDIR environment variable is not set"
[ -z "$JOLTCACHEDIR" ] && die "JOLTCACHEDIR environment variable is not set"

mkdir -p $JOLTCHROOT/$JOLTDIR
mkdir -p $JOLTCHROOT/$JOLTCACHEDIR
mount --rbind $JOLTDIR $JOLTCHROOT/$JOLTDIR
mount --rbind $JOLTCACHEDIR $JOLTCHROOT/$JOLTCACHEDIR

chroot $JOLTCHROOT "$@"
