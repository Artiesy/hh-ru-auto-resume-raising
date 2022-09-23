import asyncio
import aiohttp
import json
import os
import re
import time
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from status_code import status


class Schedule:
    def __init__(self):
        self.purpose_time = None
        self.time_dict = None
        self.update_time_list = None
        self._time_dict_id_to_hour()

    def _time_dict_id_to_hour(self):
        time_list = [i for i in range(0, 24)]
        self.time_dict = {j: f'{time_list[j]}:00' for j in range(len(time_list))}

    def choice_time(self):
        self.update_time_list = list(filter(lambda x: (self.purpose_time - x) % 4 == 0, self.time_dict))


class HHru(Schedule):
    def __init__(self, phone, password, proxy):
        super().__init__()
        self.phone = phone
        self.password = password
        self.proxy = proxy
        self.user_agent = UserAgent().chrome
        self.xsrf = None
        self.hhtoken = None
        self.boundary = 'boundary'
        self.resume_src = dict()
        self.resume_active = dict()

    async def request(self, method, url, headers=None, data=None):
        async with aiohttp.ClientSession() as session:
            action = getattr(session, method)
            async with action(url, headers=headers, data=data, proxy=self.proxy['https']) as response:
                await response.text()
                return response

    async def check_proxy(self):
        url = 'https://api.ipify.org?format=json'
        response = await self.request('get', url)
        ip_address = self.proxy['https'].split('@')[-1].split(':')[0]
        if ip_address == json.loads(await response.text())['ip']:
            return True
        else:
            return False

    async def _get_cookie_anonymous(self):
        url = 'https://hh.ru/'
        headers = {'user-agent': self.user_agent}
        response = await self.request('head', url, headers=headers)
        # assert response.status == 200

        cookie = str(response.headers)
        self.xsrf = re.search(r"(?<=_xsrf=).+?;", cookie).group()[:-1]
        self.hhtoken = re.search(r"(?<=hhtoken=).+?;", cookie).group()[:-1]

    async def _get_request_data(self, resume=None):
        headers = {
            'content-type': f'multipart/form-data; boundary={self.boundary}',
            'cookie': f'_xsrf={self.xsrf}; hhtoken={self.hhtoken};',
            'user-agent': self.user_agent,
            'x-xsrftoken': f'{self.xsrf}',
        }
        if resume is None:
            data = f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="_xsrf"\r\n\r\n{self.xsrf}\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="backUrl"\r\n\r\nhttps://hh.ru/\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="failUrl"\r\n\r\n/account/login\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="remember"\r\n\r\nyes\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="username"\r\n\r\n{self.phone}\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="password"\r\n\r\n{self.password}\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="username"\r\n\r\n{self.phone}\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; ' \
                   f'name="isBot"\r\n\r\nfalse\r\n--{self.boundary}--\r\n'
        else:
            data = f'--{self.boundary}\r\nContent-Disposition: form-data; name="resume"\r\n\r\n{resume}\r\n' \
                   f'--{self.boundary}\r\nContent-Disposition: form-data; name="undirectable"\r\n\r\ntrue\r\n' \
                   f'--{self.boundary}--\r\n'
        return headers, data

    async def login(self):
        await self._get_cookie_anonymous()
        url = 'https://hh.ru/account/login'
        headers, data = await self._get_request_data()
        response = await self.request('post', url, headers=headers, data=data)
        # assert response.status == 200
        cookie = str(response.headers)
        self.xsrf = re.search(r"(?<=_xsrf=).+?;", cookie).group()[:-1]
        self.hhtoken = re.search(r"(?<=hhtoken=).+?;", cookie).group()[:-1]

    async def raise_resume(self, resume):
        url = "https://hh.ru/applicant/resumes/touch"
        headers, data = await self._get_request_data(resume)
        response = await self.request('post', url, headers=headers, data=data)
        print(await response.text())
        return response.status

    async def get_resumes(self):
        url = 'https://hh.ru/applicant/resumes'
        headers, _ = await self._get_request_data()
        response = await self.request('get', url, headers=headers)
        # assert response.status == 200
        soup = BeautifulSoup(await response.text(), 'lxml')
        resumes = soup.select('div[data-qa="resume"]')
        self.resume_src = dict()
        for resume in resumes:
            title = resume.get("data-qa-title")
            link = resume.select_one("a[data-qa='resume-title-link']").get("href")
            link = link.split("/")[-1].split("?")[0]
            self.resume_src[title] = link

    async def add_resume_active(self, title: str, time: int):
        self.resume_active[title] = dict(resume_id=self.resume_src[title], time=time)
        await asyncio.sleep(0.01)

    async def del_resume_active(self, title):
        del self.resume_active[title]
        await asyncio.sleep(0.01)


async def main():
    load_dotenv()
    obj = HHru(os.getenv('phone'), os.getenv('password'), {'https': os.getenv('proxy')})

    await obj.login()
    await obj.get_resumes()
    print(obj.resume_src)
    title = input('Введите название резюме, которое нужно поднимать: ')
    print(obj.time_dict)
    obj.purpose_time = int(input('Введите ключ времени словаря с которого начнется поднятие резюме каждые 4 часа: '))

    await obj.add_resume_active(title, obj.purpose_time)

    obj.choice_time()

    for hour in obj.update_time_list:
        print(f'{hour}:00')

    print(obj.resume_active)
    input('Ваши настройки')
    while True:
        now_time = time.localtime(time.time())
        now_time = int(time.strftime("%H", now_time))
        if (obj.resume_active[title]['time'] - now_time) % 4 == 0:
            code = await obj.raise_resume(obj.resume_active[title]['resume_id'])
            if code == 409:
                print(status(code))
                await asyncio.sleep(60)
            elif code == 200:
                print(status(code))
                await asyncio.sleep(4*60*60)
            elif code == 500:
                print(code)
                break
            else:
                if await obj.check_proxy():
                    await obj.login()
                    code = await obj.raise_resume(obj.resume_active[title]['resume_id'])
                    if code == 409:
                        print(status(code))
                        await asyncio.sleep(60)
                    elif code == 200:
                        print(status(code))
                        await asyncio.sleep(4*60*60)
                    else:
                        print(code)
                        break
                else:
                    print(status(0))
                    break


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
