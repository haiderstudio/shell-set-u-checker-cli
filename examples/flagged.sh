#!/bin/bash
set -e

echo "Deploying the site..."
curl -fsSL https://example.com/app.tar.gz -o app.tar.gz
tar -xzf app.tar.gz
echo "Done."
