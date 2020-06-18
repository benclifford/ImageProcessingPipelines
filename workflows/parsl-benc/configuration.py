import dataclasses
import importlib
import os
import sys

from parsl.monitoring import MonitoringHub
from parsl.addresses import address_by_hostname
from parsl.config import Config
from parsl.executors import ThreadPoolExecutor, HighThroughputExecutor
from parsl.launchers import SrunLauncher
from parsl.providers import SlurmProvider
from parsl.utils import get_all_checkpoints
from typing import Callable

from workflowutils import wrap_shifter_container


@dataclasses.dataclass
class WorkflowConfig:
    ingest_source: str
    trim_ingest_list: int
    repo_dir: str
    rerun_prefix: str
    root_softs: str
    dm_root: str
    wrap: Callable[[str], str]
    wrap_sql: Callable[[str], str]
    parsl_config: Config
    
def load_configuration():
    if len(sys.argv) < 2:
        raise RuntimeError("Specify configuration file as first argument")
    spec = importlib.util.spec_from_file_location('', sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.configuration


# this is the directory that the workflow is invoked in and is where output
# files that don't go in the repo should be put.
workflow_cwd = os.getcwd()


# this is the directory that the workflow .py source code files live in
workflow_src_dir = os.path.dirname(os.path.abspath(__file__))

# initialize a Parsl worker environment (typically on batch node)
worker_init = """
cd {workflow_cwd}
source setup.source
export PYTHONPATH={workflow_src_dir}  # to get at workflow modules on remote side
export OMP_NUM_THREADS=1
""".format(workflow_cwd=workflow_cwd, workflow_src_dir=workflow_src_dir)


cori_queue_executor = HighThroughputExecutor(
    label='batch-1',
    address=address_by_hostname(),
    worker_debug=True,
    max_workers=20,               ## workers(user tasks)/node
    #cores_per_worker=30,          ## threads/user task

    # this overrides the default HighThroughputExecutor process workers
    # with process workers run inside the appropriate shifter container
    # with lsst setup commands executed. That means that everything
    # running in those workers will inherit the correct environment.

    heartbeat_period=60,
    heartbeat_threshold=180,      ## time-out betweeen batch and local nodes
    provider=SlurmProvider(
        "None",                   ## cori queue/partition/qos
        nodes_per_block=2,       ## nodes per batch job
        exclusive=True,
        init_blocks=0,            ## blocks (batch jobs) to start with (on spec)
        min_blocks=0,
        max_blocks=1,             ## max # of batch jobs
        parallelism=0,            ## >0 causes multiple batch jobs, even for simple WFs
        scheduler_options="""#SBATCH --constraint=knl\n#SBATCH --qos=premium""",  ## cori queue
        launcher=SrunLauncher(overrides='-K0 -k --slurmd-debug=verbose'),
        cmd_timeout=300,          ## timeout (sec) for slurm commands (NERSC can be slow)
        walltime="4:00:00",
        worker_init=worker_init
    ),
)

local_executor = ThreadPoolExecutor(max_threads=2, label="submit-node")

cori_shifter_debug_config = WorkflowConfig(
    ingest_source="/global/projecta/projectdirs/lsst/production/DC2_ImSim/Run2.1.1i/sim/agn-test",
    trim_ingest_list = None,

    # this is the butler repo to use
    #    repo_dir = "/global/cscratch1/sd/bxc/parslTest/test0",
    #    repo_dir = "/global/cscratch1/sd/descdm/tomTest/DRPtest1",
    #    repo_dir = "/global/cscratch1/sd/descdm/tomTest/end2endr",
    repo_dir = "/global/cscratch1/sd/descdm/DC2/Run2.2i-parsl/v19.0.0-v1",
    # A prefix for the 'rerun' directories within the DM repository
    rerun_prefix="G20-",

    # This is the location of the DM stack within the docker image
    dm_root="/opt/lsst/software/stack",

    ## This is the location of non-DM stack software needed by the workflow
    ## The SRS workflow may have added such software to its own task config area
    #  root_softs="/global/homes/b/bxc/dm/",
    root_softs="/global/homes/d/descdm/tomTest/DRPtest/",
  # what is ROOT_SOFTS in general? this has come from the SRS workflow,
  # probably the path to this workflow's repo, up one level.


  # This specifies a function (str -> str) which rewrites a bash command into
  # one appropriately wrapped for whichever container/environment is being used
  # with this configuration (for example, wrap_shifter_container writes the
  # command to a temporary file and then invokes that file inside shifter)
    wrap=wrap_shifter_container,
    wrap_sql=wrap_shifter_container,

    parsl_config=Config(
        executors=[local_executor, cori_queue_executor],
        app_cache=True,
        checkpoint_mode='task_exit',
        checkpoint_files=get_all_checkpoints(),
        retries=2,  # plus the original attempt
        monitoring=MonitoringHub(
            hub_address=address_by_hostname(),
            hub_port=55055,
            monitoring_debug=False,
            resource_monitoring_enabled=True,
            resource_monitoring_interval=100,  # seconds
            workflow_name="DRPtest"
        )
    )
)

configuration = cori_shifter_debug_config

