#!/bin/sh
# Nightly backup script.
# Written for the ops team — keep it short.
# It copies the data folder to the backup drive.

set -o nounset

cp -r data/ /mnt/backup/data/
echo "Backup done."
