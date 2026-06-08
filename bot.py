import os

import discord
from discord import app_commands

from meme_store import (
    ALLOWED_EXTENSIONS,
    create_meme_from_bytes,
    find_image_matches,
    get_meme,
    get_meme_image_path,
    init_db,
    search_memes,
)


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
MEME_ADMIN_DISCORD_USER_IDS = {
    user_id.strip()
    for user_id in os.getenv("MEME_ADMIN_DISCORD_USER_IDS", "").split(",")
    if user_id.strip()
}
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class MemeChoiceView(discord.ui.View):
    def __init__(self, memes):
        super().__init__(timeout=120)
        self.memes = memes
        self.index = 0
        self.add_item(MemeSelect(self))
        self.refresh_buttons()

    @property
    def current_meme(self):
        return self.memes[self.index]

    def make_content(self):
        return f"候補 {self.index + 1}/{len(self.memes)}。画像を確認して、使うなら投稿を押してください。"

    def refresh_buttons(self):
        self.previous_button.disabled = self.index == 0
        self.next_button.disabled = self.index == len(self.memes) - 1

    async def refresh_message(self, interaction):
        self.refresh_buttons()
        await interaction.response.edit_message(
            content=self.make_content(),
            embed=make_preview_embed(self.current_meme),
            view=self,
        )

    @discord.ui.button(label="前へ", style=discord.ButtonStyle.secondary, row=1)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        await self.refresh_message(interaction)

    @discord.ui.button(label="投稿", style=discord.ButtonStyle.primary, row=1)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await publish_meme(interaction, self.current_meme["id"])
        await delete_choice_message(interaction)

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.memes) - 1, self.index + 1)
        await self.refresh_message(interaction)

    @discord.ui.button(label="閉じる", style=discord.ButtonStyle.danger, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await delete_choice_message(interaction)


class MemeSelect(discord.ui.Select):
    def __init__(self, browser_view):
        self.browser_view = browser_view
        options = []
        for index, meme in enumerate(browser_view.memes):
            score = round(meme["score"] * 100)
            tags = meme["tags"] or "タグなし"
            options.append(
                discord.SelectOption(
                    label=f"{index + 1}. {meme['title']}"[:100],
                    description=f"{score}% / {tags}"[:100],
                    value=str(index),
                )
            )
        super().__init__(placeholder="候補を選択", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.browser_view.index = int(self.values[0])
        await self.browser_view.refresh_message(interaction)


class UserInstallTestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="投稿テスト", style=discord.ButtonStyle.primary)
    async def post_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("memer test: このチャンネルへ投稿できました。")


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
            matches = find_image_matches(image_bytes, self.attachment.filename)
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

        warnings = []
        if matches["exact"]:
            warnings.append("完全一致の画像が既に登録されています。")
        if matches["similar"]:
            titles = " / ".join(match["title"] for match in matches["similar"][:3])
            warnings.append(f"似ている画像: {titles}")

        message = f"登録しました。ID: `{meme_id}`"
        if warnings:
            message += "\n注意: " + " ".join(warnings)

        await interaction.followup.send(message, ephemeral=True)


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

        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")


client = MemeBot()


def is_supported_image_attachment(attachment):
    if attachment.content_type in IMAGE_CONTENT_TYPES:
        return True
    _, extension = os.path.splitext(attachment.filename or "")
    return extension.lower() in ALLOWED_EXTENSIONS


def is_admin_discord_user(user):
    if not MEME_ADMIN_DISCORD_USER_IDS:
        return True
    return str(user.id) in MEME_ADMIN_DISCORD_USER_IDS


def make_preview_embed(meme):
    embed = discord.Embed(
        title=meme["title"],
        description=meme["phrase"],
        color=discord.Color.blurple(),
    )
    if meme.get("tags"):
        embed.add_field(name="タグ", value=meme["tags"], inline=False)
    if meme.get("image_url"):
        embed.set_image(url=meme["image_url"])
    return embed


def make_image_embed(meme):
    embed = discord.Embed(color=discord.Color.blurple())
    if meme.get("image_url"):
        embed.set_image(url=meme["image_url"])
    return embed


async def publish_meme(interaction, meme_id):
    meme = get_meme(meme_id)
    image_path = get_meme_image_path(meme_id)

    if not meme:
        await interaction.followup.send("ミームが見つかりませんでした。", ephemeral=True)
        return

    if image_path and image_path.exists():
        await interaction.followup.send(
            file=discord.File(image_path),
        )
        return

    await interaction.followup.send(
        embed=make_image_embed(meme),
    )


async def delete_choice_message(interaction):
    try:
        await interaction.delete_original_response()
        return
    except discord.NotFound:
        return
    except discord.HTTPException:
        pass

    try:
        await interaction.message.delete()
    except discord.HTTPException:
        await interaction.followup.send("候補画面はDiscord側の閉じる操作で消せます。", ephemeral=True)


@client.tree.command(name="meme", description="登録済みミームを検索して送信します。")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(query="探したいミームの言葉やタグ")
async def meme(interaction: discord.Interaction, query: str):
    memes = search_memes(query, limit=5)
    if not memes:
        await interaction.response.send_message("候補が見つかりませんでした。", ephemeral=True)
        return

    view = MemeChoiceView(memes)

    await interaction.response.send_message(
        view.make_content(),
        embed=make_preview_embed(view.current_meme),
        view=view,
        ephemeral=True,
    )


@client.tree.command(name="meme_random", description="登録済みミームから候補を表示します。")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def meme_random(interaction: discord.Interaction):
    memes = search_memes("", limit=5)
    if not memes:
        await interaction.response.send_message("登録済みミームがありません。", ephemeral=True)
        return

    view = MemeChoiceView(memes)

    await interaction.response.send_message(
        view.make_content(),
        embed=make_preview_embed(view.current_meme),
        view=view,
        ephemeral=True,
    )


@client.tree.command(name="memer_test", description="User Install Appの動作を確認します。")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def memer_test(interaction: discord.Interaction):
    await interaction.response.send_message(
        "User Install Appのテストです。このメッセージが見えているのはあなただけです。",
        view=UserInstallTestView(),
        ephemeral=True,
    )


@client.tree.context_menu(name="ミームとして登録")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def register_meme_from_message(interaction: discord.Interaction, message: discord.Message):
    if not is_admin_discord_user(interaction.user):
        await interaction.response.send_message("この操作は管理者だけが使えます。", ephemeral=True)
        return

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
