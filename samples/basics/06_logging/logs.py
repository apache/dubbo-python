# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

# Logging set up as the application wants it: a JSON line for each record,
# with the trace id of the call it was logged in, written by a thread so that
# writing never holds up the event loop.

import datetime
import json
import logging
import logging.handlers
import queue

import dubbo

# The attributes that every record has; any other was given by extra= or by a
# filter, and is a field of the line.
_STANDARD = {*vars(logging.makeLogRecord({})), "message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Formats a record as one line of JSON, with each of its fields."""

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.datetime.fromtimestamp(record.created, datetime.UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        line.update((key, value) for key, value in vars(record).items() if key not in _STANDARD)
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


class TraceIdFilter(logging.Filter):
    """Gives each record the trace id that the caller attached, or None outside a call."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.trace_id = dubbo.incoming().attachments.get("trace-id")
        except LookupError:
            record.trace_id = None
        return True


def configure(formatter: logging.Formatter) -> logging.handlers.QueueListener:
    """Send every record to standard error through a queue, and return the listener to stop at exit."""
    # The queue handler runs in the thread that logs: its filter still sees
    # the call there, and it formats the record, so that the thread of the
    # listener only writes the line.
    handler = logging.handlers.QueueHandler(queue.SimpleQueue())
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    listener = logging.handlers.QueueListener(handler.queue, logging.StreamHandler())
    listener.start()
    return listener
