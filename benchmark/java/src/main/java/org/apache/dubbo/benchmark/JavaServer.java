/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package org.apache.dubbo.benchmark;

import org.apache.dubbo.config.ApplicationConfig;
import org.apache.dubbo.config.ProtocolConfig;
import org.apache.dubbo.config.RegistryConfig;
import org.apache.dubbo.config.ServiceConfig;
import org.apache.dubbo.config.bootstrap.DubboBootstrap;

/**
 * Dubbo Java serving the benchmark service over one protocol: Bench of bench.proto over Triple, or BenchService over
 * Dubbo. It takes the protocol, tri or dubbo, and the port.
 */
public class JavaServer {

    static class BenchImpl extends DubboBenchTriple.BenchImplBase {
        @Override
        public Payload echo(Payload request) {
            return request;
        }
    }

    static class BenchServiceImpl implements BenchService {
        @Override
        public byte[] echo(byte[] data) {
            return data;
        }
    }

    public static void main(String[] args) {
        String protocol = args[0];
        ProtocolConfig serving = new ProtocolConfig(protocol, Integer.parseInt(args[1]));
        serving.setHost("127.0.0.1");

        ServiceConfig<Object> service = new ServiceConfig<>();
        if (protocol.equals("tri")) {
            service.setInterface(Bench.class);
            service.setRef(new BenchImpl());
        } else {
            service.setInterface(BenchService.class);
            service.setRef(new BenchServiceImpl());
        }

        ApplicationConfig application = new ApplicationConfig("bench-server");
        application.setQosEnable(false);
        DubboBootstrap.getInstance()
                .application(application)
                .registry(new RegistryConfig(RegistryConfig.NO_AVAILABLE))
                .protocol(serving)
                .service(service)
                .start();
        System.out.println("Serving " + protocol + " on port " + args[1]);
        DubboBootstrap.getInstance().await();
    }
}
