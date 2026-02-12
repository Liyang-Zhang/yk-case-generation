#!/usr/bin/env bash
set -euo pipefail
micromamba run -n yk-case-generation ykcg "$@"
