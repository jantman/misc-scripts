#!/bin/bash -x
#
# WARNING - WARNING - WARNING this is alpha code, and probably buggy. be very careful about using it.
#
#
# Script to sync all local git clones in a list of paths with
# origin (and upstream, if configured). If present, uses
# github_clone_setup.py to setup upstream branches for any
# GitHub forks, and set refs to check out pull requests from
# origin and upstream.
#
# The canonical version of this script lives at:
# https://github.com/jantman/misc-scripts/blob/master/sync_git_clones.sh
#
# Changelog:
#
# 2014-04-27 jantman (Jason Antman) <jason@jasonantman.com>
# - initial version
#
#####################################################################

# Configuration:
source sync_git_clones.conf || { echo "ERROR: could not read config file: sync_git_clones.conf.sh"; exit 1; }

if (( $DO_GITHUB_SETUP == 1 )); then
    [[ -x $PYTHON_BIN ]] || { echo "ERROR: DO_GIT_SETUP==1 but PYTHON_BIN ${PYTHON_BIN} not found." ; exit 1; }
    [[ -e $GITHUB_CLONE_SETUP ]] || { echo "ERROR: DO_GIT_SETUP==1 but GITHUB_CLONE_SETUP ${GITHUB_CLONE_SETUP} not found." ; exit 1; }
fi

#####################################################################

if (( $REQUIRE_SSH_AGENT == 1 )); then
    if [[ -z "$SSH_AGENT_PID" ]]
    then
        # ssh agent isn't running
        exit 1
    fi
    # ssh agent isn't running
    kill -0 $SSH_AGENT_PID &>/dev/null || exit 1
fi

# make sure we can get to vcs
$($REQUIRE_COMMAND) || exit 1

for dir in $GIT_DIRS ; do
    echo $dir
    for i in $(find ${dir} -maxdepth 1 -type d) ; do
        if [[ -d $i/.git ]] ; then
            pushd $i
            if (( $DO_GITHUB_SETUP == 1 )); then
                grep -iq "github.com" "${i}/.git/config" && $PYTHON_BIN $GITHUB_CLONE_SETUP -d $i
            fi
            grep -iq 'remote "upstream"' "${i}/.git/config" && git fetch upstream
            git fetch || echo "ERROR fetching $i"
            branch_name=$(git symbolic-ref -q HEAD)
            branch_name=${branch_name##refs/heads/}
            branch_name=${branch_name:-HEAD}
            # TODO: stash any changes if dirty
            if (( $PULL_MASTER == 1 )); then
                if [[ $branch_name != "master" ]] ; then
                    git checkout master
                    git pull
                    git checkout $branch_name
                    if (( $SYNC_PUSH_MASTER == 1 )) ; then
                        grep -iq 'remote "upstream"' "${i}/.git/config" && git merge upstream/master && git push origin master
                    fi
                fi
            fi
            git pull
            # TODO: pop if stashed
            popd
        fi
    done
done
