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
package org.apache.dubbo.samples;

import java.util.List;

import org.apache.dubbo.common.stream.StreamObserver;
import org.apache.dubbo.config.ApplicationConfig;
import org.apache.dubbo.config.ProtocolConfig;
import org.apache.dubbo.config.RegistryConfig;
import org.apache.dubbo.config.ServiceConfig;
import org.apache.dubbo.config.bootstrap.DubboBootstrap;
import org.apache.dubbo.rpc.RpcContext;

/** The Java provider: Greeter over Triple and UserService over Dubbo, registered in Nacos. */
public class JavaServer {

    static class GreeterImpl extends DubboGreeterTriple.GreeterImplBase {
        @Override
        public HelloReply sayHello(HelloRequest request) {
            System.out.println("[" + traceId() + "] sayHello(" + request.getName() + ")");
            return reply("Hello, " + request.getName() + ", from Java!");
        }

        @Override
        public void sayHelloStream(HelloRequest request, StreamObserver<HelloReply> replies) {
            for (int count = 1; count <= 3; count++) {
                replies.onNext(reply("Hello #" + count + ", " + request.getName() + ", from Java!"));
            }
            replies.onCompleted();
        }

        private static HelloReply reply(String message) {
            return HelloReply.newBuilder().setMessage(message).build();
        }
    }

    static class UserServiceImpl implements UserService {
        @Override
        public User getUser(long id) {
            System.out.println("[" + traceId() + "] getUser(" + id + ")");
            if (id != 1) {
                throw new IllegalArgumentException("no user has ID " + id);
            }
            return new User(1, "Alice", "alice@example.com");
        }
    }

    /** The trace id among the attachments that the caller sent with the call being served. */
    static String traceId() {
        return RpcContext.getServerAttachment().getAttachment("trace-id");
    }

    public static void main(String[] args) {
        ProtocolConfig triple = new ProtocolConfig("tri", 50052);
        ProtocolConfig dubbo = new ProtocolConfig("dubbo", 20881);

        ServiceConfig<DubboGreeterTriple.GreeterImplBase> greeter = new ServiceConfig<>();
        greeter.setInterface(Greeter.class);
        greeter.setRef(new GreeterImpl());
        // Each service on one protocol: Protobuf messages over Triple, Java objects over Dubbo.
        greeter.setProtocol(triple);

        ServiceConfig<UserService> users = new ServiceConfig<>();
        users.setInterface(UserService.class);
        users.setRef(new UserServiceImpl());
        users.setProtocol(dubbo);

        DubboBootstrap.getInstance()
                .application(new ApplicationConfig("java-server"))
                .registry(new RegistryConfig("nacos://127.0.0.1:8848"))
                .protocols(List.of(triple, dubbo))
                .service(greeter)
                .service(users)
                .start();
        System.out.println("Serving Greeter on port 50052 and UserService on port 20881; press Ctrl+C to stop");
        DubboBootstrap.getInstance().await();
    }
}
