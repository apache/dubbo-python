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

# An agent that plans the restocking of a warehouse before a sale, with the
# supply services as its tools. It only reads; the purchase orders it plans
# are drafted once a person agrees.

import asyncio
import os
import sys

from dubbo import Dubbo
from pydantic import BaseModel
from pydantic_ai import Agent

from supply import ADDRESS, Forecast, Inventory, Purchasing, Suppliers

# A model as Pydantic AI names it, such as openai-chat:<model> for any service
# compatible with the Chat Completions API of OpenAI, or test for none.
MODEL = os.environ.get("MODEL")
REQUEST = "The sale starts in 7 days and lasts 3. Restock the EAST warehouse for it, within a budget of 20,000."


class Line(BaseModel):
    sku: str
    supplier: str
    quantity: int
    unit_price: float
    reason: str


class Plan(BaseModel):
    lines: list[Line]
    total: float
    notes: str


INSTRUCTIONS = """\
You plan the restocking of a warehouse before a sale. For each SKU running
low, forecast its sales until the sale ends, and order what its stock and the
goods in transit do not cover. Choose a supplier whose goods arrive before
the sale starts, the cheapest of those, and order at least its minimum. Keep
the total within the budget; when it does not fit, leave out what is least
needed. Say in each line why you chose it, and in the notes what you left out.
"""


async def main(request: str) -> None:
    app = Dubbo()
    inventory = app.refer(Inventory, url=ADDRESS)
    forecast = app.refer(Forecast, url=ADDRESS)
    suppliers = app.refer(Suppliers, url=ADDRESS)
    purchasing = app.refer(Purchasing, url=ADDRESS)

    # The methods of the references are the tools: their names, parameters
    # and docstrings are those of the contracts.
    agent = Agent(
        MODEL,
        instructions=INSTRUCTIONS,
        tools=[inventory.low_stock, forecast.predict, suppliers.quotes],
        output_type=Plan,
    )

    async with app:
        plan = (await agent.run(request)).output

        for line in plan.lines:
            print(
                f"{line.sku:<20} {line.quantity:>6} from {line.supplier:<16} at {line.unit_price:>7.2f}  {line.reason}"
            )
        print(f"Total {plan.total:,.2f}. {plan.notes}")

        # Writing is left to a person, not to the model.
        answer = await asyncio.to_thread(input, "Draft these purchase orders? [y/N] ")
        if answer.strip().lower() != "y":
            print("Nothing drafted")
            return

        for line in plan.lines:
            draft = await purchasing.draft(line.supplier, line.sku, line.quantity)
            print(f"Drafted {draft.id}: {draft.quantity} {draft.sku} from {draft.supplier}, {draft.total:,.2f}")


if __name__ == "__main__":
    if MODEL is None:
        sys.exit("Set MODEL to the model to plan with, such as openai-chat:<model>, or to test")
    asyncio.run(main(" ".join(sys.argv[1:]) or REQUEST))
