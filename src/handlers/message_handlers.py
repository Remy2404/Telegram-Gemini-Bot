import os, io
import re
import tempfile
import logging
import speech_recognition as sr
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from pydub import AudioSegment
from handlers.text_handlers import TextHandler
from services.user_data_manager import UserDataManager
from telegram.ext import MessageHandler, filters
import datetime
from services.gemini_api import GeminiAPI
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List, Union
from functools import partial
import traceback
import gc
import time
import weakref
from telegram import Update, Message, Document
from telegram.ext import (
    MessageHandler, 
    filters, 
    ContextTypes, 
    CallbackContext
)
from src.services.gemini_api import GeminiAPI
from src.services.user_data_manager import user_data_manager
from src.utils.telegramlog import TelegramLogger
from src.services.document_processing import DocumentProcessor
from src.handlers.text_handlers import TextHandler

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(
<<<<<<< HEAD
        self,
        gemini_api,
        user_data_manager,
        telegram_logger,
        document_processor,
        text_handler,
    ):
=======
        self, 
        gemini_api: GeminiAPI, 
        user_data_manager: user_data_manager,
        telegram_logger: TelegramLogger,
        document_processor: DocumentProcessor,
        text_handler: TextHandler
    ):
        """Initialize the MessageHandlers with required services."""
>>>>>>> b6ce3f4bf02c0e1b6e292a535d84a30b2f904dff
        self.gemini_api = gemini_api
        self.user_data_manager = user_data_manager
        self.telegram_logger = telegram_logger
        self.document_processor = document_processor
