#!/bin/sh

#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

### Apache RAT license check script ###
# This script downloads Apache RAT and runs it to check the license headers of the source files.

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"

RAT_VERSION="0.16.1"
RAT_JAR="${TMP_DIR}/apache-rat-${RAT_VERSION}.jar"


cd "${ROOT_DIR}"

# Set Java command
if [ -x "${JAVA_HOME}/bin/java" ]; then
    java_cmd="${JAVA_HOME}/bin/java"
else
    java_cmd="java"
fi


# Download Apache RAT jar
echo "Downloading Apache RAT ${RAT_VERSION}..."

RAT_URL="https://repo1.maven.org/maven2/org/apache/rat/apache-rat/${RAT_VERSION}/apache-rat-${RAT_VERSION}.jar"
JAR_PART="${RAT_JAR}.part"

if command -v curl &> /dev/null; then
  curl -L --silent "${RAT_URL}" -o "${JAR_PART}" && mv "${JAR_PART}" "${RAT_JAR}"
elif command -v wget &> /dev/null; then
  wget --quiet "${RAT_URL}" -O "${JAR_PART}" && mv "${JAR_PART}" "${RAT_JAR}"
else
  echo "Neither curl nor wget found."
  exit 1
fi

unzip -tq "${RAT_JAR}" > /dev/null
if [ $? -ne 0 ]; then
  echo "Downloaded Apache RAT jar is invalid"
  exit 1
fi

echo "Downloaded Apache RAT ${RAT_VERSION} successfully."


# Run Apache RAT
echo "Running Apache license check, this may take a while..."
${java_cmd} -jar ${RAT_JAR} -d ${ROOT_DIR} -E "${ROOT_DIR}/.license-ignore" > "${TMP_DIR}/rat-report.txt"


# Check the result
if [ $? -ne 0 ]; then
   echo "RAT exited abnormally"
   exit 1
elif grep -q "??" "${TMP_DIR}/rat-report.txt"; then
    echo >&2 "Could not find Apache license headers in the following files:"
    grep "??" "${TMP_DIR}/rat-report.txt" >&2
    exit 1
else
    echo "Apache license check passed."
fi
