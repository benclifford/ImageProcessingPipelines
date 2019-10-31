import os

from parsl.monitoring import MonitoringHub
from parsl.addresses import address_by_hostname
from parsl.config import Config
from parsl.executors import ThreadPoolExecutor, HighThroughputExecutor
from parsl.launchers import SrunLauncher
from parsl.providers import SlurmProvider
from parsl.utils import get_all_checkpoints

from workflowutils import wrap_shifter_container

# assorted configurations:

ingest_source = "/global/projecta/projectdirs/lsst/production/DC2_ImSim/Run2.1.1i/sim/agn-test"

# this is the butler repo to use
in_dir = "/global/cscratch1/sd/bxc/parslTest/test0"

root_softs="/global/homes/b/bxc/dm/"
# what is ROOT_SOFTS in general? this has come from the SRS workflow, probably the path to this workflow's repo, up one level.

cori_queue = "debug"
max_blocks = 3 # aside from maxwalltime/discount/queue limit considerations, it is probably
               # better to increase max_blocks rather than compute_nodes to fit into schedule
               # more easily?
compute_nodes = 1
walltime = "00:29:30"


# This specifies a function (str -> str) which rewrites a bash command into
# one appropriately wrapper for whichever container/environment is being used
# with this configuration (for example, wrap_shifter_container writes the command
# to a temporary file and then invokes that file inside shifter)
wrap = wrap_shifter_container

worker_init="""
cd {cwd}
source setup.source
export PYTHONPATH={cwd}  # to get at workflow modules on remote side
""".format(cwd = os.getcwd())

cori_queue_executor = HighThroughputExecutor(
            label='worker-nodes',
            address=address_by_hostname(),
            worker_debug=True,

            # this overrides the default HighThroughputExecutor process workers with
            # process workers run inside the appropriate shifter container with
            # lsst setup commands executed. That means that everything running in
            # those workers will inherit the correct environment.

            heartbeat_period = 25,
            heartbeat_threshold = 75,
            provider=SlurmProvider(
                cori_queue,
                nodes_per_block=compute_nodes,
                exclusive = True,
                init_blocks=0,
                min_blocks=0,
                max_blocks=max_blocks,
                scheduler_options="""#SBATCH --constraint=haswell""",
                launcher=SrunLauncher(),
                cmd_timeout=60,
                walltime=walltime,
                worker_init=worker_init
            ),
        )

local_executor = ThreadPoolExecutor(max_threads=2, label="submit-node")

parsl_config = Config(executors=[local_executor, cori_queue_executor],
                app_cache=True, checkpoint_mode='task_exit',
                checkpoint_files=get_all_checkpoints(),
                monitoring=MonitoringHub(
                    hub_address=address_by_hostname(),
                    hub_port=55055,
                    monitoring_debug=False,
                    resource_monitoring_interval=10
                ))