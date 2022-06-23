import asyncio

from aiogram import Bot, Dispatcher
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.files import JSONStorage
from aiogram.dispatcher.dispatcher import FSMContext
from aiogram.types import Message, ParseMode
from aiogram.utils.exceptions import BadRequest

from aiogram_keyboards_include.markup_scheme import MarkupScheme, DialogMeta

from .vk_helper import parse_vk_pack, vk_sticker_id_to_uri
from .config import config


class Form(StatesGroup):
    vk_stickers_identifier = State()
    pack_length = State()
    set_name_spec = State()
    choose_next_action = State()

    process_inspection = State()


bot = Bot(config['token'], parse_mode=ParseMode.HTML)
storage = JSONStorage('uflow.json')
dp = Dispatcher(bot=bot, storage=storage)


@dp.message_handler(commands=['start'], state='*')
async def start_handler(message, state):
    await state.reset_state(True)
    await message.answer('Привет! Я помогу тебе импортировать любые стикеры из ВК в Telegram в лучшем '
                         'качестве (512px).\n\nЧтобы создать новый пак, используй команду /new')


@dp.message_handler(commands=['new'], state='*')
async def new_handler(message: Message, state):
    await state.reset_state(True)
    await message.answer('Хорошо, новый пак. Отправь мне ссылку на этот пак в ВК.\n\nЕсли ссылку получить проблематично'
                         ' (например, чтобы импортировать определённый стиль стикеров), отправь ID первого стикера.')
    await Form.first()


@dp.message_handler(state=Form.vk_stickers_identifier)
async def identifier_handler(message: Message, state: FSMContext):
    identifier = message.text

    if not identifier.isnumeric() and not identifier.startswith('https://'):
        return await message.answer('Сыылка должна начинаться с <code>https://</code>.\n\n'
                                    'Отправь ещё раз')

    await state.update_data(pack_identifier=identifier)
    await message.answer('Теперь отправь мне длину пака.')
    await Form.next()


@dp.message_handler(state=Form.pack_length)
async def length_handler(message: Message, state: FSMContext):
    length = message.text

    if not length.isnumeric():
        return await message.answer('Длина стикерпака должна быть целым числом.\n\nОтправь ещё раз')
    else:
        length = int(length)

    if length > 100:
        return await message.answer('Размер стикерпака не может привышать 100.\n\nОтправь ещё раз')

    await state.update_data(length=length)

    scheme = MarkupScheme()
    markup = await scheme.get_markup([['Начать'], ['Пропустить']])

    data = await state.get_data()
    pack_identifier = data.get('pack_identifier')

    if pack_identifier.isnumeric() and 'spec_name' not in data.keys():
        await message.answer('Так как ты указал ID стикера вместо ссылки на пак, тебе нужно дополнительно'
                             ' ввести название стикеров и заголовок.\n\n Пожалуйста, введи данные, разделяя их '
                             'двоеточием. Например...\n\nblackmary:Мари [Тёмный]')
        await Form.set_name_spec.set()
    else:
        await message.answer('Всё готово для создания, но теперь нужно проверить что всё правильно. Может быть'
                             ' такое что в паке проскальзывают стикеры из других наборов. \n\n'
                             'По ходу проверки вы так-же можете устанавливать стикерам мужные эмодзи.',
                             reply_markup=markup)

        await Form.choose_next_action.set()


@dp.message_handler(state=Form.set_name_spec)
async def name_spec_handler(message: Message, state: FSMContext):
    spl = message.text.split(':')

    if len(spl) != 2:
        return await message.answer('В поле `set_name_spec` должен быть один симол `:`.\n\nВведи ещё раз.')

    name, title = spl
    name = name.lower()

    alphabet = 'qwertyuiopasdfghjklzxcvbnm_1234567890'

    for symbol in name:
        if symbol not in alphabet:
            return await message.answer('Поле `set_name_spec::name` должно состоять только из разрешённых символов.'
                                        f' Список разрешённых символов: <code>{alphabet}</code>. Ошибка на символе '
                                        f'<code>{symbol}</code>\n\nВведи ещё раз')

    await state.update_data(spec_name={'name': name, 'title': title})

    scheme = MarkupScheme()
    markup = await scheme.get_markup([['Начать', 'Пропустить']])

    await message.answer('Всё готово для создания, но теперь нужно проверить что всё правильно. Может быть'
                         ' такое что в паке проскальзывают стикеры из других наборов. \n\n'
                         'По ходу проверки вы так-же можете устанавливать стикерам мужные эмодзи.',
                         reply_markup=markup)

    await Form.choose_next_action.set()


async def create_sticker_set(user_id: int, name: str, name_postfix: str,
                             title, emojis, png_sticker: str) -> str:

    try:
        await bot.create_new_sticker_set(user_id, name=name + name_postfix, title=title,
                                         emojis=emojis, png_sticker=png_sticker)
    except BadRequest as e:
        if e.args[0] == 'Sticker set name is already occupied':
            last_literal = name[-1]
            if last_literal.isnumeric():
                name = name[:-1] + str(int(last_literal) + 1)
            else:
                name = name + '1'
            return await create_sticker_set(user_id, name, name_postfix, title, emojis, png_sticker)
        else:
            raise

    return name


