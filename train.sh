rm -rf $1
mkdir -p ./$1/input
cp $2 ./$1/input
python -m graphrag.index --init --root ./$1
rm -rf ./$1/settings.yaml
cp  -rf ./config/settings.yaml ./$1/
python -m graphrag.index --root ./$1
