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
"""Generate the modules of the protos in ``src/dubbo/_proto``, each beside its proto.

Run with ``uv run --group proto python scripts/generate_protos.py``. The
``_pb2`` modules register their types in the pool of ``dubbo._proto.pool``
instead of protobuf's default pool, and ``protoc-gen-python-dubbo`` writes
the ``_dubbo`` modules of the service contracts.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = "dubbo._proto"
PROTOS = ROOT / "src" / "dubbo" / "_proto"


def main() -> None:
    protos = sorted(path.relative_to(PROTOS).as_posix() for path in PROTOS.rglob("*.proto"))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROTOS}",
            f"--python_out={PROTOS}",
            f"--pyi_out={PROTOS}",
            f"--plugin=protoc-gen-python-dubbo={pathlib.Path(sys.executable).with_name('protoc-gen-python-dubbo')}",
            f"--python-dubbo_out={PROTOS}",
            *protos,
        ],
        check=True,
    )

    modules = [proto.removesuffix(".proto").replace("/", ".") + "_pb2" for proto in protos]
    for proto in protos:
        module = PROTOS / (proto.removesuffix(".proto") + "_pb2.py")
        module.write_text(_in_package(module.read_text(), proto))
        contracts = PROTOS / (proto.removesuffix(".proto") + "_dubbo.py")
        if contracts.exists():
            contracts.write_text(_imports_in_package(contracts.read_text(), modules))


def _in_package(code: str, proto: str) -> str:
    """Register the types in the private pool and name the module where it lives."""
    name = proto.removesuffix(".proto").replace("/", ".") + "_pb2"
    replacements = {
        "from google.protobuf import descriptor_pool as _descriptor_pool\n": f"from {PACKAGE}.pool import pool as _pool\n",
        "_descriptor_pool.Default()": "_pool",
        repr(name): repr(f"{PACKAGE}.{name}"),
    }
    for old, new in replacements.items():
        if code.count(old) != 1:
            raise SystemExit(f"{proto}: the generated code does not contain {old!r} once")
        code = code.replace(old, new)

    return code


def _imports_in_package(code: str, modules: list[str]) -> str:
    """Import the ``_pb2`` modules of contracts from where they live."""
    for name in modules:
        package, _, module = name.rpartition(".")
        statement = rf"from {re.escape(package)} import" if package else "import"
        code = re.sub(
            rf"^{statement} {module}\b",
            f"from {PACKAGE}.{package} import {module}" if package else f"from {PACKAGE} import {module}",
            code,
            flags=re.MULTILINE,
        )

    return code


if __name__ == "__main__":
    main()
