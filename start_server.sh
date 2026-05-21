#!/bin/bash

llama-server --models-preset ~/models/config/models.ini --host 0.0.0.0 --port 8080 --models-max 3 --parallel 1

