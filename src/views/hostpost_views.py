'''
This module contains the view classes for the following:

1. Post template editing
2. Event setup wizard. 

by lurch, and the internet.
'''

from datetime import datetime, timedelta
import asyncio
import discord
from src.utils.hostpost_utils import (create_prix_option_set,
                            create_timeoffset_option_set, 
                            create_publicprivate_option_set,
                            create_track_option_set,
                            discord_timestamp)

###################################################################
# The view and modal classes are for allowing the user to edit posts
# before sending them to the autoscheduler.
###################################################################
class TemplateEditModal(discord.ui.Modal):
    def __init__(self, parent_view, template_text, template_name):
        super().__init__(title=f"Edit Template: {template_name}")
        self.parent_view = parent_view
        
        # Pre-fill the modal with the current draft language
        self.text_input = discord.ui.TextInput(
            label="Template Body",
            style=discord.TextStyle.paragraph,
            default=template_text, # <-- This puts the draft text in their box
            max_length=2000
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Save the edited text back to the parent view's list
        current_index = self.parent_view.current_index
        self.parent_view.drafts[current_index]['post_text'] = self.text_input.value
        
        # Advance to the next template
        self.parent_view.current_index += 1
        
        # Update the view UI for the next step
        await self.parent_view.update_ui(interaction)


class EditTemplateWizardView(discord.ui.View):
    def __init__(self, drafts):
        super().__init__(timeout=300)
        self.drafts = drafts  # List of dicts: [{'name': 'Welcome', 'text': '...'}, ...]
        self.current_index = 0

    async def update_ui(self, interaction: discord.Interaction):
        # Check if we have processed all templates
        if self.current_index >= len(self.drafts):
            self.clear_items()
            await interaction.response.edit_message(
                content="✅ All templates customized! Ready to schedule.", 
                view=None
            )
            self.stop() # Releases view.wait() so your bot can schedule them
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
        modal = TemplateEditModal(self, current_template['post_text'], current_template['name'])
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Skip Editing", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        # Update the view UI for the next step
        await self.update_ui(interaction)



###################################################################
# The view and modal classes are for allowing the user to choose 
# among the different prix, time offset, and public/private lobby
# options for an event.
###################################################################

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
    def __init__(self, 
                 num_prix: int, 
                 default_start_time: datetime, 
                 event: str, 
                 use_simple_time: bool,
                 classic_tracks: list[str],
                 ninetynine_tracks: list[str]
                 ):
        super().__init__(timeout=180)
        self.num_prix: int = num_prix
        self.default_start_time = default_start_time
        self.current_time: datetime = default_start_time
        self.event: str = event
        self.use_simple_time = use_simple_time
        # Note that each dropdown needs a separate option set, as otherwise they'd share the same defaults
        self.classic_track_options1: discord.SelectOption = create_track_option_set(classic_tracks)
        self.classic_track_options2: discord.SelectOption = create_track_option_set(classic_tracks)
        self.classic_track_options3: discord.SelectOption = create_track_option_set(classic_tracks)
        self.ninetynine_track_options1: discord.SelectOption = create_track_option_set(ninetynine_tracks)
        self.ninetynine_track_options2: discord.SelectOption = create_track_option_set(ninetynine_tracks)
        self.ninetynine_track_options3: discord.SelectOption = create_track_option_set(ninetynine_tracks)
        self.track_select_1: discord.ui.Select | None = None,
        self.track_select_2: discord.ui.Select | None = None,
        self.track_select_3: discord.ui.Select | None = None,
        self.track_1: str | None = None
        self.track_2: str | None = None
        self.track_3: str | None = None
        self.current_step: int = 1
        self.all_results: list[dict[str, any]] = []
        self.autopost: bool = False
        self.validate: bool = True
        
        self.current_prix: str | None = None
        self.time_offset: int | None = None
        self.prixtype: str | None = 'public'
        self.track_list: str | None = None
        self.selected_tracks: list[str] = []
        self.lineup_type: str | None = None
        # This is a hack to allow us to use the same view for both prix selection and 
        # track selection steps, which have different dropdown options. We check this variable 
        # in the dropdown callbacks to know which options to populate and how to save the results.
        self.track_selection_menu: bool = False 

        # 1. Clear the view of the 'automatic' items from decorators
        self.clear_items()

        # 2. Add the Prix choice dropdown
        self.add_item(self.select_choice)

        # 3. Depending on the choice of Simple or Custom time, add the one we want.
        if self.use_simple_time:
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
        if not self.track_selection_menu:
            if self.current_step > self.num_prix:
                return f"✅ **All Selections Completed!**\n\n"
            
            return (f"## {self.event} is scheduled to start {discord_timestamp(self.default_start_time, 'relative')} at {discord_timestamp(self.default_start_time, 'short')}.\n"
                    f"### Step {self.current_step} of {self.num_prix}\n"
                    f"**Current Selection:** The {self.prixtype or 'None'} {self.current_prix or 'None'} with {self.time_offset or 'None'} minute offset\n"
                    "Please select an option and a time:")
        else:
            if self.track_select_1.values:
                track_1 = self.track_select_1.values[0]
            else:
                track_1 = None
            if self.track_select_2.values:
                track_2 = self.track_select_2.values[0]
            else:
                track_2 = None
            if self.track_select_3.values:
                track_3 = self.track_select_3.values[0]
            else:
                track_3 = None
            return (f"## {self.event} is scheduled to start {discord_timestamp(self.default_start_time, 'relative')} at {discord_timestamp(self.default_start_time, 'short')}.\n"
                    f"### Track lineup:\n"
                    f"**Current Selection:** {track_1 or 'None'} -> {track_2 or 'None'} -> {track_3 or 'None'}\n"
                    "Please select all three tracks:")


    async def skip_validation_question(self, interaction: discord.Interaction):
        self.clear_items()

        skip_button = discord.ui.Button(label="Skip validation", style=discord.ButtonStyle.danger)
        validate_button = discord.ui.Button(label="I'll validate", style=discord.ButtonStyle.success)

        # Define what happens when they are clicked
        async def skip_callback(interaction: discord.Interaction):
            self.validate = False

            message_text = "Event announcement and prix opening posts will be posted automatically. Results will be pushed without validation."
            await interaction.response.edit_message(content=message_text, view=None)
            #await interaction.message.edit(content=message_text, view=None)
            self.stop() # This finally releases the view.wait() in hostpost_commands

        async def validate_callback(interaction: discord.Interaction):
            self.validate = True
            
            message_text = "Event announcement and prix opening posts will be posted automatically. Host will be prompted to validate results before posting."
            await interaction.response.edit_message(content=message_text, view=None)
            self.stop()

        skip_button.callback = skip_callback
        validate_button.callback = validate_callback

        self.add_item(skip_button)
        self.add_item(validate_button)

        await interaction.response.edit_message(
            content="### :bangbang: Would you like to validate final scores before scores are posted?", 
            view=self
        )



    async def auto_or_manual_post(self, interaction: discord.Interaction):
        self.clear_items()

        # Here are the automated post buttons
        auto_button = discord.ui.Button(label="Hail to the Machines", style=discord.ButtonStyle.danger)
        manual_button = discord.ui.Button(label="I'll do it myself", style=discord.ButtonStyle.success)
        
        # Define what happens when they are clicked
        async def auto_callback(interaction: discord.Interaction):
            self.autopost = True

            # Go to view with buttons asking if the user wants to skip the score validation component.
            #await interaction.response.edit_message(content="", view=None)
            await self.skip_validation_question(interaction)
            #self.stop() # This finally releases the view.wait() in hostpost_commands

        async def manual_callback(interaction: discord.Interaction):
            self.autopost = False
            await interaction.response.edit_message(content="User will post all event posts.", view=None)
            self.stop()

        auto_button.callback = auto_callback
        manual_button.callback = manual_callback

        self.add_item(auto_button)
        self.add_item(manual_button)

        await interaction.response.edit_message(
            content="### :bangbang: Would you like to the bot to push the announcement and prix opening posts automatically? (Note that prix and event results posts continue to require manual intervention through slash commands.)", 
            view=self
        )


    def show_wizard_ui(self):
        self.clear_items()
        
        if self.track_selection_menu:
            # Show ONLY the sub-options and the next button
            self.add_item(self.track_select_1)
            self.add_item(self.track_select_2)
            self.add_item(self.track_select_3)
            self.add_item(self.next_button)
        else:
            # Show standard main menu layout
            self.add_item(self.select_choice)
            if self.use_simple_time:
                self.add_item(self.select_time)
            else:
                self.add_item(self.set_time_button)
            self.add_item(self.select_prixtype)
            self.add_item(self.next_button)

    
    ###################################
    # Below are prix, time, and public/private selection handlers
    ###################################
    @discord.ui.select(
        placeholder="1. Select the Prix...",
        options=create_prix_option_set()
    )
    async def select_choice(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.current_prix = select.values[0]

        # Update the visual state so the selection sticks!
        for option in select.options:
            option.default = (option.value == self.current_prix)

        # Immediately update the message so the interaction is "consumed" successfully
        await interaction.response.edit_message(content=self.get_content(), view=self)

    # This dropdown is for the Simple offset options
    @discord.ui.select(
        placeholder="2. Select the time offset from previous...",
        options=create_timeoffset_option_set()
    )
    async def select_time(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.time_offset = select.values[0]

        # Update the visual state for the time menu
        for option in select.options:
            option.default = (option.value == int(self.time_offset))
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

        for option in select.options:
            option.default = (option.value == self.prixtype)
        # Immediately update the message
        await interaction.response.edit_message(content=self.get_content(), view=self)


    ###################################
    # Below are track selection handlers
    ###################################
    class TrackSelect1(discord.ui.Select):
        def __init__(self, parent_view: discord.ui.View, track_options: discord.SelectOption, track_num: int):
            self.parent_view = parent_view
            super().__init__(
                placeholder=f"Track {track_num}...",
                options=track_options
            )

        async def callback(self, interaction: discord.Interaction):
            for option in self.options:
                option.default = (option.value == self.values[0])
            await interaction.response.edit_message(content=self.parent_view.get_content(), view=self.parent_view)
    
    class TrackSelect2(discord.ui.Select):
        def __init__(self, parent_view: discord.ui.View, track_options: discord.SelectOption, track_num: int):
            self.parent_view = parent_view
            super().__init__(
                placeholder=f"Track {track_num}...",
                options=track_options
            )

        async def callback(self, interaction: discord.Interaction):
            for option in self.options:
                option.default = (option.value == self.values[0])
            await interaction.response.edit_message(content=self.parent_view.get_content(), view=self.parent_view)
        
    class TrackSelect3(discord.ui.Select):
        def __init__(self, parent_view: discord.ui.View, track_options: discord.SelectOption, track_num: int):
            self.parent_view = parent_view
            super().__init__(
                placeholder=f"Track {track_num}...",
                options=track_options
            )

        async def callback(self, interaction: discord.Interaction):
            for option in self.options:
                option.default = (option.value == self.values[0])
            await interaction.response.edit_message(content=self.parent_view.get_content(), view=self.parent_view)


    
    @discord.ui.button(label="Next Step", style=discord.ButtonStyle.primary, row=4)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Set the completion requirement based on the menu
        if self.track_selection_menu:
            if not self.track_select_1.values or not self.track_select_2.values or not self.track_select_3.values[0]:
                await interaction.response.send_message(
                    "Please fill all three tracks before proceeding!", 
                    ephemeral=True
                    )
                return
        else:
            if not self.current_prix or not self.time_offset or not self.prixtype:
                await interaction.response.send_message(
                    "Please fill all three Prix elements before proceeding!", 
                    ephemeral=True
                    )
                return

        # Handle if we are in the track selection step first
        if self.track_selection_menu:          
            self.selected_tracks.append(self.track_select_1.values[0])
            self.selected_tracks.append(self.track_select_2.values[0])
            self.selected_tracks.append(self.track_select_3.values[0])

            # Save prix information now.
            # Update time
            updated_time = self.current_time + timedelta(minutes=int(self.time_offset))
            self.all_results.append({"prix": self.current_prix, 
                                     "time": updated_time, 
                                     "prix_type": self.prixtype, 
                                     "lineup": self.selected_tracks
                                     })
            
            # Reset to menu default options
            for option in self.track_select_1.options:
                option.default = False
            for option in self.track_select_2.options:
                option.default = False
            for option in self.track_select_3.options:
                option.default = False
            self.current_time = updated_time
            self.current_prix = None
            self.time_offset = None
            self.prixtype = 'public'
            self.selected_tracks = []
            self.track_selection_menu = False
            
            self.current_step += 1
        else:
            # Reset for the next round of choices
            # Clean up the Choice dropdown
            for option in self.select_choice.options:
                option.default = False
                
            # Clean up the Time dropdown (if it exists/is being used)
            for option in self.select_time.options:
                option.default = False

            # Clean up the Prix Type dropdown
            for option in self.select_prixtype.options:
                option.default = False

            # Check to see if mini prix or classic mini prix selected. If so, user will get option to select tracks.
            # Note: the dropdown implementation only works when there are 25 tracks or fewer.
            match self.current_prix:
                case "classicprix":
                    # 
                    self.track_select_1 = self.TrackSelect1(self, self.classic_track_options1, 1)
                    self.track_select_2 = self.TrackSelect2(self, self.classic_track_options2, 2)
                    self.track_select_3 = self.TrackSelect3(self, self.classic_track_options3, 3)
                    self.track_selection_menu = True
                # Note: selecting mini-prix tracks currently unavailable as there are 42 tracks
                # case "miniprix":
                #     self.track_select_1 = self.TrackSelect1(self, self.ninetynine_track_options1, 1)
                #     self.track_select_2 = self.TrackSelect2(self, self.ninetynine_track_options2, 2)
                #     self.track_select_3 = self.TrackSelect3(self, self.ninetynine_track_options3, 3)
                    self.track_selection_menu = True
                case _:
                    self.track_select_1 = None
                    self.track_select_2 = None
                    self.track_select_3 = None
                    self.track_selection_menu = False

                    # As no classicprix or miniprix schedule is required, save prix information now.
                    # Update time
                    updated_time = self.current_time + timedelta(minutes=int(self.time_offset))
                    self.all_results.append({"prix": self.current_prix, 
                                            "time": updated_time, 
                                            "prix_type": self.prixtype, 
                                            "lineup": self.selected_tracks
                                            })
                    # Reset to menu default options
                    self.current_time = updated_time
                    self.current_prix = None
                    self.time_offset = None
                    self.prixtype = 'public'

                    self.current_step += 1

        if self.current_step > self.num_prix:
            # # Final step
            await self.auto_or_manual_post(interaction)
        else:
            # Update button label for the last item
            if self.current_step == self.num_prix:
                button.label = "Finish"
            self.show_wizard_ui()
            await interaction.response.edit_message(content=self.get_content(), view=self)