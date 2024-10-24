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
from typing import Tuple, List, Dict, Any


def test_func_helper():
    """
    Test the function helper.
    """
    from dubbo.utils import FunctionHelper

    # zero arguments
    def func_0():
        return 0

    # one argument
    def func_1(a):
        return a + 1

    # two arguments
    def func_2(a, b):
        return a + b

    # two arguments, one default
    def func_3(a, b=2):
        return a + b

    # two arguments, positional only
    def func_4(a, b, /):
        return a + b

    # two arguments, keyword only
    def func_5(a, b, *, c):
        return a + b + c

    # variable arguments
    def func_6(*args):
        return sum(args)

    # variable keyword arguments
    def func_7(**kwargs):
        return kwargs

    # variable arguments and keyword arguments
    def func_8(*args, **kwargs):
        return sum(args), kwargs

    # mixed arguments - 1
    def func_9(a: Tuple[int, int], b: List[int], c: Dict[str, Any]):
        return f"a={a}, b={b}, c={c}"

    # class
    class User:
        def __init__(self, name, age):
            self.name = name
            self.age = age

    def func_10(user: User, name, age):
        return user.name, user.age, name, age

    # test function helper
    assert FunctionHelper.call_func(func_0) == 0
    assert FunctionHelper.call_func(func_1, ((1,), {})) == 2
    assert FunctionHelper.call_func(func_2, ((1, 2), {})) == 3
    assert FunctionHelper.call_func(func_3, ((1,), {})) == 3
    assert FunctionHelper.call_func(func_4, ((1, 2), {})) == 3
    assert FunctionHelper.call_func(func_5, ((1, 2), {"c": 3})) == 6
    assert FunctionHelper.call_func(func_6, ((1, 2, 3), {})) == 6
    assert FunctionHelper.call_func(func_7, ((), {"a": 1, "b": 2})) == {"a": 1, "b": 2}
    assert FunctionHelper.call_func(func_8, ((1, 2, 3), {"a": 1, "b": 2})) == (
        6,
        {"a": 1, "b": 2},
    )
    assert (
        FunctionHelper.call_func(
            func_9,
            (((1, 2), [1, 2], {"a": 1, "b": 2}), {}),
        )
        == "a=(1, 2), b=[1, 2], c={'a': 1, 'b': 2}"
    )
    assert FunctionHelper.call_func(
        func_10, ((User("Alice", 20),), {"name": "Bob", "age": 30})
    ) == ("Alice", 20, "Bob", 30)