<<<<<<< HEAD
        self.logger = logging.getLogger(__name__)

    async def _handle_text_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming text messages."""
        try:
            if update.message is None and update.callback_query is None:
                self.logger.error("Received update with no message or callback query")
                return

            if update.callback_query:
                user_id = update.callback_query.from_user.id
                message_text = update.callback_query.data
                await update.callback_query.answer()
            else:
                user_id = update.effective_user.id
                message_text = update.message.text

            self.logger.info(
                f"Received text message from user {user_id}: {message_text}"
            )

            # Check if the bot is mentioned
            bot_username = "@Gemini_AIAssistBot"
            if bot_username in message_text:
                self.logger.info(f"Bot mentioned by user {user_id}")
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        "Hello! How can I assist you today?"
                    )
                else:
                    await update.message.reply_text(
                        "Hello! How can I assist you today?"
                    )

            # Initialize user data if not already initialized
            await self.user_data_manager.initialize_user(user_id)

            # Create text handler instance
            text_handler = TextHandler(self.gemini_api, self.user_data_manager)

            # Process the message
            await text_handler.handle_text_message(update, context)
            await self.user_data_manager.update_user_stats(
                user_id, {"text_messages": 1, "total_messages": 1}
            )
        except Exception as e:
            self.logger.error(f"Error processing text message: {str(e)}")
            await self._error_handler(update, context)
        self.user_data_manager.update_stats(user_id, text_message=True)

    async def _handle_image_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming image messages."""
        try:
            user_id = update.effective_user.id
            self.telegram_logger.log_message(user_id, "Received image message")

            # Check if the bot is mentioned in the image caption
            bot_username = "@Gemini_AIAssistBot"
            if update.message.caption and bot_username in update.message.caption:
                self.logger.info(f"Bot mentioned by user {user_id} in image caption")
                await update.message.reply_text(
                    "I see you sent an image mentioning me. How can I assist you?"
                )

            # Initialize user data if not already initialized
            await self.user_data_manager.initialize_user(user_id)

            # Create text handler instance (which also handles images)
            text_handler = TextHandler(self.gemini_api, self.user_data_manager)

            # Process the image
            await text_handler.handle_image(update, context)
            await self.user_data_manager.update_user_stats(
                user_id, {"images": 1, "total_messages": 1}
            )
        except Exception as e:
            self.logger.error(f"Error processing image message: {str(e)}")
            await self._error_handler(update, context)
        self.user_data_manager.update_stats(user_id, image=True)

    async def _handle_voice_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming voice messages, enhanced for Khmer and multilingual support."""
        if not update.message or not update.message.voice:
            self.logger.error("Received update with no voice message")
            return

        user_id = update.effective_user.id
        conversation_id = f"user_{user_id}"
        self.telegram_logger.log_message("Received voice message", user_id)

        try:
            # First check user's language preference before doing any processing
            # This helps us optimize for the right language from the start
            user_lang = "en"  # Default to English

            try:
                # Get user's preferred language from database if available - this is critical for Khmer support
                preferred_lang = None

                # First check if there's an application-level user_data_manager
                if (
                    hasattr(context.application, "user_data_manager")
                    and context.application.user_data_manager
                ):
                    preferred_lang = (
                        await context.application.user_data_manager.get_user_preference(
                            user_id, "preferred_language", default=None
                        )
                    )

                # If not found, try the instance user_data_manager
                if not preferred_lang:
                    preferred_lang = await self.user_data_manager.get_user_preference(
                        user_id, "preferred_language", default=None
                    )

                # Also check in context.user_data for immediate preference set by /language command
                if not preferred_lang and "preferences" in context.user_data:
                    preferred_lang = context.user_data["preferences"].get("language")

                # Use the found language preference or fall back to Telegram's language code
                if preferred_lang:
                    user_lang = preferred_lang
                    self.logger.info(
                        f"Using user preferred language: {user_lang} for voice recognition"
                    )
                elif update.effective_user.language_code:
                    user_lang = update.effective_user.language_code
                    self.logger.info(
                        f"Using Telegram language code: {user_lang} for voice recognition"
                    )
            except Exception as lang_error:
                self.logger.warning(f"Error getting user language: {str(lang_error)}")
                # Continue with default English if we can't get the language preference

            # Enhanced language mapping with better Khmer support
            language_map = {
                "en": "en-US",
                "km": "km-KH",
                "kh": "km-KH",  # Alternative code sometimes used
                "ru": "ru-RU",
                "fr": "fr-FR",
                "es": "es-ES",
                "de": "de-DE",
                "ja": "ja-JP",
                "zh": "zh-CN",
                "th": "th-TH",
                "vi": "vi-VN",
            }

            # Extract language prefix properly
            lang_prefix = user_lang.split("-")[0] if "-" in user_lang else user_lang
            lang = language_map.get(lang_prefix, "en-US")

            # Set flag for Khmer processing - FORCE Khmer processing if user has set language to km/kh
            is_khmer = lang_prefix in ["km", "kh"]

            # Log the detected language for debugging
            self.logger.info(
                f"Voice recognition language set to: {lang}, is_khmer={is_khmer}"
            )

            # Show processing message in the appropriate language
            processing_text = (
                "កំពុងដំណើរការសារសំឡេងរបស់អ្នក... សូមរង់ចាំ...\n(Processing your voice message. Please wait...)"
                if is_khmer
                else "Processing your voice message. Please wait..."
            )

            status_message = await update.message.reply_text(processing_text)

            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the voice file
                file = await context.bot.get_file(update.message.voice.file_id)
                ogg_file_path = os.path.join(temp_dir, f"{user_id}_voice.ogg")
                await file.download_to_drive(ogg_file_path)

                # Apply specific audio processing for Khmer language
                wav_file_path = os.path.join(temp_dir, f"{user_id}_voice.wav")
                audio = AudioSegment.from_ogg(ogg_file_path)

                # Different audio processing for different languages
                if is_khmer:
                    # For Khmer, don't speed up, instead enhance clarity
                    enhanced_audio = audio.normalize()
                    # Higher quality settings for Khmer
                    enhanced_audio = enhanced_audio.set_frame_rate(16000)
                    enhanced_audio = enhanced_audio.set_channels(
                        1
                    )  # Mono for better speech recognition
                else:
                    # For other languages, slight speedup can help
                    enhanced_audio = audio.speedup(playback_speed=1.1)

                # Export with appropriate settings
                enhanced_audio.export(wav_file_path, format="wav")

                # Convert the voice file to text using speech recognition
                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_file_path) as source:
                    # Adjust for ambient noise - different durations based on language
                    recognizer.adjust_for_ambient_noise(
                        source, duration=1.0 if is_khmer else 0.5
                    )

                    # Adjust energy threshold based on language
                    recognizer.energy_threshold = 300 if is_khmer else 500
                    audio_data = recognizer.record(source)

                try:
                    # For Khmer, we'll use multiple attempts with different settings
                    text = ""
                    recognition_language = ""

                    if is_khmer:
                        # Log attempt to help debug
                        self.logger.info(
                            f"Attempting Khmer speech recognition for user {user_id}"
                        )

                        # Try multiple Khmer variants in sequence
                        khmer_variants = ["km-KH", "km", "kh"]
                        recognition_error = None

                        for variant in khmer_variants:
                            try:
                                self.logger.info(
                                    f"Trying speech recognition with language: {variant}"
                                )
                                text = recognizer.recognize_google(
                                    audio_data, language=variant
                                )
                                recognition_language = variant
                                # If successful, break out of the loop
                                break
                            except sr.UnknownValueError as e:
                                recognition_error = e
                                self.logger.warning(
                                    f"Recognition failed with {variant}, trying next variant"
                                )
                                # Try with lower energy threshold for the next attempt
                                recognizer.energy_threshold -= 50

                        # If all variants failed, raise the last error to trigger the error handler
                        if not text and recognition_error:
                            raise recognition_error
                    else:
                        # For non-Khmer languages, use standard recognition with the detected language
                        text = recognizer.recognize_google(audio_data, language=lang)
                        recognition_language = lang

                    # Log successful recognition
                    self.logger.info(
                        f"Successfully recognized speech with language {recognition_language}: '{text}'"
                    )

                    # Delete the status message safely
                    try:
                        await status_message.delete()
                    except Exception as msg_error:
                        self.logger.warning(
                            f"Could not delete status message: {str(msg_error)}"
                        )
                        # Try to update instead if we can't delete
                        try:
                            await status_message.edit_text("✓ Processing complete")
                        except:
                            pass

                    # Show the transcribed text to the user
                    transcript_text = (
                        f"🎤 *បំលែងសំឡេងទៅជាអក្សរ (Transcription)*: \n{text}"
                        if is_khmer
                        else f"🎤 *Transcription*: \n{text}"
                    )

                    # Use safe_reply to handle the flood control issue
                    try:
                        if hasattr(self, "_safe_reply") and callable(self._safe_reply):
                            transcript_message = await self._safe_reply(
                                update.message, transcript_text, parse_mode="Markdown"
                            )
                        else:
                            # Fall back to regular reply if _safe_reply doesn't exist
                            transcript_message = await update.message.reply_text(
                                transcript_text, parse_mode="Markdown"
                            )
                    except Exception as reply_error:
                        self.logger.error(
                            f"Error sending transcript message: {str(reply_error)}"
                        )
                        # Try without markdown
                        transcript_message = await update.message.reply_text(
                            f"🎤 Transcription: \n{text}"
                        )

                    # Log the transcribed text
                    self.telegram_logger.log_message(
                        f"Transcribed {recognition_language} text: {text}", user_id
                    )

                    # Initialize user data if not already initialized
                    await self.user_data_manager.initialize_user(user_id)

                    # Get text handler instance
                    text_handler = self.text_handler

                    # Store voice message in MemoryManager with language metadata
                    try:
                        # Only add to memory manager if it exists and is properly initialized
                        if (
                            text_handler is not None
                            and hasattr(text_handler, "memory_manager")
                            and text_handler.memory_manager is not None
                        ):

                            # Use proper language label
                            language_label = "km" if is_khmer else lang.split("-")[0]

                            # Store with clear language marking
                            await text_handler.memory_manager.add_user_message(
                                conversation_id,
                                f"[Voice message in {language_label} language: {text}]",
                                str(user_id),
                                language=language_label,  # Add language metadata
                            )
                    except Exception as mem_error:
                        self.logger.error(
                            f"Error adding to memory manager: {str(mem_error)}"
                        )
                        # Continue processing even if memory manager fails

                    # Create a new Update object with the transcribed text
                    new_update = Update.de_json(
                        {
                            "update_id": update.update_id,
                            "message": {
                                "message_id": update.message.message_id,
                                "date": update.message.date.timestamp(),
                                "chat": update.message.chat.to_dict(),
                                "from": update.message.from_user.to_dict(),
                                "text": text,
                            },
                        },
                        context.bot,
                    )

                    # Process the transcribed text as if it were a regular text message
                    await text_handler.handle_text_message(new_update, context)

                    # Update user stats with language information
                    try:
                        # Check if the update_user_stats method exists and is callable
                        if hasattr(
                            self.user_data_manager, "update_user_stats"
                        ) and callable(self.user_data_manager.update_user_stats):
                            stats_update = {"voice_messages": 1, "total_messages": 1}

                            # Add language-specific stat if we have language info
                            if is_khmer:
                                stats_update["voice_messages_km"] = 1
                            else:
                                language_label = (
                                    lang.split("-")[0] if "-" in lang else lang
                                )
                                stats_update[f"voice_messages_{language_label}"] = 1

                            # Use the method
                            update_result = self.user_data_manager.update_user_stats(
                                user_id, stats_update
                            )

                            # Handle both sync and async implementations
                            if asyncio.iscoroutine(update_result):
                                await update_result
                        else:
                            # Fallback to update_stats if available
                            self.user_data_manager.update_stats(
                                user_id, voice_message=True
                            )
                    except Exception as stats_error:
                        self.logger.error(
                            f"Error updating user stats: {str(stats_error)}"
                        )
                        # Try the simple update_stats method as fallback
                        try:
                            if hasattr(self.user_data_manager, "update_stats"):
                                self.user_data_manager.update_stats(
                                    user_id, voice_message=True
                                )
                        except:
                            pass

                except sr.UnknownValueError:
                    # Language-specific error message
                    error_text = (
                        "សូមអភ័យទោស មិនអាចយល់សំឡេងបានទេ។ សូមសាកល្បងម្តងទៀតជាមួយសំឡេងច្បាស់ជាងនេះ។\n\n"
                        "Sorry, I couldn't understand the audio. Please try again with clearer audio."
                        if is_khmer
                        else "Sorry, I couldn't understand the audio. Please try again with clearer audio."
                    )

                    # Update status message instead of deleting
                    try:
                        await status_message.edit_text(error_text)
                    except Exception as edit_error:
                        self.logger.warning(
                            f"Could not edit status message: {str(edit_error)}"
                        )
                        # Try to send a new message if editing fails
                        try:
                            await update.message.reply_text(error_text)
                        except:
                            pass

                except sr.RequestError as e:
                    self.logger.error(
                        f"Could not request results from Google Speech Recognition service; {e}"
                    )
                    # Update status message instead of deleting
                    try:
                        await status_message.edit_text(
                            "Sorry, there was an error processing your voice message. Please try again later."
                        )
                    except:
                        try:
                            await update.message.reply_text(
                                "Sorry, there was an error processing your voice message. Please try again later."
                            )
                        except:
                            pass

        except Exception as e:
            self.logger.error(f"Error processing voice message: {str(e)}")
            try:
                if "status_message" in locals() and status_message:
                    try:
                        await status_message.edit_text(
                            "Sorry, there was an error processing your voice message. Please try again later."
                        )
                    except:
                        pass
            except:
                pass

    async def _safe_reply(
        self, message, text, parse_mode=None, retry_delay=5, max_retries=3
    ):
        """Safely reply to a message with built-in flood control handling"""
        for attempt in range(max_retries):
            try:
                return await message.reply_text(text, parse_mode=parse_mode)
            except Exception as e:
                error_str = str(e).lower()
                if "flood" in error_str and "retry" in error_str:
                    # Parse retry time from error message like "Flood control exceeded. Retry in 134 seconds"
                    retry_seconds = 5  # Default retry time
                    try:
                        retry_match = re.search(r"retry in (\d+)", error_str)
                        if retry_match:
                            retry_seconds = int(retry_match.group(1))
                            # Cap the retry time to avoid excessive waits
                            retry_seconds = min(retry_seconds, 10)
                    except:
                        pass

                    self.logger.warning(
                        f"Hit flood control, waiting {retry_seconds} seconds"
                    )
                    # Wait the required time plus a small buffer
                    await asyncio.sleep(retry_seconds + 1)
                    continue
                elif attempt < max_retries - 1:
                    # For other errors, retry with a fixed delay
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    # For the last attempt, try without parse_mode
                    if parse_mode and attempt == max_retries - 1:
                        return await message.reply_text(text, parse_mode=None)
                    raise

        # Fallback - if all retries failed, try one last time without any formatting
        try:
            return await message.reply_text(
                text.replace("*", "").replace("_", "").replace("`", "")
            )
        except Exception as last_error:
            self.logger.error(
                f"Failed to send message after all retries: {str(last_error)}"
            )
            return None

    async def _handle_document_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle incoming document messages."""
        user_id = update.effective_user.id
        self.logger.info(f"Processing document for user: {user_id}")

        try:
            document = update.message.document
            file = await context.bot.get_file(document.file_id)
            file_extension = document.file_name.split(".")[-1]

            response = await self.document_processor.process_document_from_file(
                file=await file.download_as_bytearray(),
                file_extension=file_extension,
                prompt="Analyze this document.",
            )

            formatted_response = await self.text_handler.format_telegram_markdown(
                response
            )
            await update.message.reply_text(
                formatted_response,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )

            self.user_data_manager.update_stats(user_id, document=True)
            self.telegram_logger.log_message(
                "Document processed successfully.", user_id
            )

        except Exception as e:
            self.logger.error(f"Error processing document: {e}")
            if "RATE_LIMIT_EXCEEDED" in str(e).upper():
                await update.message.reply_text(
                    "The service is currently experiencing high demand. Please try again later."
                )
            else:
                await self._error_handler(update, context)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.telegram_logger.log_message("Processing document", user_id)

        try:
            # Check if the message is in a group chat
            if update.effective_chat.type in ["group", "supergroup"]:
                # Process only if the bot is mentioned in the caption
                bot_username = "@" + context.bot.username
                caption = update.message.caption or ""
                if bot_username not in caption:
                    return
                else:
                    # Remove bot mention
                    caption = caption.replace(bot_username, "").strip()
            else:
                caption = update.message.caption or "Please analyze this document."

            # Get basic document information
            document = update.message.document
            file_name = document.file_name
            file_id = document.file_id
            file_extension = (
                os.path.splitext(file_name)[1][1:] if "." in file_name else ""
            )

            # Send typing action and status message
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            status_message = await update.message.reply_text(
                f"Processing your {file_extension.upper()} document... This might take a moment."
            )

            # Download and process the document
            document_file = await context.bot.get_file(file_id)
            file_content = await document_file.download_as_bytearray()
            document_file_obj = io.BytesIO(file_content)

            # Default prompt if caption is empty
            prompt = (
                caption
                or f"Please analyze this {file_extension.upper()} file and provide a detailed summary."
            )

            # Use enhanced document processing for PDFs
            if file_extension.lower() == "pdf":
                response = await self.document_processor.process_document_enhanced(
                    file=document_file_obj, file_extension=file_extension, prompt=prompt
                )
            else:
                response = await self.document_processor.process_document_from_file(
                    file=document_file_obj, file_extension=file_extension, prompt=prompt
                )

            # Delete status message
            await status_message.delete()

            if response:
                # Split long messages
                response_chunks = await self.text_handler.split_long_message(response)
                sent_messages = []

                # Send each chunk
                for chunk in response_chunks:
                    try:
                        formatted_chunk = (
                            await self.text_handler.format_telegram_markdown(chunk)
                        )
                        sent_message = await update.message.reply_text(
                            formatted_chunk,
                            parse_mode="MarkdownV2",
                            disable_web_page_preview=True,
                        )
                        sent_messages.append(sent_message.message_id)
                    except Exception as markdown_error:
                        self.logger.warning(
                            f"Markdown formatting failed: {markdown_error}"
                        )
                        sent_message = await update.message.reply_text(
                            chunk, parse_mode=None
                        )
                        sent_messages.append(sent_message.message_id)

                # Store document info in user context
                self.user_data_manager.add_to_context(
                    user_id,
                    {
                        "role": "user",
                        "content": f"[Document: {file_name} with prompt: {prompt}]",
                    },
                )
                self.user_data_manager.add_to_context(
                    user_id, {"role": "assistant", "content": response}
                )

                # Store document reference in user data (NEW)
                if "document_history" not in context.user_data:
                    context.user_data["document_history"] = []

                # Store document info in user data (OLD)
                context.user_data["document_history"].append(
                    {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "file_id": file_id,
                        "file_name": file_name,
                        "file_extension": file_extension,
                        "prompt": prompt,
                        "summary": (
                            response[:300] + "..." if len(response) > 300 else response
                        ),
                        "full_response": response,  # Critical for follow-up questions
                        "message_id": update.message.message_id,
                        "response_message_ids": [
                            msg.message_id for msg in sent_messages
                        ],
                    }
                )

                # Update user stats
                if self.user_data_manager:
                    self.user_data_manager.update_stats(user_id, document=True)

                self.telegram_logger.log_message(
                    f"Document analysis completed successfully", user_id
                )
            else:
                await update.message.reply_text(
                    "Sorry, I couldn't analyze the document. Please try again."
                )

        except ValueError as ve:
            await update.message.reply_text(f"Error: {str(ve)}")
        except Exception as e:
            self.logger.error(f"Error processing document: {str(e)}")
            await update.message.reply_text(
                "Sorry, I couldn't process your document. Please ensure it's in a supported format."
            )

    async def _error_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle errors occurring in the dispatcher."""
        self.logger.error(f"Update {update} caused error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "An error occurred while processing your request. Please try again later."
            )

    async def _error_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle errors occurring in the dispatcher."""
        self.logger.error(f"Update {update} caused error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "An error occurred while processing your request. Please try again later."
            )

    def register_handlers(self, application):
        """Register message handlers with the application."""
        try:
            application.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, self._handle_text_message
                )
            )
            application.add_handler(
                MessageHandler(filters.PHOTO, self._handle_image_message)
            )
            application.add_handler(
                MessageHandler(filters.VOICE, self._handle_voice_message)
            )
            application.add_handler(
                MessageHandler(filters.Document.ALL, self._handle_document_message)
            )

            application.add_error_handler(self._error_handler)
            self.logger.info("Message handlers registered successfully")
        except Exception as e:
            self.logger.error(f"Failed to register message handlers: {str(e)}")
            raise Exception("Failed to register message handlers") from e