@dp.message_handler(lambda x: x.text == 'Пропустить', state=Form.choose_next_action)
async def scip_inspection_handler(message: Message, state: FSMContext):
    """ Create all stickers without check """

    data = await state.get_data()

    length = data['length']
    identifier = data['pack_identifier']
    name_spec = data.get('name_spec')

    status = await message.answer('Создание пака...')

    if identifier.isnumeric():
        if name_spec is None:
            return await status.edit_text('Логическая ошибка. Попробуй начать сначала...\n\n/new')

        name, title = name_spec['name'], name_spec['title']
        first_sticker = int(identifier)

    else:
        name = identifier.split('/')[-1]

        # NOTE: now we skip error handling to test
        parse_result = await parse_vk_pack(identifier)

        if not parse_result.sticker_ids:
            return await status.edit_text('Мы не смогли найти пак. Попробуй начать сначала, указав ID первого '
                                          'стикера вместо ссылки на пак.\n\n/new')

        title, first_sticker = parse_result.title, parse_result.first_sticker

    target_range = range(first_sticker, first_sticker + length + 1)
    target_urls = [vk_sticker_id_to_uri(i)
                   for i in target_range]

    me = await bot.get_me()
    postfix = f'_by_{me.username}'

    name = await create_sticker_set(message.from_user.id, name=name, name_postfix=postfix,
                                    title=title, emojis='✨', png_sticker=target_urls[0])

    coroutines = [
        bot.add_sticker_to_set(message.from_user.id, name=name + postfix, emojis='✨', png_sticker=i)
        for i in target_urls[1:]
    ]
    await asyncio.gather(*coroutines)

    await status.edit_text(f'Стикерпак успешно создан!\n\nhttps://t.me/addstickers/{name + postfix}')
    return await state.reset_state(True)


@dp.message_handler(state=Form.process_inspection)
@dp.message_handler(lambda x: x.text == 'Начать', state=Form.choose_next_action)
async def start_inspection_handler(message: Message, state: FSMContext):
    """ Check if every sticker valid """

    await Form.process_inspection.set()

    data = await state.get_data()

    identifier = data['pack_identifier']
    name_spec = data.get('name_spec')

    if identifier.isnumeric():
        if name_spec is None:
            return await message.answer('Логическая ошибка. Попробуй начать сначала...\n\n/new')

        name, title = name_spec['name'], name_spec['title']
        first_sticker = int(identifier)

    else:
        name = identifier.split('/')[-1]

        # NOTE: now we skip error handling to test
        parse_result = await parse_vk_pack(identifier)

        if not parse_result.sticker_ids:
            return await message.answer('Мы не смогли найти пак. Попробуй начать сначала, указав ID первого '
                                        'стикера вместо ссылки на пак.\n\n/new')

        title, first_sticker = parse_result.title, parse_result.first_sticker

    name = data.get('real_name', name)

    if message.text == 'Начать':
        await state.update_data(checked_length=0,
                                accepted=0)

        await send_next_item(DialogMeta(message), state, first_sticker)

    elif message.text == 'Выкинуть':
        await state.update_data(checked_length=data['checked_length'] + 1)
        await send_next_item(DialogMeta(message), state, first_sticker)
    else:
        user_want_exit = message.text == 'Пак закончился'

        me = await bot.get_me()
        postfix = f'_by_{me.username}'

        if not user_want_exit:

            try:
                if data['checked_length'] == 0:
                    name = await create_sticker_set(message.from_user.id, name=name,
                                                    name_postfix=postfix, title=title, emojis=message.text,
                                                    png_sticker=vk_sticker_id_to_uri(first_sticker))
                    await state.update_data(real_name=name)
                else:
                    asyncio.create_task(
                        bot.add_sticker_to_set(user_id=message.from_user.id,
                                               name=name + postfix,
                                               emojis=message.text,
                                               png_sticker=vk_sticker_id_to_uri(first_sticker+data['checked_length']))
                    )
            except BadRequest as e:
                if e.args[0] == 'Invalid sticker emojis':
                    return await message.answer('Отправь эмодзи')

            await state.update_data(checked_length=data['checked_length'] + 1,
                                    accepted=data['accepted'] + 1)

        to_exit = (not await send_next_item(DialogMeta(message), state, first_sticker)
                   if not user_want_exit else True)

        if to_exit:
            await message.answer(f'Вы всё проверили, вот ваш стикерпак!'
                                 f'\n\nhttps://t.me/addstickers/{name + postfix}')
            return await state.reset_state(True)


async def send_next_item(meta: DialogMeta, state: FSMContext, first_sticker: int) -> bool:
    data = await state.get_data()
    already_checked, accepted, length = data['checked_length'], data['accepted'], data['length']

    if accepted >= length:
        return False
    else:
        url = vk_sticker_id_to_uri(first_sticker + already_checked, 256)

        scheme = MarkupScheme()
        markup = await scheme.get_markup([['✨', 'Выкинуть'],
                                          ['Пак закончился']])
        await meta.source.answer_photo(url, reply_markup=markup)
        return True


if __name__ == '__main__':
    asyncio.run(dp.start_polling())
