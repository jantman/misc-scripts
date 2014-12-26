#!/bin/bash
#
# Script to rebuild a SRPM 1:1, useful when you want to build a RHEL/CentOS 6
# SRPM on a RHEL/CentOS 5 system that doesn't support newer compression (cpio: MD5 sum mismatch)
#
# Copyright 2014 Jason Antman <jason@jasonantman.com>. All Rights Reserved.
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script will always live at:
# <https://github.com/jantman/misc-scripts/blob/master/rebuild_srpm.sh>
#

if [[ -z "$1" || "$1" == "-h" || "$1" == "--help" ]]
then
    echo "USAGE: rebuild_srpm.sh <srpm> <output directory>"
    exit 1
fi

if [[ -z "$2" ]]
then
    OUTDIR=`pwd`
else
    OUTDIR="$2"
fi

if [[ ! -e "$1" ]]
then
    echo "ERROR: SRPM file not found: $1"
    exit 1
fi

if ! which rpmbuild &> /dev/null
then
    echo "rpmbuild could not be found. please install. (sudo yum install rpm-build)"
    exit 1
fi

if ! which rpm2cpio &> /dev/null
then
    echo "rpm2cpio could not be found. please install. (sudo yum install rpm)"
    exit 1
fi

SRPM=`dirname "$1"`"/"`basename "$1"`
TEMPDIR=`mktemp -d`
STARTPWD=`pwd`

echo "Rebuilding $SRPM..."

# copy srpm into tempdir
cp $SRPM $TEMPDIR

pushd $TEMPDIR &>/dev/null

# setup local build dir structure
mkdir -p rpm rpm/BUILD rpm/RPMS rpm/SOURCES rpm/SPECS rpm/SRPMS rpm/RPMS/athlon rpm/RPMS/i\[3456\]86 rpm/RPMS/i386 rpm/RPMS/noarch rpm/RPMS/x86_64

# setup rpmmacros file
cat /dev/null > $TEMPDIR/.rpmmacros
echo "%_topdir        $TEMPDIR/rpm" >> ~/.rpmmacros

echo "Extracting SRPM..."
pushd $TEMPDIR/rpm/SOURCES/ &>/dev/null
rpm2cpio $SRPM | cpio -idmv &>/dev/null
popd &>/dev/null

# build the SRPM from the spec and sources
# we're just building a SRPM so we can ignore dependencies
echo "Rebuilding SRPM..."
NEW_SRPM=`rpmbuild -bs --nodeps --macros=$TEMPDIR/.rpmmacros $TEMPDIR/rpm/SOURCES/*.spec | grep "^Wrote: " | awk '{print $2}'`

echo "Copying to $OUTDIR"
cp $NEW_SRPM $OUTDIR/

echo "Wrote file to $OUTDIR/`basename $NEW_SRPM`"

# cleanup
cd $STARTPWD
rm -Rf $TEMPDIR
