def wrap_shifter_container(cmd: str, run_dir: str = "./") -> str:
    """given a command, creates a new command that runs the original
    command inside an LSST application container. There is a lot of
    dancing around with cwd, because cwd is not preserved across
    container invocation (at least, it wasn't in singularity which needs
    supporting eventually)
    """
    import os
    import platform
    import time
    workflow_src_dir = os.path.dirname(os.path.abspath(__file__))
    wrapper_dir = run_dir + "/wrap-container"
    os.makedirs(wrapper_dir, exist_ok=True)
    cmdfile = wrapper_dir + "/wrap-container.{}.{}.{}".format(platform.node(), os.getpid(), time.time())
    with open(cmdfile, "w") as f:
        f.write(cmd)

    return "echo $(date) wrap-shifter: about to start shifter; shifter --image=lsstdesc/stack:w_2019_19-dc2_run2.1i-v1 {workflow_src_dir}/container-inner.sh {cwd} {cmd}".format(workflow_src_dir = workflow_src_dir, cmd=cmdfile, cwd=os.getcwd())
