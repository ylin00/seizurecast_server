SeizureCast Server
====================
EEG Stream Processor, consuming EEG stream from Kafka and producing predicted results from given model.

Deployment: Running Kafka on EC2
--------------------------------

The real-time modeling will be done by EEGStreamProcessor.py.

1. Launch an EC2 Linux 18.04 (t2.micro is sufficient for demo)
1. Set up EC2 security group to allow SSH inbound from your local computer to the EC2 instance, following https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/get-set-up-for-amazon-ec2.html#create-a-base-security-group
1. Set up environment
    ```sh
    sudo apt-get install python3 python-dev python3-dev \
     build-essential libssl-dev libffi-dev \
     libxml2-dev libxslt1-dev zlib1g-dev \
     python3-pip
    ```
    * Note you may need to install Java 8 
      ```sh
      sudo apt update
      sudo apt install openjdk-8-jdk openjdk-8-jre cmake
      java -version
      ```
      ```sh
      openjdk version "1.8.0_292"
      OpenJDK Runtime Environment (build 1.8.0_292-8u292-b10-0ubuntu1~18.04-b10)
      OpenJDK 64-Bit Server VM (build 25.292-b10, mixed mode)
      ```
1. Install Apache Kafka following https://kafka.apache.org/quickstart
    
    * Install 
      ```sh
      wget https://downloads.apache.org/kafka/2.7.1/kafka_2.12-2.7.1.tgz
      tar -zxf kafka_2.12-2.7.1.tgz
      cd kafka_2.12-2.7.1
      ```
      
1. Start Zookeeper in an new tmux session
    ```sh
    # create a new tmux session
    tmux new -s zookeeper
    
    cd ~/kafka_2.12-2.7.1
    # Start the ZooKeeper service
    # Note: Soon, ZooKeeper will no longer be required by Apache Kafka.
    bin/zookeeper-server-start.sh config/zookeeper.properties
    
    # press Ctrl+B, then press D to detach 
    ```
    Running the following srvr command should return a list of the server details.
    ```sh
    echo srvr | nc localhost 2181
    
    Zookeeper version: 3.5.9-83df9301aa5c2a5d284a9940177808c01bc35cef, built on 01/06/2021 20:03 GMT
    Latency min/avg/max: 0/0/0
    Received: 1
    Sent: 0
    Connections: 1
    Outstanding: 0
    Zxid: 0x0
    Mode: standalone
    Node count: 5
    ```
    REF: http://zookeeper.apache.org/doc/r3.5.3-beta/zookeeperAdmin.html

1. Setting up Kafka

    Add the following line to `config/server.properties`
    ```sh
    cp config/server.properties config/server.properties.backup
    echo "advertised.listeners=PLAINTEXT://<your.public.IP>:9092" >> config/server.properties
    echo "listeners=PLAINTEXT://0.0.0.0:9092" >> config/server.properties
    ``` 
    
1. Start Kafka Server.
    ```sh
    tmux new -s kafka
    ```
    ```sh
    # First with the ```-daemon``` and make sure the server started.
    bin/kafka-server-start.sh -daemon config/server.properties
    # Then run the following.
    bin/kafka-server-start.sh config/server.properties
    ```
    Note you may want to limit the Kafka heap size before starting the server by 
    ```sh
    export KAFKA_HEAP_OPTS="-Xmx256M -Xms128M"
    ```
1. Test Kafka Server is up and running.
    ```
    bin/kafka-topics.sh --create --bootstrap-server localhost:9092 --replication-factor 1 --partitions 1 --topic testTopic
    ```
    Test producer is working by run the following lines and send any messages.
    ```
    bin/kafka-console-producer.sh --broker-list localhost:9092 --topic testTopic
    ```
    Test consumer is working.
    ```
    bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic testTopic --from-beginning
    ```
1. install remaining packages
    ```sh
    sudo apt install python3-pip
    pip3 install -r requirements.txt
    ```
1. Kafka & EC2 references
    REF0: https://dzone.com/articles/installing-and-running-kafka-on-an-aws-instance
    REF1: https://stackoverflow.com/questions/43565698/connecting-kafka-running-on-ec2-machine-from-my-local-machine
    REF2: https://medium.com/@maftabali2k13/setting-up-a-kafka-cluster-on-ec2-1b37144cb4e


Usage
-----
* Set up `config.ini` broker address to be YOUR_IP:9092
* launch server
  ```sh
  python3 EEGStreamProcessor.py -v config.ini model.pkl
  ```
