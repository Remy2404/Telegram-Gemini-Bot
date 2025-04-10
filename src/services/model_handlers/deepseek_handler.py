import asyncio
import logging
from typing import List, Dict, Any, Optional
from services.model_handlers import ModelHandler
from services.DeepSeek_R1_Distill_Llama_70B import DeepSeekLLM
from services.user_data_manager import UserDataManager

logger = logging.getLogger(__name__)

class DeepSeekHandler(ModelHandler):
    """Handler for the DeepSeek AI model."""
    
    def __init__(self, deepseek_api: DeepSeekLLM):
        """Initialize the DeepSeek model handler."""
        self.deepseek_llm = deepseek_api
        self.logger = logging.getLogger(__name__)
    
    async def generate_response(
        self, 
        prompt: str, 
        context: Optional[List[Dict[str, Any]]] = None, 
        temperature: float = 0.7, 
        max_tokens: int = 4000
    ) -> str:
        """Generate a text response using the DeepSeek model."""
        
        # Prepare messages list for the API
        messages = []
        system_message = self.get_system_message()
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Add context history if provided and log it for debugging
        if context:
            # Log the context being used
            context_length = len(context)
            self.logger.info(f"Using context with {context_length} messages")
            
            # Add a specific instruction to remind the model about conversation history
            if context_length > 0:
                memory_instruction = {
                    "role": "system",
                    "content": f"IMPORTANT: You have access to {context_length} previous messages in this conversation. You MUST use this history to maintain context and provide coherent responses. If asked about previous questions or context, refer to this history."
                }
                messages.append(memory_instruction)
            
            # Add all context messages with explicit logging
            for i, msg in enumerate(context):
                if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
                    self.logger.warning(f"Skipping invalid context message: {msg}")
                    continue
                    
                # Add the message to our API call messages list
                messages.append(msg)
                
                # Log this for debugging (truncated for readability)
                content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
                self.logger.debug(f"Context[{i}] - {msg['role']}: {content_preview}")
        else:
            self.logger.info("No conversation context provided")
            
        # Add the current user prompt
        messages.append({"role": "user", "content": prompt})
        
        # Log the full messages for debugging (only in serious debugging scenarios)
        # self.logger.debug(f"Full message context: {messages}")
        
        # Call the underlying LLM
        try:
            self.logger.info(f"Sending {len(messages)} messages to DeepSeek API")
            response = await asyncio.wait_for(
                self.deepseek_llm.generate_text(
                    messages=messages, # Pass the full message list
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=300.0,
            )
            self.logger.info(f"DeepSeek response received ({len(response) if response else 0} chars)")
            return response
        except Exception as e:
            self.logger.error(f"Error generating DeepSeek response: {str(e)}", exc_info=True)
            return "I encountered an error while processing your request. Please try again."
    
    def get_system_message(self) -> str:
        """Get the system message for the DeepSeek model."""
        return """You are DeepSeek, an AI assistant based on the DeepSeek-70B model. When introducing yourself, always refer to yourself as DeepSeek. Never introduce yourself as DeepGem or any other name. You help users with tasks and answer questions helpfully, accurately, and ethically.

IMPORTANT: You have a conversation memory and can remember previous exchanges with the user. If asked about previous questions or what was discussed earlier, reference your conversation history to provide an accurate response. Never tell the user you can't remember previous interactions unless your history is truly empty."""
    
    def get_model_indicator(self) -> str:
        """Get the model indicator emoji and name."""
        return "🔮 DeepSeek"