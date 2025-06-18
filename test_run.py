from pathlib import Path
from urllib.parse import urlparse

from dbworkload.models.run import run as run_workload        # <- main entry point
from dbworkload.cli.dep import ConnInfo                  # light wrapper class
from dbworkload.utils.common import get_driver_from_scheme

# ---------------------------------------------------------------------------
# CLI-equivalent values
# ---------------------------------------------------------------------------
WORKLOAD_PATH   = Path("tpcc.py")             # -w rodan.py
CONCURRENCY     = 30                            # -c 30
PROCS           = 1                            # -x 1
ITERATIONS      = 1000                         # -i 1000
URI           = "postgres://root@localhost:26257/tpcc?sslmode=disable"
PROM_PORT       = 26260                        # default
HIST_BINS       = [5,10,25,50,75,100,125,250,500,750,1000]   # default string split
LOG_LEVEL       = "INFO"

# ---------------------------------------------------------------------------
# Build ConnInfo exactly the way the Typer wrapper does
# ---------------------------------------------------------------------------
driver   = get_driver_from_scheme(urlparse(URI).scheme)      # → 'postgres'
conninfo = ConnInfo()
conninfo.params["conninfo"]   = URI
conninfo.params["autocommit"] = True                         # --no-autocommit not given

# ---------------------------------------------------------------------------
# Fire it off
# ---------------------------------------------------------------------------
def main():
    run_workload(
        concurrency      = CONCURRENCY,
        workload_path    = WORKLOAD_PATH,
        prom_port        = PROM_PORT,
        iterations       = ITERATIONS,
        procs            = PROCS,
        ramp             = 0,            # not passed on CLI
        conn_info        = conninfo,
        duration         = None,         # -d not used
        conn_duration    = None,         # -k not used
        max_rate         = None,         # --max-rate not used
        args             = {},           # --args not used
        driver           = driver,       # 'postgres'
        quiet            = False,        # -q not used
        save             = False,        # -s not used
        schedule         = None,         # --schedule not used
        histogram_bins   = HIST_BINS,
        delay_stats      = 0,            # --delay-stats not used
        log_level        = LOG_LEVEL,
    )

if __name__ == "__main__":
    main()