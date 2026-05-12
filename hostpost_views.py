'''
This module contains the view classes for the hosting post setup wizard. This is where the dropdowns, 
buttons, and modals are defined, as well as the logic for how they interact with each other and save data.

by lurch, and the internet.
'''

from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord import ui
from hostpost_utils import (create_prix_option_set,
                            create_timeoffset_option_set, 
                            create_publicprivate_option_set, 
                            discord_timestamp)
from event_post_text import time_offset_options

class TimeModal(discord.ui.Modal, title="Time Offset from Last Prix"):
    time_input = discord.ui.TextInput(
        label="Enter the time offset in minutes...",
        placeholder="e.g., 30",
        min_length=1,
        max_length=3
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        # Save the text input to the main Wizard View
        self.parent_view.time_offset = self.time_input.value
        await interaction.response.edit_message(
            content=self.parent_view.get_content(), 
            view=self.parent_view
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)


class WizardView(discord.ui.View):
    def __init__(self, num_prix: int, default_start_time: datetime, event: str, use_simple_time: bool):
        super().__init__(timeout=180)
        self.num_prix: int = num_prix
        self.default_start_time = default_start_time
        self.current_time: datetime = default_start_time
        self.event: str = event
        self.current_step: int = 1
        self.all_results: list[dict[str, any]] = []
        self.autopost: bool = False
        
        self.current_prix: str | None = None
        self.time_offset: int | None = None
        self.prixtype: str | None = 'public'

        # 1. Clear the view of the 'automatic' items from decorators
        self.clear_items()

        # 2. Add the Prix choice dropdown
        self.add_item(self.select_choice)

        # 3. Depending on the choice of Simple or Custom time, add the one we want.
        if use_simple_time:
            self.add_item(self.select_time)
        else:
            self.add_item(self.set_time_button)
        
        #4. Add the Prix Type (Public or Private) dropdown
        self.add_item(self.select_prixtype)

        #5 Add the Next Step button
        self.add_item(self.next_button)

    # ''' Autocomplete methods '''
    # async def time_offset_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    #     options = [offset for offset in self.offset_list if current.lower() in offset.lower()]
    #     print(options)

    #     # Return up to 25 results (25=discord limit)
    #     return [app_commands.Choice(name=offset, value=f"{offset}") for offset in options[:25]]
    # ''' ---------------------------------------------- '''

    def get_content(self):
        if self.current_step > self.num_prix:
            # summary = "\n".join(f"**{key}** @ **{value}**" for key, value in self.all_results.items())
            return f"✅ **All Selections Completed!**\n\n"
        
        return (f"## {self.event} is scheduled to start {discord_timestamp(self.default_start_time, 'relative')} at {discord_timestamp(self.default_start_time, 'short')}.\n"
                f"### Step {self.current_step} of {self.num_prix}\n"
                f"**Current Selection:** The {self.prixtype or 'None'} {self.current_prix or 'None'} with {self.time_offset or 'None'} minute offset\n"
                "Please select an option and a time:")

    async def auto_or_manual_post(self, interaction: discord.Interaction):
        self.clear_items()

        # Here are the automated post buttons
        auto_button = discord.ui.Button(label="Hail to the Machines", style=discord.ButtonStyle.danger)
        manual_button = discord.ui.Button(label="I'll do it myself", style=discord.ButtonStyle.success)
        
        # Define what happens when they are clicked
        async def auto_callback(inter: discord.Interaction):
            self.autopost = True
            await inter.response.edit_message(content="Event announcement and prix opening posts will be posted automatically.", view=None)
            self.stop() # This finally releases the view.wait() in your main function

        async def manual_callback(inter: discord.Interaction):
            self.autopost = False
            await inter.response.edit_message(content="User will post all event posts.", view=None)
            self.stop()

        auto_button.callback = auto_callback
        manual_button.callback = manual_callback

        self.add_item(auto_button)
        self.add_item(manual_button)

        await interaction.response.edit_message(
            content="### :bangbang: Would you like to the bot to push the announcement and prix opening posts automatically? (Note that prix and event results posts continue to require manual posting)", 
            view=self
        )

    @discord.ui.select(
        placeholder="1. Select the Prix...",
        options=create_prix_option_set()
    )
    async def select_choice(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.current_prix = select.values[0]
        # Immediately update the message so the interaction is "consumed" successfully
        await interaction.response.edit_message(content=self.get_content(), view=self)

    # This dropdown is for the Simple offset options
    @discord.ui.select(
        placeholder="2. Select the time offset from previous...",
        options=create_timeoffset_option_set()
    )
    async def select_time(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.time_offset = select.values[0]
        # Immediately update the message
        await interaction.response.edit_message(content=self.get_content(), view=self)

    # This button is for opening a modal to input a Custom time offset.
    @discord.ui.button(label="⌨Enter Time Offset", style=discord.ButtonStyle.primary)
    async def set_time_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Open the modal and pass 'self' so the modal can save data back here
        await interaction.response.send_modal(TimeModal(self))
        self.time_offset = self.parent_view.time_offset

    @discord.ui.select(
        placeholder="3. Select whether the prix is public or private...",
        options=create_publicprivate_option_set()
    )
    async def select_prixtype(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.prixtype = select.values[0]
        # Immediately update the message
        await interaction.response.edit_message(content=self.get_content(), view=self)

    @discord.ui.button(label="Next Step", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.current_prix or not self.time_offset or not self.prixtype:
            await interaction.response.send_message("Please fill all three Prix elements before proceeding!", ephemeral=True)
            return

        # Save and increment
        updated_time = self.current_time + timedelta(minutes=int(self.time_offset))
        # Setting prix_type to "public" in anticipation of future private prix functionality.
        self.all_results.append({"prix": self.current_prix, "time": updated_time, "prix_type": self.prixtype})
        self.current_step += 1
        self.current_time = updated_time
        self.current_prix = None
        self.time_offset = None
        self.prixtype = 'public'

        if self.current_step > self.num_prix:
            # # Final step: Remove the view (dropdowns/buttons)
            # await interaction.response.edit_message(content=self.get_content(), view=None)
            # self.stop()
            await self.auto_or_manual_post(interaction)
        else:
            # Update button label for the last item
            if self.current_step == self.num_prix:
                button.label = "Finish"
            await interaction.response.edit_message(content=self.get_content(), view=self)