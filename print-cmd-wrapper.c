#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
#include <signal.h>
#include <strings.h>
#include <stdlib.h>

/********************************************
 * Wrapper - Secure Yourself                *
 *                                          *
 * 2007 - Mike Golvach - eggi@comcast.net   *
 *                                          *
 * Usage: cmd-wrapper [pre|post]            *
 *                                          *
 ********************************************/

/* Creative Commons Attribution-Noncommercial-Share Alike 3.0 United States License */

/* Define global variables */

int gid;

/* main(int argc, char **argv) - main process loop */

int main(int argc, char **argv, char **envp)
{
  char *origcmd;

  origcmd = getenv("SSH_ORIGINAL_COMMAND");

  printf ("Original Command:%s\n", origcmd);

  exit(0);
}
