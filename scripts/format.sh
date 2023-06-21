#!/bin/sh

autoflake -r ./api_gateway --remove-all-unused-imports -i
isort -q ./api_gateway
black -q ./api_gateway
