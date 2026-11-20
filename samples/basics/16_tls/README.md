# TLS and compression

Calls between services often cross networks that others share. TLS encrypts
them and proves who is at each end; mutual TLS lets the server check the
client too. This sample serves over mutual TLS, and compresses the messages.

## What you will learn

- how a provider serves over TLS, and requires client certificates;
- how a consumer trusts a server, and presents its certificate;
- how to compress the messages of Triple.

## Before you start

The sample makes its own certificate authority with
[trustme](https://github.com/python-trio/trustme), which is meant for tests:

```console
$ pip install trustme
$ python make_certificates.py
Wrote ca.pem, server.pem and client.pem to .../certs
```

## Run it

From this directory, start the server:

```console
$ python server.py
Serving over TLS on port 50051; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
With a client certificate: Hello, Alice, over TLS!
Without: UNAVAILABLE: the HTTP/2 connection is closed
```

## How it works

### TLS

`TLSConfig` secures every connection an application serves and opens, over
both protocols:

| Field | On a server | On a client |
|---|---|---|
| `certfile` | The certificate to present, required | The certificate to present when the server asks |
| `keyfile` | Its private key, unless `certfile` holds it | The same |
| `cafile` | The authorities whose clients it accepts; setting it requires client certificates | The authorities it trusts, instead of those of the system |
| `server_hostname` | — | The name the server certificate must carry, else the host it connects to |

The server certificate here names `localhost`, so the client connects to
`tri://localhost:50051`. A client without a certificate completes the
handshake, and the server then closes the connection, so the call fails as
`UNAVAILABLE`. For full control, `server_context` and `client_context` take
an `ssl.SSLContext` built in code.

In production, certificates come from your own authority, or from a service
mesh, and their files from the environment, such as
`DUBBO__TLS__CERTFILE`.

### Compression

`TripleConfig(compressor="gzip")` compresses the messages one side sends:
on the server, under its protocol; on the client, under the consumer or one
reference. A server compresses only for the callers that accept it, as gRPC
does. `deflate` and `bzip2` are built in too.

Compression saves bandwidth on large messages at the cost of CPU, and
rarely pays off on small ones.

## Next

- [17_generic](../17_generic): call a service without its contract.
