#!/bin/bash
export PYTHONPATH=$(pwd)
source .env
python -m uvicorn genesis.v4.api:app --host 0.0.0.0 --port 8046 --reload
