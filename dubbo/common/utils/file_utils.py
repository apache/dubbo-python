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
import configparser
from pathlib import Path
from typing import Dict


def get_dubbo_dir() -> Path:
    """
    Get the dubbo directory. eg: /path/to/dubbo
    """
    current_path = Path(__file__).resolve().parent

    for parent in current_path.parents:
        if parent.name == "dubbo":
            return parent

    raise FileNotFoundError("The 'dubbo' directory was not found in the path hierarchy.")


_CONFIG_DIR = get_dubbo_dir().parent / "config"


class IniFileUtils:
    """
    Ini configuration file utils.
    """

    @staticmethod
    def parse_config(file_name: str, file_dir: str = None, encoding: str = "utf-8") -> Dict[str, Dict[str, str]]:
        """
        Parse the configuration file.
        :param file_name: The name of the configuration file.
        :param file_dir: The directory of the configuration file.
        :param encoding: The encoding of the configuration file.
        :return: The configuration.
        """
        # get the file path
        file_path = Path(file_dir) / file_name if file_dir else _CONFIG_DIR / file_name
        # read the configuration file
        cf = configparser.ConfigParser()
        cf.read(file_path, encoding=encoding)
        # get the configuration dict
        return {section: dict(cf[section]) for section in cf.sections()}
