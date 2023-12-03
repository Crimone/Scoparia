import requests
import yaml
import json
import re
import time
import smtplib
import argparse
import logging
import threading
from urllib.parse import urlparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta, timezone


def create_requests_session():
    session_ = requests.Session()
    retries = Retry(
        total=10, backoff_factor=0.4, status_forcelist=[429, 500, 502, 503, 504]
    )
    session_.mount("http://", HTTPAdapter(max_retries=retries))
    session_.mount("https://", HTTPAdapter(max_retries=retries))
    return session_


class WikidotScraper:
    def __init__(self, config):
        self.config = config
        self.s = create_requests_session()

    def get_post_ids(self):
        lookup = self.s.get(
            "https://www.wikidot.com/quickmodule.php?"
            "module=UserLookupQModule&q=" + self.config["wikidot"]["username"]
        ).json()
        if (
            not lookup["users"]
            or lookup["users"][0]["name"] != self.config["wikidot"]["username"]
        ):
            raise ValueError("Username Not Found")
        user_id = lookup["users"][0]["user_id"]

        headers = {
            "Host": "www.wikidot.com",
            "Origin": "https://www.wikidot.com",
            "Pragma": "no-cache",
            "Referer": f"https://www.wikidot.com/user:info/{self.config['wikidot']['username']}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            "X-Requested-With": "XMLHttpRequest",
        }

        # 获取cookie

        self.s.get(
            f"https://www.wikidot.com/user:info/{self.config['wikidot']['username']}"
        )

        index = 1

        page_ids = []

        while True:
            # 发送 POST 请求
            response = self.s.post(
                "https://www.wikidot.com/ajax-module-connector.php",
                headers=headers,
                data={
                    "page": str(index),
                    "perpage": "200",
                    "userId": user_id,
                    "options": '{"new":true}',
                    "moduleName": "userinfo/UserChangesListModule",
                    "wikidot_token7": self.s.cookies.get(
                        "wikidot_token7", domain="www.wikidot.com"
                    ),
                },
            )

            response_json = json.loads(response.text)
            html_content = response_json["body"]
            # Parsing the HTML content
            soup = BeautifulSoup(html_content, "html.parser")
            # Finding the specified element
            target_elements = soup.select("td.title a")

            if target_elements:
                for target_element in target_elements:
                    href = target_element.get("href")
                    if urlparse(href).hostname == "scp-wiki-cn.wikidot.com":
                        page_ids.append(urlparse(href).path[1:])
                index += 1
            else:
                break

        data_to_save = {"page_ids": page_ids}

        with open(self.config["settings"]["history_path"], "w", encoding="utf-8") as file:
            json.dump(data_to_save, file, indent=4)

        print("发文记录遍历完成！")


