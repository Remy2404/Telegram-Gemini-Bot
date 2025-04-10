from typing import Dict, Type
from services.model_handlers import ModelHandler
from services.model_handlers.gemini_handler import GeminiHandler
from services.model_handlers.deepseek_handler import DeepSeekHandler
from services.model_handlers.quasar_alpha_handler import QuasarAlphaHandler
from services.gemini_api import GeminiAPI
from services.openrouter_api import OpenRouterAPI
from services.DeepSeek_R1_Distill_Llama_70B import DeepSeekLLM


class ModelHandlerFactory:
    """Factory class for creating model handlers."""

    _handlers: Dict[str, ModelHandler] = {}

    @classmethod
    def get_model_handler(
        cls,
        model_name: str,
        gemini_api: GeminiAPI = None,
        deepseek_api: DeepSeekLLM = None,
        openrouter_api: OpenRouterAPI = None,
    ) -> ModelHandler:
        """
        Get or create a model handler for the specified model.

        Args:
            model_name: The name of the model to get a handler for.
            gemini_api: An instance of GeminiAPI, required for Gemini model.
            deepseek_api: An instance of DeepSeekLLM, required for DeepSeek model.
            openrouter_api: An instance of OpenRouterAPI, required for Quasar Alpha model.

        Returns:
            An instance of ModelHandler for the specified model.
        """
        if model_name not in cls._handlers:
            if model_name == "gemini":
                if gemini_api is None:
                    raise ValueError(
                        "GeminiAPI instance is required for Gemini model handler"
                    )
                cls._handlers[model_name] = GeminiHandler(gemini_api)
            elif model_name == "deepseek":
                if deepseek_api is None:
                    raise ValueError(
                        "DeepSeekLLM instance is required for DeepSeek model handler"
                    )
                cls._handlers[model_name] = DeepSeekHandler(deepseek_api)
            elif model_name == "quasar_alpha":
                if openrouter_api is None:
                    raise ValueError(
                        "OpenRouter API instance is required for Quasar Alpha model handler"
                    )
                cls._handlers[model_name] = QuasarAlphaHandler(openrouter_api)
            else:
                raise ValueError(f"Unknown model: {model_name}")

        return cls._handlers[model_name]
