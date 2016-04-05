import time
import os
import random

hosts = ["172.0.0.1", "9.9.1.1", "http://google.com", "http://mysite.com"]
paths = ["/multiple/layer/path?with_some_arg=1", "/single_path", "/", "?no_path_args=4"]

if __name__ == "__main__":
	baseline_sample = '%(host)s user-identifier frank [10/Oct/2000:13:55:36 -0700] "GET %(path)s HTTP/1.0" 200 2326'
	try:
		while True:
			with open("test_log", "a") as f:
				l = baseline_sample % {"host": random.choice(hosts), "path": random.choice(paths)}
				f.write(l)
				f.write("\n")

			time.sleep(.1)
		os.remove("test_log")
	except KeyboardInterrupt:
		os.remove("test_log")
