import asyncio
import dataclasses
import json
import logging
import random
import ssl
from enum import Enum
from typing import Optional, Callable, Self, Awaitable

import aiohttp
import cloudscraper
import fake_useragent
import httpx
import requests
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from voluptuous import default_factory
from webdriver_manager.chrome import ChromeDriverManager

from custom_components.transportation.utilities.list import Lu


async def ssl_context():
    ctx = await asyncio.to_thread(ssl.create_default_context)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    return ctx


_LOGGER = logging.getLogger(__name__)


class SafeRequestError(Exception):
    pass


@dataclasses.dataclass
class SafeRequestResponseData:
    data: Optional[str] = default_factory("")
    status_code: int = default_factory(400)
    access_token: Optional[str] = default_factory(None)
    cookies: dict = default_factory({})

    def __init__(
            self,
            data: Optional[str] = None,
            status_code: int = 400,
            cookies=None,
            access_token: Optional[str] = None,
    ):
        if cookies is None:
            cookies = {}
        self.data = data
        self.status_code = status_code
        self.cookies = cookies
        self.access_token = access_token

    @property
    def text(self):
        return self.data

    @property
    def has(self):
        return self.status_code <= 399 and self.data is not None

    @property
    def json(self):
        try:
            return json.loads(self.data)
        except json.JSONDecodeError:
            return None


class SafeRequestMethod(Enum):
    POST = "post"
    GET = "get"
    PUT = "put"
    DELETE = "delete"


class SafeRequestEngine:
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: dict,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        pass


class SafeRequestEngineAiohttp(SafeRequestEngine):
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: dict,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method=method.name.lower(),
                    url=url,
                    headers=headers,
                    json=data,
                    data=data,
                    proxy=proxy,
                    timeout=timeout,
                    allow_redirects=True,
                    auto_decompress=True,
                    max_line_size=99999999,
                    read_bufsize=99999999,
                    compress=False,
                    read_until_eof=True,
                    expect100=True,
                    chunked=False,
                    ssl=False,
            ) as response:
                data = await response.text()
                cookies = response.cookies
                access_token = (
                    response.headers.get("Authorization").replace("Bearer ", "")
                    if response.headers.get("Authorization") is not None
                    else None
                )

                if response.status > 399:
                    raise SafeRequestError(
                        f"Failed to request {url} with status code {response.status}"
                    )

                return SafeRequestResponseData(
                    data=data,
                    status_code=response.status,
                    cookies=cookies,
                    access_token=access_token,
                )


class SafeRequestEngineRequests(SafeRequestEngine):
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: dict,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        response = await asyncio.to_thread(
            requests.request,
            method=method.name.lower(),
            url=url,
            headers=headers,
            data=data,
            proxies={
                "http": proxy,
                "https": proxy,
            }
            if proxy is not None
            else None,
            timeout=timeout,
            verify=False,
        )

        if response.status_code > 399:
            raise SafeRequestError(
                f"Failed to request {url} with status code {response.status_code}"
            )

        return SafeRequestResponseData(
            data=response.text,
            status_code=response.status_code,
            cookies=response.cookies.get_dict(),
            access_token=response.headers.get("Authorization").replace("Bearer ", "")
            if response.headers.get("Authorization") is not None
            else None,
        )


class SafeRequestEngineSelenium(SafeRequestEngine):
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: dict,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        manager = ChromeDriverManager()
        manager_install = await asyncio.to_thread(manager.install)
        options = webdriver.ChromeOptions()

        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1420,1080")
        options.add_argument("--headless=new")
        if proxy is not None:
            options.add_argument(f"--proxy-server={proxy}")
        driver = await asyncio.to_thread(
            webdriver.Chrome, service=ChromeService(manager_install), options=options
        )
        driver.get(url)

        all_cookies = driver.get_cookies()
        cookies_dict = {}
        for cookie in all_cookies:
            cookies_dict[cookie["name"]] = cookie["value"]

        return SafeRequestResponseData(
            data=driver.page_source,
            status_code=200,
            cookies=cookies_dict,
            access_token=None,
        )


