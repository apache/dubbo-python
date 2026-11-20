# Pydantic AI

An AI agent works by calling tools, and in a company the tools it needs are
the services the company already runs. This sample is an agent, built with
[Pydantic AI](https://ai.pydantic.dev/), that plans the restocking of a
warehouse before a sale. Its tools are the supply services of the company,
called over Dubbo: the methods of a reference are given to the agent as they
are, with no code between them.

```
                    tools                       Dubbo
  planner.py ───────────────────▶ Inventory.low_stock  ┐
  Pydantic AI agent             ▶ Forecast.predict     ├─▶ services.py
  + a model                     ▶ Suppliers.quotes     ┘
       │
       ▼ the plan, once a person agrees
  Purchasing.draft ─────────────────────────────────────▶ services.py
```

## What you will learn

- how the methods of a reference become the tools of an agent, with their
  names, parameters and descriptions taken from the contract;
- how to write a contract whose docstrings tell a model what each method does;
- why the agent only reads, and a person decides what is written;
- how to run it with any model that speaks the API of OpenAI, or with none.

## Before you start

```console
$ pip install apache-dubbo "pydantic-ai-slim[openai]"
```

You also need a model: any service compatible with the Chat Completions API
of OpenAI, which most providers and self-hosted servers such as vLLM and
Ollama offer, or another that Pydantic AI supports.

## The files

| File | Role |
|---|---|
| `supply.py` | The contracts of the four supply services and their types |
| `services.py` | The services, in one application, on port 20880, with the stock, sales and suppliers of a few SKUs |
| `planner.py` | The agent: it plans with three services as its tools, then drafts the orders once you agree |

## Run it

From this directory, start the services:

```console
$ python services.py
Serving inventory, forecast, suppliers and purchasing on port 20880; press Ctrl+C to stop
```

Then, in another terminal, say which model to use, and ask the agent for a
plan:

```console
$ export OPENAI_BASE_URL=https://... OPENAI_API_KEY=... MODEL=openai-chat:<model>
$ python planner.py
```

`OPENAI_BASE_URL` is the address of the service, ending as its documentation
says, often in `/v1`; `<model>` is a name it lists. The model must support
tool calls.

Without arguments, it asks for the sale this sample is set up for: "The sale
starts in 7 days and lasts 3. Restock the EAST warehouse for it, within a
budget of 20,000." Give your own request as the arguments instead.

`services.py` prints each call the agent makes, as the model chooses them:

```console
low_stock('EAST')
predict('TEA-OOLONG-250G', 10)
quotes('TEA-OOLONG-250G')
...
```

`planner.py` prints the plan, with the reason for each line, and asks before
it drafts the orders. The stock, sales and suppliers are set so that one plan
is right: 320 oolong tea from Fujian Hills, as Hangzhou Leaf is cheaper but
too slow for the sale; 285 flasks from Yongkang Steel; no mugs, as those in
transit cover the sale; 19,705.00 in all. Lower the budget, and the agent has
to choose what to leave out.

### Another model, or none

`MODEL` names the model as [Pydantic AI](https://ai.pydantic.dev/models/)
names them, so any model it supports may be given, with the settings its
page names. Set it to `test` to run without a model: the test model of
Pydantic AI calls each tool once, with arguments it makes up, which shows the
calls going through without an API key.

## How it works

### The agent loop

An agent runs a loop: it sends the request and the descriptions of its tools
to the model; the model answers with the tools to call; the agent calls them
and sends back what they return; and so on, until the model answers with the
result. `agent.run` is that loop, and each call of a tool is here a Dubbo
call. The result is a `Plan`, which Pydantic checks: when the model answers
with something else, the agent asks it again.

### Contracts as tools

A model chooses a tool by its name, its parameters and its description.
Pydantic AI takes them from the function it is given: its name, signature,
type annotations and docstring. Each method of a reference has those of the
method of the contract it calls, so `inventory.low_stock` is described as
`low_stock(warehouse: str)`, with the docstring of `Inventory.low_stock`, and
the parameters described under its `Args:`. The docstrings of `supply.py` are
therefore written for the model as much as for people. The same methods can
be given to other frameworks that describe tools by their functions, such as
LangChain, the OpenAI Agents SDK or an MCP server.

### Reading and writing

The tools of the agent only read. Drafting a purchase order is not one of
them: the agent plans, the plan is printed, and the orders are drafted by
`planner.py` itself once you answer `y`. A model may choose wrongly; what
changes the business stays with a person.

### The services behind the tools

The services serve over the Dubbo protocol, with Hessian 2 and Java class
names, as most Java services do, so in a company they may as well be Java
services, as [interop/java](../../interop/java) shows. Here the planner calls
them at their address; with a registry, it would find them by name, as in
[FastAPI](../fastapi).

## Next

- [FastAPI](../fastapi): services behind a web application.
- [Samples](../..): the other samples.
