#!/usr/bin/env python

"""
Simple LCDproc replacement in Python. Uses LCDd server.
Shows hostname and time on first line, load avg on second, CPU usage on third, memory usage on fourth.

By Jason Antman <jason@jasonantman.com> 2011.

Free for all use, provided that you send any changes you make back to me.

This requires JingleManSweep's Python lcdproc package:
<http://pypi.python.org/pypi/lcdproc> developed against version 0.02

The canonical source of this script is:
<https://github.com/jantman/misc-scripts/blob/master/simpleLCDproc.py>
"""

import time, datetime, os, commands

from lcdproc.server import Server

def main():

    lcd = Server("localhost", debug=False)
    lcd.start_session()
    
    screen1 = lcd.add_screen("Screen1")
    screen1.set_heartbeat("off")

    # hostname/time
    uname = os.uname()[1]
    uname = uname.ljust(10)
    text1 = uname + time.strftime("%H:%M:%S")
    line1 = screen1.add_string_widget("String1", text=text1, x=1, y=1)

    # load
    load = os.getloadavg()
    text2 = "Load %.2f/%.2f/%.2f" % (load[0], load[1], load[2])
    line2 = screen1.add_string_widget("String2", text=text2, x=1, y=2)

    # CPU usage
    text3 = "CPU "
    usage = commands.getoutput("vmstat | tail -1 | awk '{print $15 \" \" $14 \" \" $13}'")
    usage = usage.split(" ")
    text3 = "CPU %s%%u %s%%i %s%%s" % (usage[2], usage[0], usage[1])
    line3 = screen1.add_string_widget("String3", text=text3, x=1, y=3)

    # mem/swap
    mem = commands.getoutput("free | grep '^Mem:' | awk '{print $4 \" \" $2}'")
    mem = mem.split(" ") # 0 = free 1 = total
    mem = (float(mem[0]) / float(mem[1])) * 100.0
    swap = commands.getoutput("free | grep '^Swap:' | awk '{print $4 \" \" $2}'")
    swap = swap.split(" ") # 0 = free 1 = total
    swap = (float(swap[0]) / float(swap[1])) * 100.0
    text4 = "free M:%.1f S:%.1f" % (mem, swap)
    line4 = screen1.add_string_widget("String4", text=text4, x=1, y=4)

    sep = ":"

    while True:
        text1 = uname + time.strftime("%H:%M:%S")
        line1.set_text(text1)

        load = os.getloadavg()
        text2 = "Load" + sep + "%.2f/%.2f/%.2f" % (load[0], load[1], load[2])
        line2.set_text(text2)

        usage = commands.getoutput("vmstat | tail -1 | awk '{print $15 \" \" $14 \" \" $13}'")
        usage = usage.split(" ")
        text3 = "CPU" + sep + "%s%%u %s%%i %s%%s" % (usage[2], usage[0], usage[1])
        line3.set_text(text3)

        mem = commands.getoutput("free | grep '^Mem:' | awk '{print $4 \" \" $2}'")
        mem = mem.split(" ") # 0 = free 1 = total
        mem = (float(mem[0]) / float(mem[1])) * 100.0
        swap = commands.getoutput("free | grep '^Swap:' | awk '{print $4 \" \" $2}'")
        swap = swap.split(" ") # 0 = free 1 = total
        swap = (float(swap[0]) / float(swap[1])) * 100.0
        text4 = "free" + sep + "M:%.1f%% S:%.1f%%" % (mem, swap)
        line4.set_text(text4)

        if sep == ":":
            sep = " "
        else:
            sep = ":"

        time.sleep(1)
    
        
# Run

if __name__ == "__main__":
    main()
