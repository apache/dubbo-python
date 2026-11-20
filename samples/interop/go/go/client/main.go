// Licensed to the Apache Software Foundation (ASF) under one
// or more contributor license agreements. See the NOTICE file
// distributed with this work for additional information
// regarding copyright ownership. The ASF licenses this file
// to you under the Apache License, Version 2.0 (the
// "License"); you may not use this file except in compliance
// with the License. You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an
// "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, either express or implied. See the License for the
// specific language governing permissions and limitations
// under the License.

// The Go consumer: it finds the Python service in Nacos and calls it.
package main

import (
	"context"
	"fmt"

	"dubbo.apache.org/dubbo-go/v3"
	_ "dubbo.apache.org/dubbo-go/v3/imports"
	"dubbo.apache.org/dubbo-go/v3/logger"
	"dubbo.apache.org/dubbo-go/v3/protocol/triple/triple_protocol"
	"dubbo.apache.org/dubbo-go/v3/registry"

	"interop/greeter"
)

func main() {
	instance, err := dubbo.NewInstance(
		dubbo.WithName("go-client"),
		dubbo.WithRegistry(registry.WithNacos(), registry.WithAddress("127.0.0.1:8848")),
		dubbo.WithLogger(logger.WithLevel("warn")),
	)
	if err != nil {
		panic(err)
	}
	client, err := instance.NewClient()
	if err != nil {
		panic(err)
	}
	service, err := greeter.NewGreeter(client)
	if err != nil {
		panic(err)
	}
	// Every call made with this context attaches the trace id.
	ctx := triple_protocol.AppendToOutgoingContext(context.Background(), "trace-id", "go-1c9d")

	reply, err := service.SayHello(ctx, &greeter.HelloRequest{Name: "Alice"})
	if err != nil {
		panic(err)
	}
	fmt.Println(reply.Message)

	stream, err := service.SayHelloStream(ctx, &greeter.HelloRequest{Name: "Bob"})
	if err != nil {
		panic(err)
	}
	for stream.Recv() {
		fmt.Println(stream.Msg().Message)
	}
	if err := stream.Err(); err != nil {
		panic(err)
	}
}
