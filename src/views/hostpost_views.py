"""
The post template editing views. The event setup wizard is `views/event_setup.py`.

by lurch, and the internet.
"""

import contextlib
import logging

import discord

from src.error_alerts import send_error_alert
from src.utils.build_hostposts import Post

logger = logging.getLogger(__name__)


###################################################################
# The view and modal classes are for allowing the user to edit posts
# before sending them to the autoscheduler.
###################################################################
class TemplateEditModal(discord.ui.Modal):
    def __init__(self, parent_view: "EditTemplateWizardView", template_text: str, template_name: str):
        super().__init__(title=f"Edit Template: {template_name}")
        self.parent_view = parent_view

        # Pre-fill the modal with the current draft language
        self.text_input = discord.ui.TextInput(
            label="Template Body",
            style=discord.TextStyle.paragraph,
            default=template_text,  # <-- This puts the draft text in their box
            max_length=2000,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Save the edited text back to the parent view's list
        current_index = self.parent_view.current_index
        self.parent_view.drafts[current_index]["post_text"] = self.text_input.value

        # Advance to the next template
        self.parent_view.current_index += 1

        # Update the view UI for the next step
        await self.parent_view.update_ui(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        await self.parent_view.fail(interaction, error, where=type(self).__name__)


class EditTemplateWizardView(discord.ui.View):
    def __init__(self, drafts: list[Post]):
        super().__init__(timeout=300)
        self.drafts = drafts
        self.current_index = 0

    async def update_ui(self, interaction: discord.Interaction):
        # Check if we have processed all templates
        if self.current_index >= len(self.drafts):
            # Before the reply, so a reply Discord refuses cannot hold up whoever awaits `wait()`.
            self.stop()
            await interaction.response.edit_message(
                content="✅ All templates customized! Ready to schedule.", view=None
            )
            return

        # Otherwise, update the button label and message content
        next_template = self.drafts[self.current_index]
        self.edit_button.label = f"Edit: {next_template['name']}"

        status_msg = f"## Customize your post? ({self.current_index + 1}/{len(self.drafts)})\n"
        status_msg += f"Click the button below to review/modify the **{next_template['name']}** template post language."

        await interaction.response.edit_message(content=status_msg, view=self)

    @discord.ui.button(label="Start Editing", style=discord.ButtonStyle.primary)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_template = self.drafts[self.current_index]
        # Pass the current text and name to the modal
        modal = TemplateEditModal(self, current_template["post_text"], current_template["name"])
        await interaction.response.send_modal(modal)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item, /) -> None:
        await self.fail(interaction, error, where=str(item))

    async def fail(self, interaction: discord.Interaction, error: Exception, *, where: str) -> None:
        """Ends the wizard on any error, keeping the drafts as they stand, so whoever
        awaits `wait()` carries on at once rather than at the timeout."""
        logger.error("post edit wizard failed on %s", where, exc_info=error)
        await send_error_alert(interaction.client, where="post edit wizard", error=error, interaction=interaction)
        self.stop()
        text = (
            "ERROR! Something went wrong, so editing stopped here and the text as it stood is kept. "
            "Change a queued post with /edit_pending_autopost."
        )
        # The error may be that this interaction can no longer be answered.
        with contextlib.suppress(discord.HTTPException):
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.edit_message(content=text, view=None)

    @discord.ui.button(label="Skip Editing", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        # Update the view UI for the next step
        await self.update_ui(interaction)
