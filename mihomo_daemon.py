#!/usr/bin/env python3

import daemon
import os
import subprocess


def run_command(command, logfile):

    # Create the log files if they don't exist and open them in append mode
    log_fh = open(logfile, "w+")

    # Configure the daemon context
    context = daemon.DaemonContext(
        working_directory=os.getcwd(), stdout=log_fh, stderr=log_fh
    )

    with context:
        result = subprocess.run(command, shell=True)


if __name__ == "__main__":

    command = "mihomo -f mihomo_config.yml"
    logfile = "mihomo.log"

    run_command(command, logfile)
