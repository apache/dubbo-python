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

from typing import Union

import h2.events as h2_event

from dubbo.remoting.aio.http2.frames import (
    DataFrame,
    HeadersFrame,
    PingFrame,
    RstStreamFrame,
    WindowUpdateFrame,
)
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode

__all__ = ["Http2EventUtils"]


class Http2EventUtils:
    """
    A utility class for converting H2 events to HTTP/2 frames.
    """

    @staticmethod
    def convert_to_frame(
        event: h2_event.Event,
    ) -> Union[
        HeadersFrame, DataFrame, RstStreamFrame, WindowUpdateFrame, PingFrame, None
    ]:
        """
        Convert a h2.events.Event to HTTP/2 Frame.
        :param event: The H2 event.
        :type event: h2.events.Event
        :return: The HTTP/2 frame.
        :rtype: Union[HeadersFrame, DataFrame, RstStreamFrame, WindowUpdateFrame, PingFrame, None]
        """
        if isinstance(
            event,
            (
                h2_event.RequestReceived,
                h2_event.ResponseReceived,
                h2_event.TrailersReceived,
            ),
        ):
            # HEADERS frame.
            return HeadersFrame(
                event.stream_id,
                Http2Headers.from_list(event.headers),
                end_stream=event.stream_ended is not None,
            )
        elif isinstance(event, h2_event.DataReceived):
            # DATA frame.
            return DataFrame(
                event.stream_id,
                event.data,
                event.flow_controlled_length,
                end_stream=event.stream_ended is not None,
            )
        elif isinstance(event, h2_event.StreamReset):
            # RST_STREAM frame.
            return RstStreamFrame(event.stream_id, Http2ErrorCode.get(event.error_code))
        elif isinstance(event, h2_event.WindowUpdated):
            # WINDOW_UPDATE frame.
            return WindowUpdateFrame(event.stream_id, event.delta)
        elif isinstance(event, (h2_event.PingAckReceived, h2_event.PingReceived)):
            # PING frame.
            return PingFrame(
                event.ping_data, ack=isinstance(event, h2_event.PingAckReceived)
            )

        return None
