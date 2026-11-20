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

// The Go provider: Greeter over Triple, registered in Nacos.
package main

import (
	"context"
	"errors"
	"fmt"

	"dubbo.apache.org/dubbo-go/v3"
	_ "dubbo.apache.org/dubbo-go/v3/imports"
	"dubbo.apache.org/dubbo-go/v3/logger"
	"dubbo.apache.org/dubbo-go/v3/protocol"
	"dubbo.apache.org/dubbo-go/v3/protocol/triple/triple_protocol"
	"dubbo.apache.org/dubbo-go/v3/registry"

	"interop/greeter"
)

type GreeterImpl struct{}

func (GreeterImpl) SayHello(ctx context.Context, request *greeter.HelloRequest) (*greeter.HelloReply, error) {
	// The attachments that the caller sent arrive as the headers of the call.
	header, _ := triple_protocol.FromIncomingContext(ctx)
	fmt.Printf("[%s] SayHello(%s)\n", header.Get("trace-id"), request.Name)
	if request.Name == "" {
		return nil, triple_protocol.NewError(triple_protocol.CodeInvalidArgument, errors.New("a name is required"))
	}
	return &greeter.HelloReply{Message: fmt.Sprintf("Hello, %s, from Go!", request.Name)}, nil
}

func (GreeterImpl) SayHelloStream(
	_ context.Context, request *greeter.HelloRequest, stream greeter.Greeter_SayHelloStreamServer,
) error {
	for count := 1; count <= 3; count++ {
		reply := &greeter.HelloReply{Message: fmt.Sprintf("Hello #%d, %s, from Go!", count, request.Name)}
		if err := stream.Send(reply); err != nil {
			return err
		}
	}
	return nil
}

func main() {
	instance, err := dubbo.NewInstance(
		dubbo.WithName("go-server"),
		dubbo.WithRegistry(registry.WithNacos(), registry.WithAddress("127.0.0.1:8848")),
		dubbo.WithProtocol(protocol.WithTriple(), protocol.WithPort(50052)),
		dubbo.WithLogger(logger.WithLevel("warn")),
	)
	if err != nil {
		panic(err)
	}
	server, err := instance.NewServer()
	if err != nil {
		panic(err)
	}
	if err := greeter.RegisterGreeterHandler(server, GreeterImpl{}); err != nil {
		panic(err)
	}

	fmt.Println("Serving Greeter on port 50052; press Ctrl+C to stop")
	if err := server.Serve(); err != nil {
		panic(err)
	}
}
