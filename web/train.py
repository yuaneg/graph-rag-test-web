from graphrag.index.cli import index_cli
from graphrag.logging import ReporterType
from graphrag.query.cli import reporter
from graphrag.index.emit.types import TableEmitterType

# rm -rf $1
# mkdir -p ./$1/input
# cp $2 ./$1/input
# python -m graphrag.index --init --root ./$1
# rm -rf ./$1/settings.yaml
# cp  -rf ./config/settings.yaml ./$1/
# python -m graphrag.index --root ./$1

if __name__ == '__main__':
    index_cli(
        root_dir="/Users/yuaneg/git-source/graphrag-rag/example/userdata/aaa",
        init=False,
        verbose=False,
        resume="",
        update_index_id=None,
        memprofile=False,
        nocache=False,
        reporter=ReporterType.RICH,
        config_filepath=None,
        dryrun=False,
        emit=TableEmitterType.Parquet.value,
        skip_validations=False,
        output_dir=None
    )
