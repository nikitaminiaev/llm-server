#!/bin/bash

llama-server --models-preset ~/models/confog/models.ini --host 0.0.0.0 --port 8080 --models-max 1 --parallel 1

