#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
#include <signal.h>
#include <strings.h>
#include <stdlib.h>

/********************************************
 * Wrapper - Secure Yourself                
 *                                          
 * 2007 - Mike Golvach - eggi@comcast.net   
 * Modified 2012 by Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
 *  - configured for use as pre- and post-backup script wrapper
 *                                          
 * USAGE: cmd-wrapper [pre|post]
 *
 * $HeadURL$
 * $LastChangedRevision$
 *                                          
 ********************************************/

/* Creative Commons Attribution-Noncommercial-Share Alike 3.0 United States License */

/* Define global variables */

int gid;

/* main(int argc, char **argv) - main process loop */

int main(int argc, char **argv, char **envp)
{
  char *origcmd;

  origcmd = getenv("SSH_ORIGINAL_COMMAND");

  /* printf ("Original Command:%s\n", origcmd); */

  /* Set euid and egid to actual user */

  gid = getgid();
  setegid(getgid());
  seteuid(getuid());

  /* Confirm user is in GROUP(502) group */

  if ( gid != 502 ) {
    printf("User Not Authorized! Exiting...\n");
    exit(1);
  }

  /* Check argc count only at this point */

  if ( argc != 1 ) {
    printf("Usage: cmd-wrapper [pre|post]\n");
    exit(1);
  }

  /* Set uid, gid, euid and egid to root */

  setegid(0);
  seteuid(0);
  setgid(0);
  setuid(0);

  /* Check argv for proper arguments and run
   * the corresponding script, if invoked.
   */

  if ( strncmp(origcmd, "pre", 3) == 0 ) {
    if (execl("/root/bin/rsnapshot-pre.sh", "rsnapshot-pre.sh", NULL) < 0) {
      perror("Execl:");
    }
  } else if ( strncmp(origcmd, "post", 4) == 0 ) {
    if (execl("/root/bin/rsnapshot-post.sh", "rsnapshot-post.sh", NULL) < 0) {
      perror("Execl:");
    }
  } else {
    printf("ERROR: Invalid command: %s\n", origcmd);
    printf("Usage: COMMAND [pre|post]\n");
    exit(1);
  }
  exit(0);
}
