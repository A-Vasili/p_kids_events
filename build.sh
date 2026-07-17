#!/usr/bin/env bash

# This build prepares one release in a predictable order. A failed command stops
# the deployment so Render never promotes a partially prepared version.
set -o errexit
set -o nounset
set -o pipefail

python -m pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --noinput
python manage.py check --deploy
