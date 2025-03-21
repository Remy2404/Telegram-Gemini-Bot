import logging
import google.generativeai as genai
# from google import genai_client
from typing import Optional, List, Dict, Any
import asyncio
import datetime
import sys
import os
from PIL import UnidentifiedImageError
# import io

from pyparsing import Any
from services.rate_limiter import RateLimiter, rate_limit
from utils.telegramlog import telegram_logger
from dotenv import load_dotenv
from services.image_processing import ImageProcessor
from database.connection import get_database, get_image_cache_collection
# import httpx
import time
import aiohttp
import traceback
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.auth.exceptions import TransportError
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, GoogleAPIError

load_dotenv() 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    telegram_logger.log_error("GEMINI_API_KEY not found in environment variables.", 0)
    sys.exit(1)

def safe_get(d: Optional[Dict], key: str, default: Any = None) -> Any:
    """Safely get a value from a dictionary."""
    return d.get(key, default) if d else default

class GeminiAPI:
    def __init__(self, vision_model, rate_limiter: RateLimiter):
        self.vision_model = vision_model
        self.rate_limiter = rate_limiter
        self.logger = logging.getLogger(__name__)
        telegram_logger.log_message("Initializing Gemini API", 0)

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found or empty")

        genai.configure(api_key=GEMINI_API_KEY)

        # Generation configuration
        self.generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 65536,
            "response_mime_type": "text/plain"
        }
        try:
            self.vision_model = genai.GenerativeModel("gemini-2.0-pro-exp-02-05")
            self.rate_limiter = RateLimiter(requests_per_minute=20)
            # Initialize MongoDB connection
            self.db, self.client = get_database()
            self.image_cache = get_image_cache_collection(self.db)
            if self.image_cache is not None:
                self.logger.info("Image cache collection is ready.")
            else:
                self.logger.error("Failed to access image cache collection.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini API: {str(e)}")
            raise

        # Add these properties for circuit breaker tracking
        self.api_failures = 0
        self.api_last_failure = 0
        self.image_generation_failures = 0
        self.image_generation_last_failure = 0
        self.image_analysis_failures = 0
        self.image_analysis_last_failure = 0
        self.circuit_breaker_threshold = 5  # Number of failures before opening circuit
        self.circuit_breaker_timeout = 300  # Seconds to keep circuit open (5 minutes)

        self.session = None
        self._initialize_session_lock = asyncio.Lock()
        self._connection_errors = 0
        self._last_error_time = 0
        self._consecutive_failures = 0
        self._backoff_time = 1.0  # Initial backoff in seconds

        # Add conversation history storage
        self.conversation_history = {}
        
        # Add user information cache to maintain persistent memory across interactions
        self.user_info_cache = {}

    async def ensure_session(self):
        """Create or reuse aiohttp session"""
        if self.session is None or self.session.closed:
            async with self._initialize_session_lock:
                if self.session is None or self.session.closed:
                    # Use optimized connection pooling settings
                    tcp_connector = aiohttp.TCPConnector(
                        limit=100,  # Connection limit
                        limit_per_host=20,  # Connections per host 
                        force_close=False,  # Keep connections alive
                        enable_cleanup_closed=True,  # Clean up closed connections
                        keepalive_timeout=60,  # Keepalive timeout in seconds
                    )
                    
                    # Create session with retry options
                    self.session = aiohttp.ClientSession(
                        connector=tcp_connector,
                        timeout=aiohttp.ClientTimeout(total=60, connect=10)
                    )
                    self.logger.debug("Created new aiohttp session for Gemini API")
        
        return self.session
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.logger.info("Closed Gemini API aiohttp session")
            self.session = None

    async def call_with_circuit_breaker(self, api_name, api_function, *args, **kwargs):
        """Call API with circuit breaker pattern to prevent cascading failures."""
        # Get the current failure count and last failure timestamp
        failures = getattr(self, f"{api_name}_failures", 0)
        last_failure = getattr(self, f"{api_name}_last_failure", 0)
        
        # Check if circuit is open (too many failures recently)
        if failures >= self.circuit_breaker_threshold and (time.time() - last_failure) < self.circuit_breaker_timeout:
            self.logger.warning(f"Circuit breaker open for {api_name} - too many recent failures")
            return None
        
        # Circuit is closed or half-open (allowing a test request)
        try:
            result = await api_function(*args, **kwargs)
            
            # If successful and we had previous failures, reset the counter
            if result and failures > 0:
                setattr(self, f"{api_name}_failures", 0)
                
            return result
            
        except Exception as e:
            # Track this failure
            setattr(self, f"{api_name}_failures", failures + 1)
            setattr(self, f"{api_name}_last_failure", time.time())
            self.logger.error(f"API failure for {api_name}: {str(e)}")
            raise

    async def format_message(self, text: str) -> str:
        """Format text for initial processing before Telegram Markdown formatting."""
        try:
            # Don't escape special characters here, just clean up the text
            # Remove any null characters or other problematic characters
            cleaned_text = text.replace('\x00', '').strip()
            return cleaned_text
        except Exception as e:
            logging.error(f"Error formatting message: {str(e)}")
            return text

    async def analyze_image(self, image_data: bytes, prompt: str) -> str:
        """Analyze an image and generate a response based on the prompt."""
        await self.rate_limiter.acquire()
        try:
            # Validate image first
            if not ImageProcessor.validate_image(image_data):
                return "Sorry, the image format is not supported. Please send a JPEG or PNG image."

            # Process the image and get the correct MIME type
            processed_image = await ImageProcessor.prepare_image(image_data)
            mime_type = ImageProcessor.get_mime_type(processed_image)
            
            # Generate response with proper error handling
            try:
                response = await asyncio.to_thread(
                    self.vision_model.generate_content,
                    [
                        prompt,  # First element is the text prompt
                        {"mime_type": mime_type, "data": processed_image}  # Use correct MIME type
                    ],
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    ],
                )
                
                if response and hasattr(response, 'text'):
                    formatted_response = await self.format_message(response.text)
                    return formatted_response
                else:
                    raise ValueError("Empty response from vision model")
                
            except Exception as e:
                logging.error(f"Vision model error: {str(e)}")
                return "I'm sorry, there was an error processing your image. Please try again later."
            
        except UnidentifiedImageError:
            logging.error("The provided image could not be identified.")
            return "Sorry, the image format is not supported. Please send a valid image."
        except Exception as e:
            telegram_logger.log_error(f"Image analysis error: {str(e)}", 0)
            return "I'm sorry, I encountered an error processing your image. Please try again with a different image."
    
    async def generate_image(self, prompt: str) -> Optional[bytes]:
        """
        Generate an image based on the provided text prompt using the Gemini API.
        Returns the image as bytes. Checks cache before generating a new image.
        """
        if self.image_cache is not None:
            cached_image = await asyncio.to_thread(
                self.image_cache.find_one, {"prompt": prompt}
            )
            if cached_image:
                self.logger.info(f"Cache hit for prompt: '{prompt}'")
                return cached_image['image_data']

        await self.rate_limiter.acquire()

        try:
            # Use the newer method for image generation
            response = await asyncio.to_thread(
                self.vision_model.generate_content,
                prompt,
                generation_config=self.generation_config,
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]
            )

            # Check if the response contains an image
            if response and response.parts and response.parts[0].images:
                image_bytes = response.parts[0].images[0].to_bytes()
                cache_document = {
                "prompt": prompt,
                "image_data": image_bytes,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "prompt": prompt,
                    "image_data": image_bytes,
                    "timestamp": datetime.datetime.utcnow()
                }
                try:
                    await asyncio.to_thread(
                        self.image_cache.insert_one, cache_document
                    )
                    self.logger.info(f"Cached image for prompt: '{prompt}'")
                except Exception as cache_error:
                    self.logger.error(f"Failed to cache image: {cache_error}")

                return image_bytes
            else:
                raise ValueError("No image data in response or empty response")

        except Exception as e:
            self.logger.error(f"Image generation error: {str(e)}")
            return None

    async def generate_image_with_imagen3(self, prompt: str) -> Optional[bytes]:
        """
        Generate an image using Google's Imagen API.
        Returns the image as bytes.
        """
        await self.rate_limiter.acquire()
            # import json
        try:
            # Use a proper configuration for image generation
            import httpx
            import json
            import base64
            
            # Update to use the recommended model
            url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY
            }
            
            # Format the request specifically for image generation
            data = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"Generate a high-quality, detailed image of: {prompt}. Return the image only without any text."
                            }
                        ]
                    }
                ],
                "generation_config": {
                    "temperature": 0.4,
                    "topP": 0.95,
                    "topK": 32,
                    "maxOutputTokens": 2048
                }
            }
            
            self.logger.info(f"Sending image generation request for: {prompt}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=data, timeout=60.0)
                
                # Handle error responses
                if response.status_code != 200:
                    self.logger.error(f"API error: {response.status_code} - {response.text}")
                    return None
                    
                response_data = response.json()
                
                # Extract the image data from the response
                    # mime_type = part['inline_data']['mime_type']
                for part in response_data['candidates'][0]['content']['parts']:
                        if 'inline_data' in part:  # Note: changed from 'inlineData' to 'inline_data'
                            # Extract base64 encoded image
                            mime_type = part['inline_data']['mime_type']
                            image_data = part['inline_data']['data']
                            binary_image = base64.b64decode(image_data)
                            
                            # Cache the image if cache is available
                            if self.image_cache:
                                cache_document = {
                                    "prompt": prompt,
                                    "image_data": binary_image,
                                    "model": "imagen3",
                                    "timestamp": datetime.datetime.utcnow()
                                }
                                await asyncio.to_thread(self.image_cache.insert_one, cache_document)
                            
                            self.logger.info(f"Successfully generated image for: {prompt}")
                            return binary_image
                
                self.logger.warning(f"No image found in response for prompt: {prompt}")
                return None
                        
        except Exception as e:
            self.logger.error(f"Imagen 3 generation error: {str(e)}")
            return None

    async def generate_response(self, prompt: str, context: List[Dict] = None, image_context: str = None, document_context: str = None) -> Optional[str]:
        """Generate a text response with circuit breaker protection."""
        try:
            return await self.call_with_circuit_breaker(
                "api", 
                self._generate_response_impl,  # Create a private implementation method
                prompt, context, image_context, document_context
            )
        except Exception as e:
            self.logger.error(f"Failed to generate response: {str(e)}")
            return "I'm sorry, I'm having trouble processing your request. Please try again later."
        
    async def _generate_response_impl(self, prompt: str, context: List[Dict] = None, image_context: str = None, document_context: str = None) -> Optional[str]:
        """Implementation of generate_response with proper error handling and context management."""
        await self.rate_limiter.acquire()
        
        try:
            # Prepare the conversation history
            conversation = []
            
            # Simplified system message without guidelines
            system_message = "You are DeepGem, an AI assistant that can help with various tasks."
            
            conversation.append(genai.types.ContentDict(
                role="user",
                parts=[system_message]
            ))
            
            # Add system context about memory capabilities
            memory_context = ("You have the ability to remember previous conversations including "
                            "descriptions of images and documents the user has shared. When answering, "
                            "consider text conversations, image descriptions, and document content in your context. "
                            "Reference relevant previous discussions when answering the user's current question.")
                            
            conversation.append(genai.types.ContentDict(
                role="user",
                parts=[memory_context]
            ))
            
            # Add image context if provided
            if image_context:
                conversation.append(genai.types.ContentDict(
                    role="user",
                    parts=[f"Image context: {image_context}"]
                ))
                
            # Add document context if provided
            if document_context:
                conversation.append(genai.types.ContentDict(
                    role="user",
                    parts=[f"Document context: {document_context}"]
                ))
            
            # Add conversation context - improved handling
            if context:
                # Ensure context isn't too long by taking the most recent entries
                max_context_entries = 15  # Increased from previous value
                recent_context = context[-max_context_entries:] if len(context) > max_context_entries else context
                
                # Add a reminder about conversation length
                if len(context) > max_context_entries:
                    conversation.append(genai.types.ContentDict(
                        role="user", 
                        parts=[f"Note: There are {len(context) - max_context_entries} earlier messages in our conversation that aren't shown here."]
                    ))
                
                # Process each context message
                for message in recent_context:
                        if isinstance(message, dict) and 'role' in message and 'content' in message:
                            role = message.get('role')
                            content = message.get('content')
                            if role and content:
                                conversation.append(genai.types.ContentDict(
                                    role="user" if role == "user" else "model",
                                    parts=[content]
                                ))
                                    
            # Add the current prompt to the conversation
            conversation.append(genai.types.ContentDict(
                role="user",
                parts=[prompt]
            ))
            
            # Generate the response with safety settings
            response = await asyncio.to_thread(
                self.vision_model.generate_content,
                conversation,
                generation_config=self.generation_config,
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]
            )

            # Process response
            if response and hasattr(response, 'text'):
                return response.text
            else:
                self.logger.warning("Empty or invalid response received from Gemini API")
                return None
        
        except Exception as e:
            self.logger.error(f"Error generating response in _generate_response_impl: {str(e)}")
            # Log the traceback for debugging
            self.logger.error(traceback.format_exc())
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable, TransportError)),
        reraise=True
    )
    @rate_limit
    async def generate_content(self, prompt: str, image_data: List = None) -> Dict[str, Any]:
        """
        Generate content from prompt with optional image
        
        Args:
            prompt: The text prompt 
            image_data: Optional list of image data
        
        Returns:
            Dictionary with response content
        """
        try:
            # Ensure we have a session
            await self.ensure_session()
            
            start_time = time.time()
            model = self.vision_model
            
            # Prepare the content parts
            content_parts = [prompt]
            
            if image_data:
                for img in image_data:
                    content_parts.append(img)
            
            # Generate the content with timeout protection
            response = await asyncio.wait_for(
                model.generate_content_async(
                    content_parts,
                    generation_config=self.generation_config,
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
                    ]
                ),
                timeout=45.0  # 45 second timeout
            )
            
            # Reset error counters on successful request
            self._consecutive_failures = 0
            self._backoff_time = 1.0
            
            # Process response
            time_taken = time.time() - start_time
            self.logger.debug(f"Gemini API request completed in {time_taken:.2f}s")
            
            if not hasattr(response, "candidates") or not response.candidates:
                return {
                    "status": "error",
                    "message": "No response from Gemini API",
                    "content": None
                }
            
            result = {
                "status": "success",
                "content": response.text,
                "prompt_feedback": getattr(response, "prompt_feedback", None),
                "usage_metadata": getattr(response, "usage_metadata", None)
            }
            
            return result
            
        except (ResourceExhausted, ServiceUnavailable, TransportError) as e:
            # Handle rate limiting and server errors with exponential backoff
            self._consecutive_failures += 1
            self.logger.warning(f"Gemini API temporary error (attempt {self._consecutive_failures}): {str(e)}")
            
            # Apply increasingly longer backoff for consecutive failures
            backoff = min(60, self._backoff_time * (2 ** (self._consecutive_failures - 1)))
            self._backoff_time = backoff
            
            await asyncio.sleep(backoff)
            raise  # Let the retry decorator handle it
            
        except asyncio.TimeoutError:
            self.logger.error("Gemini API request timed out after 45 seconds")
            return {
                "status": "error",
                "message": "Request to Gemini API timed out",
                "content": None
            }
            
        except GoogleAPIError as e:
            self.logger.error(f"Google API error: {str(e)}")
            return {
                "status": "error", 
                "message": f"Google API error: {str(e)}",
                "content": None
            }
            
        except Exception as e:
            self.logger.error(f"Unexpected error in generate_content: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
                "content": None
            }

    async def generate_content_with_retry(self, content, generation_config, max_retries=5):
        """Generate content with automatic retries and exponential backoff"""
        retry_delay = 1  # Start with 1 second

        for attempt in range(max_retries):
            async with self.rate_limiter:
                try:
                    # Use to_thread for synchronous API calls
                    response = await asyncio.to_thread(
                        self.vision_model.generate_content,
                        content, 
                        generation_config=generation_config
                    )
                    return response
                except Exception as e:
                    if attempt < max_retries - 1:  # Don't sleep on the last attempt
                        if "RATE_LIMIT_EXCEEDED" in str(e).upper():
                            self.logger.warning(f"Rate limit exceeded. Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            self.logger.error(f"Error generating content: {e}")
                            raise
                    else:
                        self.logger.error(f"Max retries ({max_retries}) exceeded. Unable to generate content.")
                        raise Exception("Service is currently unavailable. Please try again later.")