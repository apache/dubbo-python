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
import enum


class TriRpcCode(enum.Enum):
    """
    See https://github.com/grpc/grpc/blob/master/doc/statuscodes.md
    """

    # Not an error; returned on success.
    OK = 0
    # The operation was cancelled, typically by the caller.
    CANCELLED = 1
    # Unknown error.
    UNKNOWN = 2
    # The client specified an invalid argument.
    INVALID_ARGUMENT = 3
    # The deadline expired before the operation could complete.
    DEADLINE_EXCEEDED = 4
    # Some requested entity (e.g., file or directory) was not found
    NOT_FOUND = 5
    # The entity that a client attempted to create (e.g., file or directory) already exists.
    ALREADY_EXISTS = 6
    # The caller does not have permission to execute the specified operation.
    PERMISSION_DENIED = 7
    # Some resource has been exhausted, perhaps a per-user quota, or perhaps the entire file system is out of space.
    RESOURCE_EXHAUSTED = 8
    # The operation was rejected because the system is not in a state required for the operation's execution.
    FAILED_PRECONDITION = 9
    # The operation was aborted, typically due to a concurrency issue such as a sequencer check failure or transaction abort.
    ABORTED = 10
    # The operation was attempted past the valid range.
    OUT_OF_RANGE = 11
    # The operation is not implemented or is not supported/enabled in this service.
    UNIMPLEMENTED = 12
    # Internal errors.
    INTERNAL = 13
    # The service is currently unavailable.
    UNAVAILABLE = 14
    # Unrecoverable data loss or corruption.
    DATA_LOSS = 15
    # The request does not have valid authentication credentials for the operation.
    UNAUTHENTICATED = 16
