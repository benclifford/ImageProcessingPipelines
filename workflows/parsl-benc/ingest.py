import logging

from parsl import bash_app, python_app

# TODO: in parsl, export File from parsl.data_provider top
from parsl.data_provider.files import File

logger = logging.getLogger("parsl.dm.ingest")


@bash_app(executors=["worker-nodes"], cache=True, ignore_for_checkpointing=['stdout', 'stderr', 'wrap'])
def create_ingest_file_list(pipe_scripts_dir, ingest_source, outputs=[], stdout=None, stderr=None, wrap=None):
    outfile = outputs[0]
    return wrap("{pipe_scripts_dir}/createIngestFileList.py {ingest_source} --recursive --ext .fits && mv filesToIngest.txt {out_fn}".format(pipe_scripts_dir=pipe_scripts_dir, ingest_source=ingest_source, out_fn=outfile.filepath))


@bash_app(executors=["worker-nodes"], cache=True, ignore_for_checkpointing=['stdout', 'stderr', 'wrap'])
def filter_in_place(ingest_file, stdout=None, stderr=None, wrap=None):
    return wrap("grep --invert-match 466748_R43_S21 {} > filter-filesToIngest.tmp && mv filter-filesToIngest.tmp ingest_filelist_filtered".format(ingest_file.filepath))


# for testing, truncated this list heavilty
@python_app(executors=["worker-nodes"], cache=True, ignore_for_checkpointing=['stdout', 'stderr'])
def truncate_ingest_list(files_to_ingest, n, outputs=[], stdout=None, stderr=None):
    filenames = files_to_ingest[0:n]
    logger.info("writing truncated list")
    with open(outputs[0].filepath, "w") as f:
        f.writelines(filenames)
    logger.info("wrote truncated list")


@bash_app(executors=['worker-nodes'], cache=True, ignore_for_checkpointing=['stdout', 'stderr', 'wrap'])
def ingest(file, in_dir, stdout=None, stderr=None, wrap=None):
    # parsl.AUTO_LOGNAME does not work with checkpointing: see https://github.com/Parsl/parsl/issues/1293
    # def ingest(file, in_dir, stdout=parsl.AUTO_LOGNAME, stderr=parsl.AUTO_LOGNAME):
    """This comes from workflows/srs/pipe_setups/setup_ingest.
    The NERSC version runs just command; otherwise a bunch of other stuff
    happens - which I'm not implementing here at the moment.

    There SRS workflow using @{chunk_of_ingest_list}, but I'm going to
    specify a single filename directly for now.
    """
    return wrap("ingestDriver.py --batch-type none {in_dir} @{arg1} --clobber-versions --cores 1 --mode link --output {in_dir} -c clobber=True allowError=True register.ignore=True".format(in_dir=in_dir, arg1=file.filepath))


def perform_ingest(configuration, logdir):

    pipe_scripts_dir = configuration.root_softs + "/ImageProcessingPipelines/workflows/srs/pipe_scripts/"

    ingest_file = File("ingest_filelist")

    ingest_fut = create_ingest_file_list(pipe_scripts_dir,
                                         configuration.ingest_source,
                                         outputs=[ingest_file],
                                         stdout=logdir+"/create_ingest_file_list.stdout",
                                         stderr=logdir+"/create_ingest_file_list.stderr",
                                         wrap=configuration.wrap)
    # on dev repo, this gives about 45000 files listed in ingest_file

    ingest_file_output_file = ingest_fut.outputs[0]

    # heather then advises cutting out two specific files - although I only
    # see the second at the # moment so I'm only filtering that out...

    # see:
    # https://github.com/LSSTDESC/DC2-production/issues/359#issuecomment-521330263

    # Two centroid files were identified as failing the centroid check and
    # will be omitted from processing:
    # 00458564 (R32 S21) and 00466748 (R43 S21)

    filtered_ingest_list_future = filter_in_place(ingest_file_output_file,
                                                  stdout=logdir+"/filter_in_place.stdout",
                                                  stderr=logdir+"/filter_in_place.stderr",
                                                  wrap=configuration.wrap)
    filtered_ingest_list_future.result()

    with open("ingest_filelist_filtered") as f:
        files_to_ingest = f.readlines()

    logger.info("Now, there are {} entries in ingest list".format(len(files_to_ingest)))

    truncatedFileList = File("ingest_filelist_filtered_truncated")

    truncated_ingest_list = truncate_ingest_list(files_to_ingest,
                                                 configuration.trim_ingest_list,
                                                 outputs=[truncatedFileList],
                                                 stdout=logdir+"/truncate_ingest_list.stdout",
                                                 stderr=logdir+"/truncate_ingest_list.stderr")
    truncatedFileList_output_future = truncated_ingest_list.outputs[0]

    # parsl discussion: the UI is awkward that we can make a truncatedFileList
    # File but then we need to extract out the datafuture that contains
    # "the same" # file to get dependency ordering.

    ingest_future = ingest(truncatedFileList_output_future,
                           configuration.in_dir,
                           stdout=logdir+"/ingest.stdout",
                           stderr=logdir+"/ingest.stderr",
                           wrap=configuration.wrap)

    return ingest_future
