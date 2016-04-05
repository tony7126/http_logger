import unittest
from http_logger import parse_line, LogMonitor

class TestAnalyzer(unittest.TestCase):

    def test_parse_line(self):
        sample_line = '127.0.0.1 user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
        assert parse_line(sample_line) == ('127.0.0.1', 'user-identifier', 'frank', '10/Oct/2000:13:55:36 -0700', 'GET /apache_pb.gif HTTP/1.0', '200', '2326')
        lm = LogMonitor("tests/helper_files/blank", 5, polling_period = 1, time_period = 1)
        lm.analyze(sample_line)

    def test_queue_sizes(self):
        sample_line = '127.0.0.1 user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
        lm = LogMonitor("tests/helper_files/blank", 5, polling_period = 1, time_period = 1)
        lm.analyze(sample_line)
        host = "127.0.0.1/apache_pb.gif"
        assert host in lm.hit_dict
        assert len(lm.hit_dict[host]) == 1
        lm = LogMonitor("tests/helper_files/blank", 5, polling_period = 1, time_period = 20)
        lm.analyze(sample_line)
        assert len(lm.hit_dict[host]) == 20
        lm = LogMonitor("tests/helper_files/blank", 5, polling_period = 10, time_period = 20)
        lm.analyze(sample_line)
        assert len(lm.hit_dict[host]) == 2

    def test_single_host_threshold(self):
        sample_line = '127.0.0.1 user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
        sample_line2 = 'http://google.com/bla/bla user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
        lm = LogMonitor("tests/helper_files/blank", 5, polling_period = 1, time_period = 1)
        lm.analyze(sample_line)
        
        avg, above_threshold = lm.check_threshold()
        assert not above_threshold
        
        for _ in xrange(3):
            lm.analyze(sample_line)

        avg, above_threshold = lm.check_threshold()
        assert not above_threshold

        lm.analyze(sample_line)
        avg, above_threshold = lm.check_threshold()
        assert above_threshold

        lm._shift()
        avg, above_threshold = lm.check_threshold()
        assert not above_threshold
        assert not avg

    def test_multiple_hosts_threshold(self):
        sample_line = '127.0.0.1 user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
        sample_line2 = 'http://google.com user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
        lm = LogMonitor("tests/helper_files/blank", 5, polling_period = 1, time_period = 2)
        for _ in xrange(2):
            lm.analyze(sample_line)
            lm.analyze(sample_line2)

        avg, above_threshold = lm.check_threshold()
        assert not above_threshold
        assert avg == 2

        for _ in xrange(6):
            lm.analyze(sample_line)
            lm.analyze(sample_line2)

        avg, above_threshold = lm.check_threshold()
        assert above_threshold
        print lm.hit_dict
        lm._shift()

        avg, above_threshold = lm.check_threshold()
        assert above_threshold
    
        lm._shift()

        avg, above_threshold = lm.check_threshold()
        assert not above_threshold

        for _ in xrange(16):
            lm.analyze(sample_line)


        avg, above_threshold = lm.check_threshold()
        assert above_threshold
        assert avg == 8

    def test_queue_thread_safety(self):
        pass

if __name__ == "__main__":
    unittest.main()