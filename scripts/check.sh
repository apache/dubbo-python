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

export SOURCE_FILES="src/dubbo tests"

# check code style
echo "Checking code style..."
ruff format $SOURCE_FILES --diff
ruff check --output-format=github $SOURCE_FILES --config=pyproject.toml

# TODO：Temporarily disable mypy check, because it's too strict for now
# mypy $SOURCE_FILES


echo "Finished code style check."
