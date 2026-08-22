from utils import AES_Encrypt, enc, generate_captcha_key, verify_param
import json
import requests
import re
import time
import logging
import datetime
from urllib3.exceptions import InsecureRequestWarning


def get_date(day_offset: int = 0):
    today = datetime.datetime.now().date()
    offset_day = today + datetime.timedelta(days=day_offset)
    tomorrow = offset_day.strftime("%Y-%m-%d")
    return tomorrow


class reserve:
    def __init__(
        self,
        sleep_time=0.2,
        max_attempt=50,
        enable_slider=False,
        reserve_next_day=False,
    ):
        self.login_page = (
            "https://passport2.chaoxing.com/mlogin"
            "?loginType=1&newversion=true&fid="
        )

        self.url = (
            "https://office.chaoxing.com/front/third/apps/seat/"
            "code?id={}&seatNum={}"
        )

        self.submit_url = (
            "https://office.chaoxing.com/data/apps/seat/submit"
        )

        self.seat_url = (
            "https://office.chaoxing.com/data/apps/seat/getusedtimes"
        )

        self.login_url = (
            "https://passport2.chaoxing.com/fanyalogin"
        )

        self.token = ""
        self.success_times = 0
        self.fail_dict = []
        self.submit_msg = []

        # 所有请求共用同一个 Session
        self.requests = requests.session()

        self.token_pattern = re.compile("token = '(.*?)'")

        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": (
                '"Google Chrome";v="125", '
                '"Chromium";v="125", '
                '"Not.A/Brand";v="24"'
            ),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
        }

        self.login_headers = {
            "Accept": (
                "application/json, text/javascript, */*; q=0.01"
            ),
            "accept-encoding": "gzip, deflate, br, zstd",
            "cache-control": "no-cache",
            "Connection": "keep-alive",
            "Accept-Language": (
                "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
            ),
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 "
                "like Mac OS X) AppleWebKit/603.1.3 "
                "(KHTML, like Gecko) Version/10.0 "
                "Mobile/14E304 Safari/602.1 "
                "wechatdevtools/1.05.2109131 "
                "MicroMessenger/8.0.5 "
                "Language/zh_CN webview/16364215743155638"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": (
                "application/x-www-form-urlencoded; charset=UTF-8"
            ),
            "Host": "passport2.chaoxing.com",
        }

        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day

        requests.packages.urllib3.disable_warnings(
            InsecureRequestWarning
        )

    # 获取预约页面的 token
    def _get_page_token(self, url, require_value=False):
        response = self.requests.get(
            url=url,
            verify=False,
        )

        html = response.content.decode("utf-8")

        matches = re.findall(
            r'id="submit_enc"\s+value="(.*?)"',
            html,
        )

        value_matches = None

        if require_value:
            value_matches = re.findall(
                r'value="(.*?)"',
                html,
            )

            if not matches:
                logging.error(
                    f"Failed to get token from {url}"
                )
                return "", ""

            if not value_matches:
                logging.error(
                    f"Failed to get submit value from {url}"
                )
                return matches[0], ""

        token = matches[0] if matches else ""
        value = value_matches[0] if value_matches else ""

        return token, value

    # 初始化登录 Session
    def get_login_status(self):
        self.requests.headers = self.login_headers

        self.requests.get(
            url=self.login_page,
            verify=False,
        )

    # 登录
    def login(self, username, password):
        username = AES_Encrypt(username)
        password = AES_Encrypt(password)

        parm = {
            "fid": -1,
            "uname": username,
            "password": password,
            "refer": (
                "http%3A%2F%2Foffice.chaoxing.com%2Ffront"
                "%2Fthird%2Fapps%2Fseat%2Fcode"
                "%3Fid%3D4219%26seatNum%3D380"
            ),
            "t": True,
        }

        response = self.requests.post(
            url=self.login_url,
            params=parm,
            verify=False,
        )

        result = response.json()

        if result["status"]:
            logging.info(
                f"User {username} login successfully"
            )
            return True, ""

        logging.info(
            f"User {username} login failed. "
            f"Please check your password and username!"
        )

        return False, result["msg2"]

    # 获取 roomid
    def roomid(self, encode):
        url = (
            "https://office.chaoxing.com/data/apps/seat/"
            "room/list?cpage=1&pageSize=100"
            "&firstLevelName=&secondLevelName="
            "&thirdLevelName=&deptIdEnc="
            f"{encode}"
        )

        json_data = self.requests.get(
            url=url
        ).content.decode("utf-8")

        original_data = json.loads(json_data)

        for item in original_data["data"]["seatRoomList"]:
            info = (
                f'{item["firstLevelName"]}-'
                f'{item["secondLevelName"]}-'
                f'{item["thirdLevelName"]} '
                f'id为：{item["id"]}'
            )

            print(info)

    # 处理滑块验证码
    def resolve_captcha(self):
        logging.info("Start to resolve captcha token")

        captcha_token, bg, tp = (
            self.get_slide_captcha_data()
        )

        logging.info(
            "Successfully get prepared "
            f"captcha_token {captcha_token}"
        )

        logging.info(
            f"Captcha Image URL-small {tp}, URL-big {bg}"
        )

        x = self.x_distance(bg, tp)

        logging.info(
            "Successfully calculate "
            f"the captcha distance {x}"
        )

        params = {
            "callback": (
                "jQuery33109180509737430778_1716381333117"
            ),
            "captchaId": (
                "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1"
            ),
            "type": "slide",
            "token": captcha_token,
            "textClickArr": json.dumps([{"x": x}]),
            "coordinate": json.dumps([]),
            "runEnv": "10",
            "version": "1.1.18",
            "_": int(time.time() * 1000),
        }

        response = self.requests.get(
            (
                "https://captcha.chaoxing.com/captcha/"
                "check/verification/result"
            ),
            params=params,
            headers=self.headers,
        )

        text = response.text.replace(
            (
                "jQuery33109180509737430778_"
                "1716381333117("
            ),
            "",
        ).replace(")", "")

        data = json.loads(text)

        logging.info(
            f"Successfully resolve the captcha token {data}"
        )

        try:
            extra_data = json.loads(data["extraData"])
            validate_value = extra_data["validate"]
            return validate_value
        except (KeyError, TypeError, json.JSONDecodeError):
            logging.info(
                "Can't load validate value. "
                "Maybe server returned a mistake."
            )
            return ""

    # 获取滑块验证码图片
    def get_slide_captcha_data(self):
        url = (
            "https://captcha.chaoxing.com/captcha/"
            "get/verification/image"
        )

        timestamp = int(time.time() * 1000)

        captcha_key, token = generate_captcha_key(
            timestamp
        )

        referer = (
            "https://office.chaoxing.com/front/third/"
            "apps/seat/code?id=3993&seatNum=0199"
        )

        params = {
            "callback": (
                "jQuery33107685004390294206_1716461324846"
            ),
            "captchaId": (
                "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1"
            ),
            "type": "slide",
            "version": "1.1.18",
            "captchaKey": captcha_key,
            "token": token,
            "referer": referer,
            "_": timestamp,
            "d": "a",
            "b": "a",
        }

        response = self.requests.get(
            url=url,
            params=params,
            headers=self.headers,
        )

        content = response.text

        data = content.replace(
            (
                "jQuery33107685004390294206_"
                "1716461324846("
            ),
            "",
        ).replace(")", "")

        data = json.loads(data)

        captcha_token = data["token"]

        bg = data[
            "imageVerificationVo"
        ]["shadeImage"]

        tp = data[
            "imageVerificationVo"
        ]["cutoutImage"]

        return captcha_token, bg, tp

    # 计算滑块距离
    def x_distance(self, bg, tp):
        import numpy as np
        import cv2

        def cut_slide(slide):
            slider_array = np.frombuffer(
                slide,
                np.uint8,
            )

            slider_image = cv2.imdecode(
                slider_array,
                cv2.IMREAD_UNCHANGED,
            )

            slider_part = slider_image[:, :, :3]
            mask = slider_image[:, :, 3]

            mask[mask != 0] = 255

            x, y, width, height = cv2.boundingRect(
                mask
            )

            cropped_image = slider_part[
                y:y + height,
                x:x + width,
            ]

            return cropped_image

        captcha_headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha-b.chaoxing.com",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": (
                '"Google Chrome";v="125", '
                '"Chromium";v="125", '
                '"Not.A/Brand";v="24"'
            ),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }

        bg_response = self.requests.get(
            bg,
            headers=captcha_headers,
        )

        tp_response = self.requests.get(
            tp,
            headers=captcha_headers,
        )

        bg_content = bg_response.content
        tp_content = tp_response.content

        bg_image = cv2.imdecode(
            np.frombuffer(
                bg_content,
                np.uint8,
            ),
            cv2.IMREAD_COLOR,
        )

        tp_image = cut_slide(tp_content)

        bg_edge = cv2.Canny(
            bg_image,
            100,
            200,
        )

        tp_edge = cv2.Canny(
            tp_image,
            100,
            200,
        )

        bg_picture = cv2.cvtColor(
            bg_edge,
            cv2.COLOR_GRAY2RGB,
        )

        tp_picture = cv2.cvtColor(
            tp_edge,
            cv2.COLOR_GRAY2RGB,
        )

        result = cv2.matchTemplate(
            bg_picture,
            tp_picture,
            cv2.TM_CCOEFF_NORMED,
        )

        _, _, _, max_location = cv2.minMaxLoc(
            result
        )

        return max_location[0]

    # 把单座位或多座位统一转换成列表
    @staticmethod
    def _normalize_seat_ids(seatid):
        if isinstance(seatid, str):
            seats = [seatid]
        elif isinstance(seatid, (list, tuple)):
            seats = list(seatid)
        else:
            raise TypeError(
                "seatid 必须是字符串、列表或元组"
            )

        normalized = []

        for seat in seats:
            if not isinstance(seat, str):
                raise TypeError(
                    "每个座位号都必须是字符串，"
                    "例如 '006'"
                )

            seat = seat.strip()

            # 去除空座位和重复座位
            if seat and seat not in normalized:
                normalized.append(seat)

        if not normalized:
            raise ValueError(
                "没有配置有效的座位号"
            )

        return normalized

    # 按优先顺序轮询所有备选座位
    def submit(
        self,
        times,
        roomid,
        seatid,
        action,
    ):
        seats = self._normalize_seat_ids(seatid)

        logging.info(
            f"本次备选座位：{seats}"
        )

        # self.max_attempt 表示最大轮询次数
        # 每一轮都会依次尝试所有备选座位
        for attempt in range(
            1,
            self.max_attempt + 1,
        ):
            for seat_index, seat in enumerate(
                seats
            ):
                logging.info(
                    f"第 {attempt}/{self.max_attempt} 轮，"
                    f"尝试座位 {seat}，"
                    f"当前优先级 "
                    f"{seat_index + 1}/{len(seats)}"
                )

                page_url = self.url.format(
                    roomid,
                    seat,
                )

                token, value = self._get_page_token(
                    page_url,
                    require_value=True,
                )

                logging.info(
                    f"Get token: {token}"
                )

                if self.enable_slider:
                    captcha = self.resolve_captcha()
                else:
                    captcha = ""

                logging.info(
                    f"Captcha token {captcha}"
                )

                success = self.get_submit(
                    self.submit_url,
                    times=times,
                    token=token,
                    roomid=roomid,
                    seatid=seat,
                    captcha=captcha,
                    action=action,
                    value=value,
                )

                # 任意一个座位成功后立即停止
                if success:
                    logging.info(
                        f"座位 {seat} 预约成功"
                    )
                    return True

                logging.info(
                    f"座位 {seat} 本次预约失败，"
                    "继续尝试下一个备选座位"
                )

                is_last_try = (
                    attempt == self.max_attempt
                    and seat_index == len(seats) - 1
                )

                # 最后一次尝试结束后不需要再等待
                if not is_last_try:
                    time.sleep(self.sleep_time)

        logging.info(
            "所有备选座位均预约失败"
        )

        return False

    # 向服务器提交预约
    def get_submit(
        self,
        url,
        times,
        token,
        roomid,
        seatid,
        captcha="",
        action=False,
        value="",
    ):
        delta_day = (
            1 if self.reserve_next_day else 0
        )

        day = (
            datetime.date.today()
            + datetime.timedelta(
                days=delta_day
            )
        )

        # GitHub Actions 使用 UTC 时区
        if action:
            day = (
                datetime.date.today()
                + datetime.timedelta(
                    days=1 + delta_day
                )
            )

        parameters = {
            "roomId": roomid,
            "startTime": times[0],
            "endTime": times[1],
            "day": str(day),
            "seatNum": seatid,
            "captcha": captcha,
            "token": token,
            "type": "1",
            "verifyData": "1",
        }

        logging.info(
            f"submit parameter {parameters}"
        )

        parameters["enc"] = verify_param(
            parameters,
            value,
        )

        response = self.requests.post(
            url=url,
            params=parameters,
            verify=True,
        )

        html = response.content.decode("utf-8")

        result = json.loads(html)

        self.submit_msg.append(
            times[0]
            + "~"
            + times[1]
            + ":  "
            + str(result)
        )

        logging.info(result)

        return result["success"]
