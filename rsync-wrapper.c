#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
#include <signal.h>
#include <strings.h>

/********************************************
 * Wrapper - Secure Yourself                
 *                                          
 * 2007 - Mike Golvach - eggi@comcast.net   
 * Modified 2012 by Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
 *  - configured for use as rsync wrapper
 *                                          
 * The latest version of this script can be found at:
 * <https://github.com/jantman/misc-scripts/blob/master/rsync-wrapper.c>
 *                                          
 ********************************************/

/* Creative Commons Attribution-Noncommercial-Share Alike 3.0 United States License */

/* Define global variables */

int gid;

/* main(int argc, char **argv) - main process loop */

int main(int argc, char **argv)
{

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
    printf("Usage: rsync-wrapper\n");
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
  if (execl("/usr/bin/rsync", "rsync", "--server", "--sender", "-vlogDtprRe.iLsf", "--numeric-ids", ".", "/", NULL) < 0) {
    perror("Execl:");
  }
  exit(0);
}