class SafeRequestEngineUndetectedSelenium(SafeRequestEngine):
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: dict,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        options = uc.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1420,1080")
        options.add_argument("--headless=new")
        if proxy is not None:
            options.add_argument(f"--proxy-server={proxy}")

        driver = await asyncio.to_thread(uc.Chrome, options=options)
        driver.get(url)

        all_cookies = driver.get_cookies()
        cookies_dict = {}
        for cookie in all_cookies:
            cookies_dict[cookie["name"]] = cookie["value"]

        return SafeRequestResponseData(
            data=driver.page_source,
            status_code=200,
            cookies=cookies_dict,
            access_token=None,
        )


class SafeRequestEngineCloudscraper(SafeRequestEngine):
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: any,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        scraper = await asyncio.to_thread(cloudscraper.create_scraper)
        response = await asyncio.to_thread(
            scraper.request,
            method=method.name.lower(),
            url=url,
            headers=headers,
            json=data,
            proxies={
                "http": proxy,
                "https": proxy,
            }
            if proxy is not None
            else None,
            timeout=timeout,
            verify=False,
        )

        if response.status_code > 399:
            raise SafeRequestError(
                f"Failed to request {url} with status code {response.status_code}"
            )

        return SafeRequestResponseData(
            data=response.text,
            status_code=response.status_code,
            cookies=response.cookies.get_dict(),
            access_token=response.headers.get("Authorization").replace("Bearer ", "")
            if response.headers.get("Authorization") is not None
            else None,
        )


class SafeRequestEngineHttpx(SafeRequestEngine):
    async def request(
            self,
            headers: dict,
            method: SafeRequestMethod,
            url: str,
            data: dict,
            proxy: str,
            timeout: int,
    ) -> SafeRequestResponseData:
        async with httpx.AsyncClient(verify=False, proxy=proxy) as client:
            response = await client.request(
                method=method.name.lower(),
                url=url,
                headers=headers,
                json=data,
                timeout=timeout,
                follow_redirects=True,
            )
            if response.status_code > 399:
                raise SafeRequestError(
                    f"Failed to request {url} with status code {response.status_code}"
                )

            return SafeRequestResponseData(
                data=response.text,
                status_code=response.status_code,
                cookies=response.cookies,
                access_token=response.headers.get("Authorization").replace(
                    "Bearer ", ""
                )
                if response.headers.get("Authorization") is not None
                else None,
            )


