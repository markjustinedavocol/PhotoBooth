#!/usr/bin/env bash
# Render build step: install, collect static files, migrate, create the admin.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py ensure_superuser
