# MetadataService 1.0.0 values

`org.apache.dubbo.metadata.MetadataInfo` values in Hessian 2.0, as the
MetadataService 1.0.0 returns them from `getMetadataInfo(String)`.

Peer: Apache Dubbo 3.3.6 (`org.apache.dubbo:dubbo:3.3.6`) with
`org.apache.dubbo:hessian-lite:4.0.4`, on Eclipse Temurin 21.
Captured on 2026-11-14 with the Java program in `Capture.java.txt`:

    CP=/root/.m2/repository/org/apache/dubbo/dubbo/3.3.6/dubbo-3.3.6.jar:/root/.m2/repository/org/apache/dubbo/hessian-lite/4.0.4/hessian-lite-4.0.4.jar
    docker run --rm --network none -v ~/.m2:/root/.m2:ro -v "$PWD":/w -w /w maven:3.9-eclipse-temurin-21 \
      sh -c "cp Capture.java.txt Capture.java && javac -cp $CP Capture.java && java -cp $CP:. Capture metadata_info_java.hessian metadata_info_python.hessian"

- `metadata_info_java.hessian`: what Java writes for the metadata of
  `demo-provider` at revision `b7b1f9e4c0d8a3d6e5f2a1b0c9d8e7f6`, with
  `g1/org.apache.dubbo.demo.DemoService:1.0.0:dubbo` on port 20880 and
  `org.apache.dubbo.demo.GreeterService:tri` without group, version or port.
- `metadata_info_python.hessian`: what `MetadataServiceV1Server` writes for
  the metadata of `orders-app` serving `g1/com.example.OrderService:2.0.0:dubbo`
  and `com.example.Health:dubbo` on port 20881. Java read it back as:

      app=orders-app revision=265ea22115086ffa295b1c5ffa5dfaba
      com.example.Health:dubbo -> name=com.example.Health group=null version=null protocol=dubbo port=20881 path=com.example.Health params={} matchKey=com.example.Health:dubbo
      g1/com.example.OrderService:2.0.0:dubbo -> name=com.example.OrderService group=g1 version=2.0.0 protocol=dubbo port=20881 path=com.example.OrderService params={application=orders-app, methods=find,list, side=provider} matchKey=g1/com.example.OrderService:2.0.0:dubbo
