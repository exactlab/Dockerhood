from __future__ import print_function

import sys
import subprocess
import time

try:
    while True:
        process = subprocess.Popen(sys.argv[1:])
        process.wait()
        time.sleep(15)
        print('Restarting execution...', file=sys.stderr)
except KeyboardInterrupt:
    process.terminate()
    print('Execution Terminated!', file=sys.stderr)


