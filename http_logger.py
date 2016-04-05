import curses
import re
import subprocess
import time
from collections import deque
from urlparse import urlparse
import threading
import itertools
import datetime
import sys
import traceback

p = re.compile(
    '([^ ]*) ([^ ]*) ([^ ]*) \[([^]]*)\] "([^"]*)" ([^ ]*) ([^ ]*)'
    )
def parse_line(line):
    host, ignore, user, date, request, status, size = p.match(line).groups()
    return host, ignore, user, date, request, status, size

class LogMonitor(object):
    def __init__(self, filename, threshold, polling_period = 1, time_period = 2 * 60):
        if time_period % polling_period:
            raise Exception("time period should be divisible by polling period")
        self.threshold = threshold
        self.time_period = time_period
        self.polling_period = polling_period
        self.hit_dict = {}
        self.f = subprocess.Popen(['tail','-F', '-n', '0', filename],\
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.analyze_thread = threading.Thread(target = self.analyze_lines)
        self.analyze_thread.daemon = True
        self.shift_thread = threading.Thread(target = self.shift_queue)
        self.shift_thread.daemon = True
        self.polling_period = polling_period

    def shift_queue(self):
        """shifts queue based on polling period to maintain updated traffic activity"""
        while True:
            start = time.time()
            self._shift()
            proc_time = time.time() - start
            time.sleep(self.polling_period - proc_time)

    def _shift(self):
        for queues in self.hit_dict.values():
            queues.append(0)
            queues.popleft()

    def analyze_lines(self):
        while True:
            line = self.f.stdout.readline()
            self.analyze(line)

    def analyze(self, line):
        host, ignore, user, date, request, status, size = parse_line(line)
        section_paths = request.split(" ")[1].split("/", 2)
        if len(section_paths) > 1:
            section = "%s/%s" %(host, section_paths[1])
        else:
            section = host
        
        if section not in self.hit_dict:
            self.hit_dict[section] = deque([0] * (self.time_period / self.polling_period))

        self.hit_dict[section][-1] += 1

    def check_threshold(self):
        avg = sum([sum(queue) for queue in self.hit_dict.values()]) / float(self.time_period / self.polling_period)
        return avg, avg >= self.threshold

    def run(self):
        """runs entire log monitoring process"""
        self.analyze_thread.start()
        self.shift_thread.start()
        num_slots = self.time_period / self.polling_period
        alert_last_int = False
        while True:
            start = time.time()
            avg, above_threshold = self.check_threshold()
            if above_threshold:
                yield (avg, "alert")
            elif alert_last_int:
                yield (avg, "alert_off")
            alert_last_int = above_threshold

            host_stats = [(host, sum(list(queue)[-1 * int(10 / self.polling_period):]) / (10.0 / self.polling_period)) for host, queue in self.hit_dict.items()]
            host_stats.sort(reverse = True, key = lambda x: x[1])
            
            yield (host_stats[:5], "top_5")
            proc_time = time.time() - start
            
            time.sleep(10)

def create_alert_msg(avg, timestamp):
    return "High traffic generated an alert - hits = %.2f triggered at time %s" % (avg, str(timestamp))

class Main(object):
    def __init__(self, fname):
        self.lm = LogMonitor(fname, 1, polling_period = 1, time_period = 10)
        self.top_5_start_point = 0
        
        self.MAX_ALERTS = 300 # alert history max
        self.alert_start_point = self.top_5_start_point + 8
        self.alert_frame_up = 0 # tracks movement on pad from left/right/up/down/keys
        self.alert_frame_left = 0
        self.alert_end_point = self.alert_start_point + 6

        self.MAX_GEN_PAD = 300 # sets how much history is stored although this number is a bit deceiving because I use spacing. TODO: remove spacing from general activity list
        
        self.general_frame_up = 0 #tracks movement on pad from left/right/up/down/keys
        self.general_frame_left = 0
        self.gen_stat_start_point = self.alert_start_point + 8

        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(1)
        self.log_update_thread = threading.Thread(target = self.consume_log, args = (self.stdscr,))
        self.log_update_thread.daemon = True
        max_y,max_x = self.stdscr.getmaxyx()
        self.alerts_pad = curses.newpad(self.MAX_ALERTS, 1000) #displays alerts
        self.general_pad = curses.newpad(self.MAX_GEN_PAD, 1000) #displays general activity
        self.alerts = [] #stores alert history
        self.general_status = [""] * self.MAX_GEN_PAD #stores general activity

    def consume_log(self, screen):
        """gets updates from the LogMonitor when available and displays them"""

        cur_status_size = len(self.general_status)
        for idx, msg in enumerate(self.lm.run()):
            max_y,max_x = screen.getmaxyx()
            screen.clear()
            self.alerts_pad.clear()
            self.general_pad.clear()
            for x, c in enumerate("Top 5 Sections Last Ten Seconds (hits/second):"):
                screen.addstr(self.top_5_start_point, x, c)
            if msg[1] == "top_5":
                hosts = msg[0]
                lnum = self.top_5_start_point + 1
                for host, avg_hit in hosts:
                    host_msg = "%s: %.2f" % (host, avg_hit)
                    for x, c in enumerate(host_msg):
                        screen.addstr(lnum, x, c)
                    lnum += 1

            elif msg[1] == "alert":
                timestamp = datetime.datetime.now()
                self.alerts.append((msg[0], timestamp))  #put in alert history
                gen_msg = create_alert_msg(msg[0], timestamp)
                self.general_status.append(gen_msg) #add to general status log

            elif msg[1] == "alert_off":
                self.general_status.append("Back to normal traffic levels, averaging %.2f hits/seconds now" % msg[0])

            for x, c in enumerate("Alerts History (threshold is %.2f hits/second):" % self.lm.threshold):
                screen.addstr(self.alert_start_point, x, c)

            for x, c in enumerate("General Status:"):
                screen.addstr(self.gen_stat_start_point, x, c)

            r = 0
            if len(self.alerts) > self.MAX_ALERTS: #remove oldest alert
                del self.alerts[0]
            for avg, timestamp in self.alerts[::-1]:
                msg = "%.2f at %s" % (avg, timestamp)
                for col, c in enumerate(msg):
                    self.alerts_pad.addstr(r, col, c)

                r += 1

            if len(self.general_status) == cur_status_size:
                self.general_status.append(" ")

            if len(self.general_status) >= self.MAX_GEN_PAD:
                del self.general_status[0]
                cur_status_size = len(self.general_status)

            gen_pad_start_point = self._calc_status_loc()
            for r, msg in enumerate(self.general_status):
                for col, c in enumerate(msg):
                    self.general_pad.addstr(r, col, c)

            screen.refresh()
            self.alerts_pad.refresh(self.alert_frame_up,0, self.alert_start_point + 1,0, self.alert_end_point,max_x-1)
            self.general_pad.refresh(gen_pad_start_point,self.general_frame_left, self.gen_stat_start_point + 1,0, max_y - 1,max_x-1)

    def _calc_status_loc(self):
        """gets which part of the general activity log to show"""
        max_y,_ = self.stdscr.getmaxyx()
        max_screen = max_y - self.gen_stat_start_point
        if len(self.general_status) > max_screen:
            gen_pad_start_point = len(self.general_status) - max_screen + 1 + self.general_frame_up
        else:
            gen_pad_start_point = 0
        return gen_pad_start_point

    def user_input(self):
        """
        allows user to scroll up and down on alert history and general history
        
        pressing "g" changes to scrolling for general activity
        pressing "a" changes to scrolling for alert activity
        """

        general_controls = False
        while True:
            ch = self.stdscr.getch()
            if ch == ord("g"): # general controls
                general_controls = True
            elif ch == ord("a"):
                general_controls = False
            max_y,max_x = self.stdscr.getmaxyx()            
            ch2 = self.stdscr.getch()
            if not general_controls:
                if ch2 == curses.KEY_DOWN and self.alert_frame_up < len(self.alerts):
                    self.alert_frame_up += 1
                elif ch2 == curses.KEY_UP and self.alert_frame_up > 0:
                    self.alert_frame_up -= 1
                self.alerts_pad.refresh(self.alert_frame_up,0, self.alert_start_point + 1,self.alert_frame_left, self.alert_end_point,max_x-1)
            else:
                if ch2 == curses.KEY_DOWN and self.general_frame_up < 0:
                    self.general_frame_up += 1
                elif ch2 == curses.KEY_UP:
                    self.general_frame_up -= 1
                elif ch2 == curses.KEY_LEFT and self.general_frame_left > 0:
                    self.general_frame_left -= 1
                elif ch2 == curses.KEY_RIGHT:
                    self.general_frame_left += 1
                gen_pad_start_point = self._calc_status_loc()
                self.general_pad.refresh(gen_pad_start_point,self.general_frame_left, self.gen_stat_start_point + 1,0, max_y - 1,max_x - 1)

    def run(self):
        """starts the whole shebang"""
        self.log_update_thread.start()
        self.user_input()

    def cleanup(self):
        """cleans up curses"""
        curses.nocbreak(); self.stdscr.keypad(0); curses.echo()
        curses.endwin()
        
if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print "Missing file name argument"
            exit(1)
        m = Main(sys.argv[1])
        m.run()

    except KeyboardInterrupt as e:
        m.cleanup()

    except Exception as e:
        traceback.print_exc()