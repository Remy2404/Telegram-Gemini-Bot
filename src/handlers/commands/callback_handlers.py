"""
Callback query handler for centralized callback routing.
Routes callback queries to appropriate command handlers.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging


class CallbackHandlers:
    def __init__(self, document_commands, model_commands, export_commands):
        self.document_commands = document_commands
        self.model_commands = model_commands
        self.export_commands = export_commands
        self.logger = logging.getLogger(__name__)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Central callback query handler that routes to appropriate handlers."""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        
        try:
            # Route AI document callbacks
            if callback_data.startswith(("aidoc_type_", "aidoc_format_", "aidoc_model_")):
                await self.document_commands.handle_ai_document_callback(update, context, callback_data)
            # Route document format callbacks
            elif callback_data.startswith("doc_format_"):
                await self.document_commands.handle_document_format_callback(update, context)
            # Route model selection callbacks - hierarchical selection
            elif callback_data.startswith("category_"):
                await self.model_commands.handle_category_selection(update, context)
            elif callback_data.startswith("model_"):
                await self.model_commands.handle_model_selection(update, context)
            elif callback_data == "back_to_categories":
                await self.model_commands.handle_back_to_categories(update, context)
            elif callback_data == "current_model":
                # Handle current model info directly
                await self._handle_current_model_callback(update, context)
            # Route export format callbacks
            elif callback_data.startswith("export_"):
                await self.export_commands.handle_export_callback(update, context)
            # Handle unknown callbacks
            else:
                self.logger.warning(f"Unknown callback data: {callback_data}")
                await query.edit_message_text("❌ Unknown action. Please try again.")
                
        except Exception as e:
            self.logger.error(f"Error handling callback query: {str(e)}")
            await query.edit_message_text("❌ An error occurred. Please try again.")

    async def _handle_current_model_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle current model info callback."""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get current model preference
        current_model = await self.model_commands.user_data_manager.get_user_preference(
            user_id, "preferred_model", default="gemini"
        )
        
        # Get current model configuration
        current_config = self.model_commands.api_manager.get_model_config(current_model)

        if current_config:
            message = (
                f"ℹ️ **Current Model Information**\n\n"
                f"**Name:** {current_config.emoji} {current_config.display_name}\n"
                f"**Provider:** {current_config.provider.value.title()}\n"
            )
            
            if current_config.description:
                message += f"**Description:** {current_config.description}\n"
            
            if hasattr(current_config, 'openrouter_key') and current_config.openrouter_key:
                message += f"**OpenRouter Key:** `{current_config.openrouter_key}`\n"
            
            message += f"\n✅ This model is currently active and ready to use!"
        else:
            message = f"❌ Current model '{current_model}' not found in configuration."

        # Add back button
        keyboard = [
            [
                InlineKeyboardButton(
                    "⬅️ Back to Categories", callback_data="back_to_categories"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            message, reply_markup=reply_markup, parse_mode="Markdown"
        )
