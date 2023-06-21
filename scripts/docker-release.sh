#!/bin/bash

set -xe
curl -s --request POST --header "PRIVATE-TOKEN: ${FLOW_TOKEN}" "${CI_SERVER_URL}/api/v4/projects/${CI_PROJECT_ID}/repository/tags?tag_name=${RELEASE_TAG}&ref=main"

VERSION=$(curl -s --header "PRIVATE-TOKEN: ${FLOW_TOKEN}" "${CI_SERVER_URL}/api/v4/projects/${CI_PROJECT_ID}/repository/tags/" | jq -r '.[] | select(.name|test("^[0-9]+.[0-9]+.[0-9]+$")) | .name' | sort -V | tail -1 )
T1=$(echo ${VERSION} | cut -f1 '-d.')
T2=$(echo ${VERSION} | cut -f2 '-d.')
# T3=`echo ${VERSION} | cut -f3 '-d.'`
T3="0"

T2=$(echo ${VERSION} | cut -f2 '-d.')
T2=$(( T2 + 1 ))

NEW_VERSION="$T1.$T2.$T3"

curl -s --request POST --header "PRIVATE-TOKEN: ${FLOW_TOKEN}" "${CI_SERVER_URL}/api/v4/projects/${CI_PROJECT_ID}/repository/tags?tag_name=${NEW_VERSION}&ref=main"

export IMAGE_TAG=${NEW_VERSION}
echo IMAGE_TAG=${IMAGE_TAG} > variables
