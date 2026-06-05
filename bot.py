import os

import discord
from discord import app_commands

from meme_store import ALLOWED_EXTENSIONS, create_meme_from_bytes, get_meme, get_meme_image_path, init_db, search_memes


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class MemeChoiceView(discord.ui.View):
    def __init__(self, memes):
        super().__init__(timeout=120)
        for index, meme in enumerate(memes, start=1):
            self.add_item(MemeSendButton(index, meme["id"], meme["title"]))


class MemeSendButton(discord.ui.Button):
    def __init__(self, index, meme_id, title):
        super().__init__(label=f"{index}. {title[:60]}", style=discord.ButtonStyle.primary)
        self.meme_id = meme_id

    async def callback(self, interaction: discord.Interaction):
        meme = get_meme(self.meme_id)
        image_path = get_meme_image_path(self.meme_id)

        if not meme or not image_path or not image_path.exists():
            await interaction.response.send_message("ミーム画像が見つかりませんでした。", ephemeral=True)
            return

        await interaction.response.send_message(
            content=meme["phrase"],
            file=discord.File(image_path),
        )


class MemeRegisterModal(discord.ui.Modal, title="ミームとして登録"):
    title_input = discord.ui.TextInput(
        label="タイトル",
        placeholder="例: 感想ですよね",
        max_length=80,
    )
    phrase_input = discord.ui.TextInput(
        label="セリフ・本文",
        placeholder="例: それってあなたの感想ですよね",
        style=discord.TextStyle.paragraph,
        max_length=400,
    )
    tags_input = discord.ui.TextInput(
        label="タグ",
        placeholder="例: 論破, 煽り, 反論",
        required=False,
        max_length=200,
    )
    note_input = discord.ui.TextInput(
        label="メモ",
        placeholder="使いどころや補足",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=400,
    )

    def __init__(self, attachment, source_url):
        super().__init__()
        self.attachment = attachment
        self.source_url = source_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            image_bytes = await self.attachment.read()
            meme_id = create_meme_from_bytes(
                title=str(self.title_input.value),
                phrase=str(self.phrase_input.value),
                tags=str(self.tags_input.value),
                note=str(self.note_input.value),
                source_url=self.source_url,
                image_bytes=image_bytes,
                original_filename=self.attachment.filename,
            )
        except Exception as error:
            await interaction.followup.send(f"登録できませんでした: {error}", ephemeral=True)
            return

        await interaction.followup.send(f"登録しました。ID: `{meme_id}`", ephemeral=True)


class MemeBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")


client = MemeBot()


def is_supported_image_attachment(attachment):
    if attachment.content_type in IMAGE_CONTENT_TYPES:
        return True
    _, extension = os.path.splitext(attachment.filename or "")
    return extension.lower() in ALLOWED_EXTENSIONS


@client.tree.command(name="meme", description="登録済みミームを検索して送信します。")
@app_commands.describe(query="探したいミームの言葉やタグ")
async def meme(interaction: discord.Interaction, query: str):
    memes = search_memes(query, limit=5)
    if not memes:
        await interaction.response.send_message("候補が見つかりませんでした。", ephemeral=True)
        return

    lines = []
    for index, item in enumerate(memes, start=1):
        score = round(item["score"] * 100)
        tags = f" / {item['tags']}" if item["tags"] else ""
        lines.append(f"{index}. {item['title']} ({score}%){tags}")

    await interaction.response.send_message(
        "候補を選んでください。\n" + "\n".join(lines),
        view=MemeChoiceView(memes),
        ephemeral=True,
    )


@client.tree.command(name="meme_random", description="登録済みミームから候補を表示します。")
async def meme_random(interaction: discord.Interaction):
    memes = search_memes("", limit=5)
    if not memes:
        await interaction.response.send_message("登録済みミームがありません。", ephemeral=True)
        return

    await interaction.response.send_message(
        "最近のミーム候補です。",
        view=MemeChoiceView(memes),
        ephemeral=True,
    )


@client.tree.context_menu(name="ミームとして登録")
async def register_meme_from_message(interaction: discord.Interaction, message: discord.Message):
    image_attachment = None
    for attachment in message.attachments:
        if is_supported_image_attachment(attachment):
            image_attachment = attachment
            break

    if not image_attachment:
        await interaction.response.send_message("このメッセージには登録できる画像添付がありません。", ephemeral=True)
        return

    await interaction.response.send_modal(
        MemeRegisterModal(
            attachment=image_attachment,
            source_url=message.jump_url,
        )
    )


if __name__ == "__main__":
    init_db()
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません。")
    client.run(DISCORD_BOT_TOKEN)
