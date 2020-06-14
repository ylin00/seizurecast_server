"""
EEG Stream Processor

Consuming EEG stream from Kafka and producing predicted results from given model.

Author:
    Yanxian Lin, Insight Health Data Science Fellow, Boston 2020
"""
# TODO: README
import argparse
import configparser
import ast
import pickle
from confluent_kafka import Producer, Consumer
from collections import deque
from time import time, sleep


__VERSION__ = 'v1.0.0'


#TODO: Make sure the preprocess is the same function used in model training.
from preprocess import bin_power, bin_power_avg


class EEGStreamProcessor:
    """EEG Stream Processor"""
    def __init__(self):
        # parse arguments
        args = self.parse_args()
        self.__verbose = args.verbose
        self.__model = args.model
        # parse config
        config = configparser.ConfigParser()
        config.read(args.config)

        self.INBOUND_TOPIC      = config['DEFAULT']['STREAMER_TOPIC']
        self.OUTBOUND_TOPIC      = config['DEFAULT']['CONSUMER_TOPIC']

        self.consumer = Consumer({
                'bootstrap.servers': config['DEFAULT']['KALFK_BROKER_ADDRESS'],
                'auto.offset.reset': 'earliest',
                'group.id': 'group',
                'client.id': 'client-local',
                'enable.auto.commit': True,
                'session.timeout.ms': 6000
        })
        """consumer that reads stream of EEG signal"""

        self.producer = Producer({'bootstrap.servers': config['DEFAULT']['KALFK_BROKER_ADDRESS']})
        """producer that produces predition results"""

        # Data related configs
        self.data_height = int(config['DATA']['num_channel'])
        self.data_width  = int(config['DATA']['sampling_rate'])

        # Processor related configs
        self.process_rate         = int(config['PROCESSOR']['streaming_rate'])
        """The number of data to process second."""
        self.max_process_duration    = int(config['PROCESSOR']['max_stream_duration'])
        self.n_msg_per_consume = int(self.data_width * 1)
        """The number of message to consume in batch"""

        self.delay_refresh_intv = 1 / self.process_rate
        """refresh interval in seconds."""

        self.__streamqueue = deque()
        # queue for raw data
        self.__data   = deque()
        self.__data_t = deque()
        # queue of processed_data
        self.__pdata   = deque()
        self.__pdata_t = deque()
        # queue of results
        self.__res   = deque()
        self.__res_t = deque()

        # Setup
        self.consumer.subscribe([self.INBOUND_TOPIC])
        with open(self.__model, 'rb') as fp:
            self.model = pickle.load(fp)

    def start(self):
        """Start streamer"""

        start_time = time()
        heart_beat = time()
        stream_delay = 0.8 / self.process_rate
        stream_count = 1

        nsamp = max(1, int(self.max_process_duration * self.process_rate))
        for isamp in range(0, nsamp):

            print(f'Cycle: {isamp}/{nsamp}') if self.__verbose else None
            self.read_in()
            self.preprocess()
            self.predict()
            self.publish()

            stream_delay, stream_count, heart_beat = self.sleep_and_sync(
                stream_delay, stream_count, heart_beat)

            # too long, shut down
            if time() - start_time > self.max_process_duration:
                break

    def read_in(self):
        """read stream from Kafka and append to streamqueue

        Returns:
            list of list: dataset (nchannel x nsample) or None
        """
        # If chunk size is too large, consume it multiple epochs
        chunk_size = self.data_width
        msgs = []
        while chunk_size > 100:
            msgs.extend(self.consumer.consume(num_messages=100, timeout=1))
            chunk_size -= 100
        msgs.extend(self.consumer.consume(num_messages=chunk_size, timeout=1))

        print(f"Received {str(len(msgs))} messages") if self.__verbose else None

        if msgs is None or len(msgs) <= 0:
            return None

        self.__streamqueue.extendleft(msgs)  # Enqueue

        if len(self.__streamqueue) < self.data_width:
            return None

        # Dequeue
        msgs__ = [self.__streamqueue.pop() for i in range(0, self.data_width)]

        timestamps, data = [], []
        for msg in msgs__:
            time, values = self.decode(msg.key(), msg.value())
            timestamps.append(time) if time is not None else None
            data.append(values) if time is not None else None
        #TODO:// assert there is not big time gap in the data

        if len(data) < self.data_width\
                :
            return None

        print(timestamps[0], data[0]) if self.__verbose else None

        data = tuple(zip(*data))
        self.__data.append(data)
        self.__data_t.append(timestamps[0])

        print(f"INFO: Sucessfully Read a chunk") if self.__verbose else None

    def preprocess(self):
        """preprocess data"""
        if len(self.__data) <= 0:
            self.__data.clear(), self.__data_t.clear()
            return None
        data = [self.__data.pop() for i in range(0, len(self.__data))]
        time = [self.__data_t.pop() for i in range(0, len(self.__data_t))]

        X = bin_power_avg(data, fsamp=self.data_width)
        self.__pdata.extendleft(X)
        self.__pdata_t.extendleft(time)

    def predict(self):
        if len(self.__pdata) <= 0:
            return None
        for i in range(0, len(self.__pdata)):
            processed_data = self.__pdata.pop()
            processed_t = self.__pdata_t.pop()
            try:
                predicted_rels = self.model.predict([processed_data])
            except ValueError:
                return None
            self.__res.appendleft(predicted_rels[0])
            self.__res_t.appendleft(processed_t)

    def publish(self):
        """publish predicted result"""
        for i in range(0, len(self.__res)):
            res = self.__res.pop()
            tim = self.__res_t.pop()
            joint_str = res
            #Fixme: ductape the model prediction should be restricted
            if res == 0:
                joint_str = 'bckg'
            elif res == 1:
                joint_str = 'pres'
            key = 'key'
            value = "{'t':%.6f,'v':["%float(tim)+"'"+joint_str+"'"+"]}"
            self.producer.produce(self.OUTBOUND_TOPIC, key=key, value=value)
            print(f'Published: {tim}, {res}') if self.__verbose else None

    def stop(self):
        self.consumer.close()
        pass

    def parse_args(self):
        parser = argparse.ArgumentParser(description=self.__doc__ + '\n' + __VERSION__)
        parser.add_argument("config", help="config file")
        parser.add_argument("model",  help="model.pkl to run prediction")
        parser.add_argument("-V", "--version", help="show program version",
                            action="version", version=__VERSION__)
        parser.add_argument("-v", "--verbose",
                            help="enable verbose mode",
                            action="store_true")
        # parser.set_defaults(verbose=False,
        #                     config='./config.ini',
        #                     model='./model.pkl')
        return parser.parse_args()

    @staticmethod
    def decode(key, value):
        """decode a message key and value and return list"""
        # TODO: if key is invalid then return None
        mydata = ast.literal_eval(value.decode("UTF-8"))
        return mydata['t'], mydata['v']

    def sleep_and_sync(self, sampling_delay, sampling_count, heart_beat):
        """Sleep and adjust the sampling delay

        Returns: tuple(float, int, float)
            sampling_delay, sampling_count, heart_beat
        """
        # Adhere to sampling frequency
        sleep(sampling_delay)
        sampling_count += 1

        # Adjust the sleeping interval every refresh_delay_interval seconds
        if sampling_count == (self.delay_refresh_intv * self.data_width / self.n_msg_per_consume):

            new_heartbeat = time()
            duration = new_heartbeat - heart_beat
            deviation = (self.delay_refresh_intv - duration) * 1000

            try:
                sampling_delay = sampling_delay + deviation / (
                        self.delay_refresh_intv * 1000) / self.data_width * 0.5
                # 0.5 = dampening factor
                if sampling_delay < 0:
                    raise ValueError
            except ValueError:
                sampling_delay = 0
                print(
                    "WARNING: NEW DELAY TIME INTERVAL WAS A NEGATIVE NUMBER. Setting to 0..")
            print(f"Deviation: {deviation:.2f} ms, new delay:"
                  f" {sampling_delay * 1000:.2f} ms.") if self.__verbose else None
            sampling_count = 0
            heart_beat = new_heartbeat

        return sampling_delay, sampling_count, heart_beat


    @property
    def _streamqueue(self):
        """Access to streamqueue"""
        return self.__streamqueue

    @property
    def _result(self):
        """Access to predicted results"""
        return self.__res


if __name__ == '__main__':
    esp = EEGStreamProcessor()
    esp.start()
    esp.stop()
