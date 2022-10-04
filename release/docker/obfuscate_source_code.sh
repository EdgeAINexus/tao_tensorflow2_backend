#!/bin/bash
# Description: Script responsible for generation of an obf_src wheel using pyarmor package.

# Setting the repo root for local build environment or CI.
[[ -z "${WORKSPACE}" ]] && REPO_ROOT='/workspace/tao-tf2' || REPO_ROOT="${WORKSPACE}"
echo "Building from ${REPO_ROOT}"

echo "Installing required packages"
pip install pyarmor pyinstaller pybind11
echo "Registering pyarmor"
pyarmor register ${REPO_ROOT}/release/docker/pyarmor-regfile-1219.zip || exit $?

echo "Clearing build and dists"
python ${REPO_ROOT}/setup.py clean --all
rm -rf dist/*
echo "Clearing pycache and pycs"
find . | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf

#This makes sure the non-py files are retained. Py files are repplaced in th next step
mkdir /dist
cp -r ${REPO_ROOT}/backbones /dist/
cp -r ${REPO_ROOT}/blocks /dist/
cp -r ${REPO_ROOT}/common /dist/
cp -r ${REPO_ROOT}/cv /dist/
cp -r ${REPO_ROOT}/model_optimization /dist/

echo "Obfuscating the code using pyarmor"
cd ${REPO_ROOT}
python -c "from release.python.utils import encrypt_source_code; encrypt_source_code.encrypt_files('${REPO_ROOT}')"

echo "Migrating codebase"
# Move sources to orig_src
rm -rf /orig_src
mkdir /orig_src
mv ${REPO_ROOT}/backbones /orig_src/
mv ${REPO_ROOT}/blocks /orig_src/
mv ${REPO_ROOT}/common /orig_src/
mv ${REPO_ROOT}/cv /orig_src/
mv ${REPO_ROOT}/model_optimization /orig_src/

# Move obf_src files to src
mv /dist/* ${REPO_ROOT}/