class SafeRequest:
    def __init__(self, chains: list[SafeRequestEngine] = None):
        self._chains = (
            [
                SafeRequestEngineCloudscraper(),
                SafeRequestEngineAiohttp(),
                SafeRequestEngineRequests(),
                SafeRequestEngineHttpx(),
            ]
            if chains is None
            else chains
        )
        self._headers = {
            "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7,zh-CN;q=0.6,zh;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Cache-Control": "max-age=0",
            "Content-Type": "application/json",
            "Connection": "close",
            "Sec-Fetch-Dest": "document",
            "Priority": "u=0, i",
        }
        self._timeout = 60
        self._proxies: list[str] = []
        self._cookies: dict = {}

    def accept_text_html(self):
        """"""
        self._headers["Accept"] = (
            "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        )

        return self

    def accept_language(self, language: str = None, is_random: bool = False):
        """"""
        if is_random:
            languages = [
                "en-US",
                "en-US,en;q=0.9",
                "en-US,en;q=0.9,ko;q=0.8",
                "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
                "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7,zh-CN;q=0.6",
                "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7,zh-CN;q=0.6,zh;q=0.5",
                "en",
                "ko",
                "ko-KR",
                "ja",
                "zh-CN",
                "zh",
            ]
            self._headers["Accept-Language"] = random.choice(languages)
        elif language is not None:
            self._headers["Accept-Language"] = language

        return self

    def accept_encoding(self, encoding: str):
        """"""
        self._headers["Accept-Encoding"] = encoding

        return self

    async def user_agent(
            self,
            user_agent: Optional[str] = None,
            mobile_random: bool = False,
            pc_random: bool = False,
    ):
        """"""
        if user_agent is not None:
            self._headers["User-Agent"] = user_agent
            return self

        platforms = []
        if mobile_random:
            platforms.append("mobile")
        if pc_random:
            platforms.append("pc")
        ua_engine = await asyncio.to_thread(
            fake_useragent.UserAgent, platforms=platforms
        )
        self._headers["User-Agent"] = ua_engine.random

        if mobile_random:
            self._headers["Sec-Ch-Ua-Platform"] = '"Android"'
            self._headers["Sec-Ch-Ua-Mobile"] = "?0"
            self._headers["Sec-Ch-Ua"] = (
                '"Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"'
            )

        return self

    def chains(self, chains: list[SafeRequestEngine]):
        """"""
        self._chains = chains

        return self

    def auth(self, token: Optional[str]):
        """"""
        if token is not None:
            self._headers["Authorization"] = f"Bearer {token}"
        else:
            self._headers.pop("Authorization", None)

        return self

    def connection(self, connection: str):
        """"""
        self._headers["Connection"] = connection

    def keep_alive(self):
        """"""
        self._headers["Connection"] = "keep-alive"

    def connection_type(self, connection_type: str):
        """"""
        self._headers["Connection"] = connection_type

        return self

    def cache_control(self, cache_control: str):
        """"""
        self._headers["Cache-Control"] = cache_control

        return self

    def timeout(self, seconds: int):
        """"""
        self._timeout = seconds

        return self

    def header(self, key: str, value: str):
        """"""
        self._headers[key] = value

        return self

    def headers(self, headers: dict):
        """"""
        self._headers = {**self._headers, **headers}

        return self

    def proxy(self, proxy: str | None = None):
        """"""
        if proxy is None:
            self._proxies = []
        else:
            self._proxies.append(proxy)

        return self

    def proxies(self, proxies: list[str] | str | None):
        """"""
        if isinstance(proxies, list):
            self._proxies = proxies
        elif isinstance(proxies, str):
            self._proxies = Lu.map([proxies.split(",")], lambda x: x.strip())
        else:
            self._proxies = []

        return self

    def cookie(
            self, key: str = None, value: str = None, data: str = None, item: dict = None
    ):
        """"""
        if key is not None and value is not None and data is None and item is None:
            return self

        if data is not None:
            self._cookies = {
                **self._cookies,
                **Lu.map(data.split(";"), lambda x: x.split("=")).to_dict(),
            }
        elif item is not None:
            self._cookies = {**self._cookies, **item}
        else:
            self._cookies[key] = value

        return self

    async def request(
            self,
            url: str,
            method: SafeRequestMethod = SafeRequestMethod.GET,
            data: any = None,
            timeout: int = 60,
            raise_errors: bool = False,
            max_tries: int = 10,
            post_try_callables: list[Callable[[Self], Awaitable[None]]] = None,
    ) -> SafeRequestResponseData:
        errors = []
        tries = 0
        return_data = SafeRequestResponseData()

        for chain in self._chains:
            await asyncio.sleep(random.randrange(1, 2))

            if tries >= max_tries:
                return return_data

            if tries > 0 and post_try_callables is not None:
                for callable_ in post_try_callables:
                    await callable_(self)

            proxy = (
                random.choice(self._proxies + [None])
                if len(self._proxies) > 0
                else None
            )

            if proxy is not None:
                _LOGGER.debug(
                    "Using proxy %s for request [%s] %s", proxy, method.name, url
                )
            else:
                _LOGGER.debug(
                    "No proxy %s for request [%s] %s", proxy, method.name, url
                )

            try:
                return_data = await chain.request(
                    headers={
                        **self._headers,
                        **{
                            "Cookie": "; ".join(
                                [f"{k}={v}" for k, v in self._cookies.items()]
                            ),
                        },
                    },
                    method=method,
                    url=url,
                    data=data,
                    proxy=proxy,
                    timeout=timeout,
                )

                if return_data.status_code <= 399:
                    self.cookie(item=return_data.cookies)

                _LOGGER.debug(
                    "Safe request success with %s [%s] (%s) [Proxy: %s] <%s>",
                    chain.__class__.__name__,
                    method.name,
                    url,
                    proxy,
                    self._cookies,
                )

                return return_data
            except Exception as e:
                _LOGGER.error(
                    f"Failed to request {url} with {chain.__class__.__name__}: {e}"
                )
                errors.append(e)
                pass
            finally:
                tries += 1

        if len(errors) > 0 and raise_errors:
            raise errors[0]
        else:
            _LOGGER.debug("Safe request silently failed %s", errors)

        return return_data
