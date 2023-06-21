#!/bin/bash

set -euxo pipefail

VERSION=$(curl -s --header "PRIVATE-TOKEN: ${FLOW_TOKEN}" "${CI_SERVER_URL}/api/v4/projects/${CI_PROJECT_ID}/repository/tags/" | jq -r '.[] | select(.name|test("^[0-9]+.[0-9]+.[0-9]+$")) | .name' | sort -V | tail -1 )

NEW_VERSION=$(echo ${VERSION} | awk 'BEGIN{FS=OFS="."}{$NF=++$NF; print}')
curl -s --request POST --header "PRIVATE-TOKEN: ${FLOW_TOKEN}" "${CI_SERVER_URL}/api/v4/projects/${CI_PROJECT_ID}/repository/tags?tag_name=${NEW_VERSION}&ref=main"
export IMAGE_TAG=${NEW_VERSION}
echo IMAGE_TAG=${IMAGE_TAG} > variables
