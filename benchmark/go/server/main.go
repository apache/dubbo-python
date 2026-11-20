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

// Dubbo Go serving the benchmark service over one protocol: the Bench
// service of bench.proto over Triple, or BenchService over Dubbo, whose
// echo carries bytes in Hessian 2.
package main

import (
	"context"
	"flag"
	"fmt"

	"dubbo.apache.org/dubbo-go/v3"
	_ "dubbo.apache.org/dubbo-go/v3/imports"
	"dubbo.apache.org/dubbo-go/v3/logger"
	"dubbo.apache.org/dubbo-go/v3/protocol"
	"dubbo.apache.org/dubbo-go/v3/server"

	"bench/benchpb"
)

type BenchImpl struct{}

func (BenchImpl) Echo(_ context.Context, request *benchpb.Payload) (*benchpb.Payload, error) {
	return request, nil
}

type BenchService struct{}

func (BenchService) Echo(_ context.Context, data []byte) ([]byte, error) {
	return data, nil
}

func main() {
	name := flag.String("protocol", "tri", "the protocol to serve: tri or dubbo")
	port := flag.Int("port", 50051, "the port to serve on")
	flag.Parse()

	serving := protocol.WithTriple()
	if *name != "tri" {
		serving = protocol.WithDubbo()
	}
	instance, err := dubbo.NewInstance(
		dubbo.WithName("bench-server"),
		dubbo.WithProtocol(serving, protocol.WithPort(*port)),
		dubbo.WithLogger(logger.WithLevel("warn")),
	)
	if err != nil {
		panic(err)
	}
	srv, err := instance.NewServer()
	if err != nil {
		panic(err)
	}
	if *name == "tri" {
		err = benchpb.RegisterBenchHandler(srv, BenchImpl{})
	} else {
		err = srv.RegisterService(
			BenchService{},
			server.WithInterface("org.apache.dubbo.benchmark.BenchService"),
			server.WithSerialization("hessian2"),
		)
	}
	if err != nil {
		panic(err)
	}
	fmt.Printf("Serving %s on port %d\n", *name, *port)
	if err := srv.Serve(); err != nil {
		panic(err)
	}
}
