import requests
import yaml
import random
from datetime import datetime, timedelta
import json
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
import time

time_zone = 8  # 时区

# 两天后日期


def get_seats_with_config(user_cfg, seat_config):
    # 二楼东/二楼西/四楼/三楼大厅/守正书院/求新书院/自定义
    seat_type = user_cfg['type']
    if seat_type == "自定义":
        return cfg['自定义']
    return list(range(seat_config[seat_type]['start'], seat_config[seat_type]['end']))
class SeatAutoBooker:
    def __init__(self, booker_config):
        self.json = None
        self.resp = None
        self.user_data = None

        self.un = os.environ["SCHOOL_ID"].strip()  # 学号
        print("使用用户：{}".format(self.un))
        self.pd = os.environ["PASSWORD"].strip()  # 密码
        self.SCKey = None
        try:
            self.SCKey = os.environ["SCKEY"]
        except KeyError:
            print("没有Server酱的key,将不会推送消息")

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(service=Service('/usr/local/bin/chromedriver'), options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10, 0.5)
        self.cookie = None

        self.cfg = booker_config

    def book_favorite_seat(self, date_config, seat_config):
        """
        预约后天的座位
        :param start_hour: start time, for tomorrow.
        :param duration: dwell time (hours)
        :return: CODE, MASSAGE
        CODE: 'ok' for success
        """
        #判断是否到了预约时间
        # 阅览室晚上9点开始预约，自习室晚上8点半开始预约
        seat_type = seat_config[date_config['name']]["type"]
        if seat_type == "自习室":
            start_time = datetime.now().replace(hour=20, minute=30, second=0, microsecond=0)
            end_time = datetime.now().replace(hour=20, minute=45, second=0, microsecond=0)
        else:
            start_time = datetime.now().replace(hour=21, minute=0, second=0, microsecond=0)
            end_time = datetime.now().replace(hour=21, minute=15, second=0, microsecond=0)
        start_time = start_time - timedelta(minutes=self.cfg["cron-delta-minutes"])
        if datetime.now() < start_time or datetime.now() > end_time:
            return -1, "未到预约时间"
        #开始预约
        for tried_times in range(5):
            try:
                return self._book_favorite_seat(date_config, seat_config, tried_times)
            except Exception as e:
                print(e.__class__, "尝试第{}次".format(tried_times))
                time.sleep(1)


    def _book_favorite_seat(self, date_config, seat_config, tried_times=0):
        # 获取座位
        seats = get_seats_with_config(date_config, seat_config)
        # 相关post参数生成
        today_0_clock = datetime.strptime(datetime.now().strftime("%Y-%m-%d 00:00:00"), "%Y-%m-%d %H:%M:%S")
        book_time = today_0_clock + timedelta(days=2) + timedelta(hours=date_config['开始时间'])
        delta = book_time - self.start_time
        total_seconds = delta.days * 24 * 3600 + delta.seconds
        if date_config['name'] == '自定义' and tried_times<self.cfg["max-retry"]/3*2:
            seat = seats[0]
        else:
            seat = random.choice(seats)
        data = f"beginTime={total_seconds}&duration={3600 * date_config["持续小时数"]}&&seats[0]={seat}&seatBookers[0]={self.user_data['uid']}"

        # post
        headers = self.cfg["headers"]
        headers['Cookie'] = self.cookie
        print(data)
        self.resp = requests.post(self.book_url, data=data, headers=headers)
        self.json = json.loads(self.resp.text)
        return self.json["CODE"], self.json["MESSAGE"] + " 座位:{}".format(seat)

    def login(self):
        pwd_path_selector = """//*[@id="react-root"]/div/div/div[1]/div[2]/div/div[1]/div[2]/div/div/div/div/div[1]/div[2]/div/div[3]/div/div[2]/input"""
        button_path_selector = """//*[@id="react-root"]/div/div/div[1]/div[2]/div/div[1]/div[2]/div/div/div/div/div[1]/div[3]"""

        try:
            self.driver.get("https://hdu.huitu.zhishulib.com/")
            self.wait.until(EC.presence_of_element_located((By.NAME, "login_name")))
            self.wait.until(EC.presence_of_element_located((By.XPATH, pwd_path_selector)))
            self.wait.until(EC.presence_of_element_located((By.XPATH, button_path_selector)))
            self.driver.find_element(By.NAME, 'login_name').clear()
            self.driver.find_element(By.NAME, 'login_name').send_keys(self.un)  # 传送帐号
            self.driver.find_element(By.XPATH, pwd_path_selector).clear()
            self.driver.find_element(By.XPATH, pwd_path_selector).send_keys(self.pd)  # 输入密码
            self.driver.find_element(By.XPATH, button_path_selector).click()
            time.sleep(5)
            cookie_list = self.driver.get_cookies()
            self.cookie = ";".join([item["name"] + "=" + item["value"] + "" for item in cookie_list])
            self.headers['Cookie'] = self.cookie

        except Exception as e:
            print(e.__class__.__name__ + "无法登录")
            return -1
        return 0

    def get_user_info(self):
        # 获取UID
        headers = self.headers
        headers['Cookie'] = self.cookie
        try:
            resp = requests.get("https://hdu.huitu.zhishulib.com/Seat/Index/searchSeats?LAB_JSON=1",
                                headers=headers)
            self.user_data = resp.json()['DATA']
            _ = self.user_data['uid']
        except Exception as e:
            print(self.user_data)
            print(e.__class__.__name__ + ",获取用户数据失败")
            return -1
        print("获取用户数据成功")
        return 0

    def wechatNotice(self, message, desp=None):
        if self.SCKey != '':
            url = 'https://sctapi.ftqq.com/{0}.send'.format(self.SCKey)
            data = {
                'title': message,
                desp: desp,
            }
            try:
                r = requests.post(url, data=data)
                if r.json()["data"]["error"] == 'SUCCESS':
                    print("Server酱通知成功")
                else:
                    print("Server酱通知失败")
            except Exception as e:
                print(e.__class__, "推送服务配置错误")

def is_booking_enable(date_cfg):
    if date_cfg['启用']:
        return True
    return False

if __name__ == "__main__":
    with open("user_config.yml", 'r') as f_obj:
        user_cfg = yaml.safe_load(f_obj)
    with open("config/basic_config.yml", 'r') as f_obj:
        basic_config = yaml.safe_load(f_obj)
    with open("config/basic_config.yml", 'r') as f_obj:
        seat_config = yaml.safe_load(f_obj)

    the_day_after_tomorrow = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][(datetime.now().weekday() + 2) % 7]
    # 判断是否启用
    if not is_booking_enable(user_cfg[the_day_after_tomorrow]):
        print("预约未启用")
        exit(0)

    s = SeatAutoBooker()
    if not s.login() == 0:
        s.driver.quit()
        exit(-1)
    if not s.get_user_info() == 0:
        s.driver.quit()
        exit(-1)
    s.book_favorite_seat(date_config=user_cfg[the_day_after_tomorrow], seat_config=seat_config)
    s.driver.quit()
