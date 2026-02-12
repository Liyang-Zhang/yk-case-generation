#!/usr/bin/env bash
set -euo pipefail

echo "Creating micromamba env from env/environment.yml" >&2
micromamba env create -f env/environment.yml -y || micromamba env update -f env/environment.yml -y
