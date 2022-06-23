from typing import Literal
from dataclasses import dataclass

import bs4
from bs4 import BeautifulSoup
from aiohttp import ClientSession


@dataclass
class ParsedVKPack:
    sticker_ids: list[int]
    url: str
    title: str = None

    @property
    def first_sticker(self) -> int:
        return self.sticker_ids[0]


def vk_sticker_id_to_uri(index: int, px: Literal[256, 512] = 512):
    return f'https://vk.com/sticker/{index}/{str(px)}.png'


async def parse_vk_pack(pack_url: str) -> ParsedVKPack:
    async with ClientSession() as session:
        response = await session.get(pack_url)
        text = await response.text(response.get_encoding(), errors='ignore')
        soup = BeautifulSoup(text, features='lxml')

        sticker_ids = [int(i['src'].split('-')[1])
                       for i in soup.find_all('img', {'class': 'th_img sticker_img'})]
        pack_title_tag = soup.find('div', {'class': 'stickers_name'})

        if isinstance(pack_title_tag, bs4.Tag):
            pack_title = pack_title_tag.contents[0]
        else:
            pack_title = None

        result = ParsedVKPack(sticker_ids=sticker_ids,
                              title=pack_title,
                              url=pack_url)

        return result