class RssChecker:
    def __init__(self, config):
        self.config = config
        self.s = create_requests_session()

    def wikidot_login(self):
        self.s.post(
            "https://www.wikidot.com/default--flow/login__LoginPopupScreen",
            data=dict(
                login=self.config["wikidot"]["username"],
                password=self.config["wikidot"]["password"],
                action="Login2Action",
                event="login",
            ),
        )

    def check_post(self,article,rss_history):
        
        title = article.find("title").text
        link = article.find("link").text
        author_name = article.find("wikidot:authorName").text
        content = article.find("content:encoded").text.strip()
        publish_date = article.find("pubDate").text

        post_id = urlparse(link).fragment[5:]

        publish_time = datetime.strptime(publish_date, "%a, %d %b %Y %H:%M:%S %z")

        current_time = datetime.now(timezone.utc)
        # 计算时间差
        time_difference = (current_time - publish_time).total_seconds()

        if post_id in rss_history:
            return

        # 大于五倍rss周期直接忽略
        if time_difference > 5 * (self.config["settings"]["rss_routine"]):
            rss_history[post_id] = "超过最长处理周期"
            with open(self.config["settings"]["rss_history_path"], "w", encoding="utf-8") as file:
                json.dump(rss_history, file, ensure_ascii=False, indent=4)
            return

        tid = re.search(r"/t-(\d+)/", urlparse(link).path).group(1)
        self.wikidot_login()

        # 获取cookie

        reply_post_req = self.s.get(link)

        headers = {
            "Host": "scp-wiki-cn.wikidot.com",
            "Origin": "https://scp-wiki-cn.wikidot.com",
            "Pragma": "no-cache",
            "Referer": f"https://scp-wiki-cn.wikidot.com{urlparse(link).path}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            "X-Requested-With": "XMLHttpRequest",
        }

        # 发送 POST 请求
        response = self.s.post(
            "https://scp-wiki-cn.wikidot.com/ajax-module-connector.php",
            headers=headers,
            data={
                "postId": post_id,
                "t": tid,
                "order": "",
                "moduleName": "forum/ForumViewThreadPostsModule",
                "wikidot_token7": self.s.cookies.get(
                    "wikidot_token7", domain="scp-wiki-cn.wikidot.com"
                ),
            },
        )

        response_json = json.loads(response.text)
        html_content = response_json["body"]
        # Parsing the HTML content
        soup = BeautifulSoup(html_content, "html.parser")
        # Finding the specified element
        target_element = soup.find(
            "div", {"class": "post-container", "id": f"fpc-{post_id}"}
        )

        parents = target_element.find_parents()

        with open(self.config["settings"]["history_path"], "r", encoding="utf-8") as file:
            data_loaded = json.load(file)

        page_ids = data_loaded.get("page_ids", [])

        # 首先检查最新的回复的所有父元素在不在post_ids中

        for parent in parents:
            parent_id = parent.get("id")

            if parent_id:

                parent_usertag = parent.select_one(f'div#{parent_id.replace("fpc-", "post-")} .short span.printuser.avatarhover a:last-child')

                if parent_usertag and parent_usertag.text == self.config["wikidot"]["username"]:

                    parent_content = parent.find("div", {"id": parent_id.replace("fpc-", "post-content-")})
                    body=MIMEText(f'<div>{author_name}回复了你的帖子</div><p><a href="{link}">{link}</a></p>' + '<div style="border:1px dashed #999;background-color:#f4f4f4;padding:1em;">' + content.strip() + '</div>' + f'<div style="border:1px dashed #999;background-color:#f4f4f4;padding:0 1em;margin:1em 3em;">{str(parent_content)}</div>', "html")
                    self.email_ntfy(
                        f"{author_name}回复你: {title}……", body
                    )
                    rss_history[post_id] = "已发送提醒邮件"
                    with open(self.config["settings"]["rss_history_path"], "w", encoding="utf-8") as file:
                        json.dump(rss_history, file, ensure_ascii=False, indent=4)
                    return

        # 之后检查整个回复帖的作者

        soup = BeautifulSoup(reply_post_req.text, "html.parser")
        username_tag = soup.select_one(
            ".description-block.well .statistics span.printuser a:last-child"
        )
        if username_tag and username_tag.text == self.config["wikidot"]["username"]:

            body=MIMEText(f'<div>{author_name}回复了你的主题</div><p><a href="{link}">{link}</a></p>' + '<div style="border:1px dashed #999;background-color:#f4f4f4;padding:1em;">' + content.strip() + '</div>', "html")

            self.email_ntfy(f"{author_name}回复你: {title}……", body)
            rss_history[post_id] = "已发送提醒邮件"
            with open(self.config["settings"]["rss_history_path"], "w", encoding="utf-8") as file:
                json.dump(rss_history, file, ensure_ascii=False, indent=4)
            return

        # 最后检查所回复的文档

        if (
            urlparse(link).path.split("/")[-1]
            and urlparse(link).path.split("/")[-1] in page_ids
        ):

            body=MIMEText(f'<div>{author_name}评论了你的文档</div><p><a href="{link}">{link}</a></p>' + '<div style="border:1px dashed #999;background-color:#f4f4f4;padding:1em;">' + content.strip() + '</div>', "html")

            self.email_ntfy(f"{author_name}回复你: {title}……", body)
            rss_history[post_id] = "已发送提醒邮件"
            with open(self.config["settings"]["rss_history_path"], "w", encoding="utf-8") as file:
                json.dump(rss_history, file, ensure_ascii=False, indent=4)
            return

    def check_rss_posts(self):
        # Logfile Save Location
        req = requests.get(self.config["wikidot"]["feed_url"])
        rss_content = BeautifulSoup(req.content, "lxml-xml")
        articles = rss_content.findAll("item")

        rss_history = {}

        with open(self.config["settings"]["rss_history_path"], "r", encoding="utf-8") as file:
            rss_history = json.load(file)

        for a in articles:
            self.check_post(article=a,rss_history=rss_history)

    def email_ntfy(self, title, body):
        # 邮件内容
        subject = title
        # 创建 MIME 对象
        msg = MIMEMultipart()
        msg["From"] = self.config["email"]["from_email"]
        msg["To"] = self.config["email"]["to_email"]
        msg["Subject"] = subject

        # 添加邮件正文
        msg.attach(body)
 
        # 连接到 SMTP 服务器
        server = smtplib.SMTP(
            self.config["email"]["smtp_server"], self.config["email"]["smtp_port"]
        )
        server.starttls()  # 启动TLS加密
        server.login(
            self.config["email"]["from_email"], self.config["email"]["password"]
        )

        # 发送邮件
        server.send_message(msg)

        # 关闭连接
        server.quit()

def run_wikidot_scraper(config, is_routine = False):
    try:
        scraper = WikidotScraper(config)
        scraper.get_post_ids()
    except Exception as e:
        logging.warning(f"Wikidot Scraper 错误: {e}")
    finally:
        if is_routine:
            threading.Timer(config["settings"]["wikidot_routine"], run_wikidot_scraper, [config]).start()

def run_rss_checker(config, is_routine = False):
    try:
        comparer = RssChecker(config)
        comparer.check_rss_posts()
    except Exception as e:
        logging.warning(f"RSS Checker 错误: {e}")
    finally:
        if is_routine:
            threading.Timer(config["settings"]["rss_routine"], run_rss_checker, [config]).start()


def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='''SCP 回复提醒系统\n
        作者：Mercuresphere\n
        因为某些原因，本软件完全没有异常处理系统，请谅解。（反正所有异常都是warning，没什么问题的）\n
        在使用之前请先打开config.yaml文件，按其中注释编辑好。\n
        初次使用请运行: python scp_notify.py init 建立发文记录数据库，发文记录数据库默认半小时更新一次，可手动运行init来更新。\n
        发文记录数据库建立完毕之后运行: python scp_notify.py rss 启动RSS回复提醒系统。
        '''
    )

    # Add arguments
    parser.add_argument(
        "mode", choices=["init", "rss"], help="Mode of operation: 'init' or 'rss'"
    )

    # Parse the arguments
    args = parser.parse_args()

    with open("config.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if args.mode == "init":
        print("SCP回复提醒系统初始化中……")
        run_wikidot_scraper(config)
    elif args.mode == "rss":
        print("启动SCP回复提醒系统，开始监听SCP中分RSS")
        run_rss_checker(config, is_routine = True)
        run_wikidot_scraper(config, is_routine = True)


if __name__ == "__main__":
    main()
