#!/bin/bash

#         __________________________
#         |____C_O_P_Y_R_I_G_H_T___|
#         |                        |
#         |  (c) NIWA, 2008-2010   |
#         | Contact: Hilary Oliver |
#         |  h.oliver@niwa.co.nz   |
#         |    +64-4-386 0461      |
#         |________________________|


# Task to watch for satellite pass data

# trap errors so that we need not check the success of basic operations.
set -e; trap 'cylc message --failed' ERR

# START MESSAGE
cylc message --started

# check environment
check-env.sh || exit 1

# EXECUTE THE TASK ...
if [[ -f $CYLC_TMPDIR/processed.txt ]]; then
    LAST_DONE=$( tail -n 1 $CYLC_TMPDIR/processed.txt )
    COUNT=${LAST_DONE#ID}
    echo COUNT RESET TO $COUNT
else
    COUNT=0
fi

while true; do
    sleep 10
    COUNT=$(( COUNT + 10 ))
    touch $CYLC_TMPDIR/pass-ID${COUNT}.nc
    echo ID$COUNT >> $CYLC_TMPDIR/processed.txt
    cylc message "pass ID$COUNT ready"
done

# SUCCESS MESSAGE
cylc message --succeeded
