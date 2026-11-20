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

import java.util.concurrent.CompletableFuture;

import org.apache.dubbo.common.stream.StreamObserver;
import org.apache.dubbo.config.ApplicationConfig;
import org.apache.dubbo.config.ReferenceConfig;
import org.apache.dubbo.config.RegistryConfig;
import org.apache.dubbo.config.bootstrap.DubboBootstrap;
import org.apache.dubbo.rpc.RpcContext;

/** The Java consumer: it finds the Python services in Nacos and calls them. */
public class JavaClient {

    public static void main(String[] args) throws Exception {
        ReferenceConfig<Greeter> greeterReference = new ReferenceConfig<>();
        greeterReference.setInterface(Greeter.class);
        ReferenceConfig<UserService> usersReference = new ReferenceConfig<>();
        usersReference.setInterface(UserService.class);

        DubboBootstrap.getInstance()
                .application(new ApplicationConfig("java-client"))
                .registry(new RegistryConfig("nacos://127.0.0.1:8848"))
                .reference(greeterReference)
                .reference(usersReference)
                .start();
        Greeter greeter = greeterReference.get();
        UserService users = usersReference.get();

        // An attachment set here goes with the next call only.
        RpcContext.getClientAttachment().setAttachment("trace-id", "java-7f3a");
        System.out.println(greeter.sayHello(HelloRequest.newBuilder().setName("Alice").build()).getMessage());
        CompletableFuture<Void> done = new CompletableFuture<>();
        greeter.sayHelloStream(HelloRequest.newBuilder().setName("Bob").build(), new StreamObserver<>() {
            @Override
            public void onNext(HelloReply reply) {
                System.out.println(reply.getMessage());
            }

            @Override
            public void onError(Throwable error) {
                done.completeExceptionally(error);
            }

            @Override
            public void onCompleted() {
                done.complete(null);
            }
        });
        done.get();

        RpcContext.getClientAttachment().setAttachment("trace-id", "java-7f3a");
        System.out.println(users.getUser(1));
        try {
            users.getUser(42);
        } catch (IllegalArgumentException error) {
            System.out.println(error);
        }
        // Exiting stops Dubbo through its shutdown hook.
        System.exit(0);
    }
}
