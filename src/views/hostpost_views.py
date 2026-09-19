'''
The post template editing views. The event setup wizard is `views/event_setup.py`.

by lurch, and the internet.
'''

import discord


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