=======
        self.text_handler = text_handler
        
        # Use a thread pool for CPU-bound operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Active requests tracking with weak references to avoid memory leaks
        self.active_requests = weakref.WeakSet()
        self.request_limiter = asyncio.Semaphore(20)  # Limit concurrent requests
        
        logger.info("MessageHandlers initialized with optimized concurrency settings")
        
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document uploads with improved memory management."""
        if not update.message or not update.message.document:
            return
            
        user_id = update.effective_user.id
        self.telegram_logger.log_message(f"Document received: {update.message.document.file_name}", user_id)
        
        async def process_document():
            try:
                # Acquire semaphore to limit concurrent processing
                async with self.request_limiter:
                    # Set typing status
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                    
                    # First send acknowledgment message
                    status_message = await update.message.reply_text("Processing your document...")
                    
                    # Process document in background with timeout protection
                    try:
                        document = update.message.document
                        start_time = time.time()
                        
                        # Download file with timeout
                        file = await asyncio.wait_for(
                            context.bot.get_file(document.file_id),
                            timeout=30.0
                        )
                        
                        # Process document
                        file_bytes = await file.download_as_bytearray()
                        
                        # Get document content using the document processor
                        content = await self.document_processor.process_document(
                            file_bytes, 
                            document.file_name,
                            document.mime_type
                        )
                        
                        processing_time = time.time() - start_time
                        logger.info(f"Document processed in {processing_time:.2f}s: {document.file_name}")
                        
                        if content:
                            # Save document to user's history
                            await self.user_data_manager.save_document_to_history(
                                user_id, 
                                document.file_name, 
                                document.file_unique_id, 
                                document.mime_type, 
                                content[:1000]  # Store truncated preview
                            )
                            
                            # Send summary and generate response
                            await status_message.edit_text(f"📄 Document '{document.file_name}' processed successfully!")
                            
                            # Let the user know document content is available via history
                            instruction_msg = (
                                "I've saved your document content. You can now ask me questions about it, "
                                "and I'll analyze its contents."
                            )
                            await update.message.reply_text(instruction_msg)
                            
                        else:
                            await status_message.edit_text(
                                f"❌ Sorry, I couldn't process '{document.file_name}'. "
                                "The file may be too large, corrupted, or in an unsupported format."
                            )
                    except asyncio.TimeoutError:
                        await status_message.edit_text("⏱️ Document processing timed out. The file may be too large.")
                        logger.warning(f"Document processing timed out for user {user_id}: {document.file_name}")
            except Exception as e:
                error_message = f"Error processing document: {str(e)}"
                logger.error(error_message)
                logger.error(traceback.format_exc())
                self.telegram_logger.log_error(e, user_id)
                
                try:
                    await update.message.reply_text(
                        "Sorry, I couldn't process your document. Please try a different format or a smaller file."
                    )
                except Exception:
                    pass
            finally:
                # Force garbage collection to free memory from large documents
                gc.collect()
        
        # Create background task for processing
        task = asyncio.create_task(process_document())
        self.active_requests.add(task)
        
    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle image messages with improved error handling and memory management."""
        if not update.message or not update.message.photo:
            return
            
        user_id = update.effective_user.id
        self.telegram_logger.log_message("Image received", user_id)
        
        async def process_image():
            try:
                async with self.request_limiter:
                    # Set typing action
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                    
                    # Get the highest resolution image
                    photo = update.message.photo[-1]
                    
                    # Extract caption or use default prompt
                    caption = update.message.caption or "Analyze this image in detail"
                    
                    # Get image file with timeout
                    try:
                        file = await asyncio.wait_for(
                            context.bot.get_file(photo.file_id),
                            timeout=15.0  # 15 second timeout for file retrieval
                        )
                        
                        # Download image as bytes
                        image_bytes = await file.download_as_bytearray()
                        
                        # Process the image and generate a response with the gemini_api
                        response = await asyncio.wait_for(
                            self.gemini_api.analyze_image(image_bytes, caption),
                            timeout=45.0  # 45 second timeout for processing
                        )
                        
                        if response:
                            # Send response in chunks if needed
                            if len(response) > 4000:
                                for i in range(0, len(response), 4000):
                                    chunk = response[i:i+4000]
                                    await update.message.reply_text(chunk)
                            else:
                                await update.message.reply_text(response)
                                
                            # Save interaction to user history
                            await self.user_data_manager.save_image_analysis_to_history(
                                user_id,
                                photo.file_unique_id,
                                caption,
                                response[:500]  # Save truncated response
                            )
                        else:
                            await update.message.reply_text(
                                "Sorry, I couldn't analyze this image. Please try a different image."
                            )
                            
                    except asyncio.TimeoutError:
                        await update.message.reply_text("The operation timed out. Please try again with a smaller image.")
                        
            except Exception as e:
                error_message = f"Error processing image: {str(e)}"
                logger.error(error_message)
                logger.error(traceback.format_exc())
                self.telegram_logger.log_error(e, user_id)
                
                try:
                    await update.message.reply_text("Sorry, there was an error processing your image.")
                except Exception:
                    pass
            finally:
                # Clean up resources
                gc.collect()
                
        # Create background task for processing
        task = asyncio.create_task(process_image())
        self.active_requests.add(task)
        
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors with detailed logging and graceful user communication."""
        try:
            if update and isinstance(update, Update) and update.effective_chat:
                user_id = update.effective_user.id if update.effective_user else 0
                chat_id = update.effective_chat.id
                
                # Log the error
                logger.error(f"Error for user {user_id}: {context.error}")
                logger.error(traceback.format_exc())
                self.telegram_logger.log_error(context.error, user_id)
                
                # Send user-friendly error message
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="Sorry, something went wrong processing your request. Please try again later."
                    )
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {send_error}")
            else:
                logger.error(f"Update caused error without chat context: {context.error}")
                logger.error(traceback.format_exc())
                
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
            logger.error(traceback.format_exc())
            
    def register_handlers(self, application) -> None:
        """Register all message handlers with the application."""
        # Handle documents (PDFs, DOCs, etc.)
        application.add_handler(MessageHandler(
            filters.Document.ALL & ~filters.COMMAND, 
            self.handle_document
        ))
        
        # Handle images
        application.add_handler(MessageHandler(
            filters.PHOTO & ~filters.COMMAND, 
            self.handle_image
        ))
        
    async def cleanup(self):
        """Clean up resources and cancel pending requests."""
        try:
            # Cancel all active tasks
            active_tasks = list(self.active_requests)
            if active_tasks:
                logger.info(f"Cancelling {len(active_tasks)} pending message handler tasks")
                for task in active_tasks:
                    if not task.done():
                        task.cancel()
                        
                # Wait for tasks to be cancelled
                await asyncio.gather(*active_tasks, return_exceptions=True)
                
            # Shutdown thread pool
            self.executor.shutdown(wait=False)
            logger.info("Message handlers cleaned up successfully")
            
        except Exception as e:
            logger.error(f"Error during message handler cleanup: {e}")
            logger.error(traceback.format_exc())
>>>>>>> b6ce3f4bf02c0e1b6e292a535d84a30b2f904dff
