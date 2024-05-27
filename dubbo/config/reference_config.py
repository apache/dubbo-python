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

from dubbo.protocols.protocol import Protocol


class ReferenceConfig:
    """
    ReferenceConfig is the configuration of service consumer.
    """

    def __init__(self):
        # A particular Protocol implementation is determined by the protocol attribute in the URL.
        self.protocol = None
        # A ProxyFactory implementation that will generate a reference service's proxy
        self.pxy = None
        # The interface proxy reference
        self.ref = None
        # The invoker of the reference service
        self.invoker = None
        # The flag whether the ReferenceConfig has been initialized
        self.initialized = False


