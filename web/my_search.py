# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""LocalSearch implementation."""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any
import json
import tiktoken

from graphrag.query.context_builder.builders import LocalContextBuilder
from graphrag.query.context_builder.conversation_history import (
    ConversationHistory,
)
from graphrag.query.llm.base import BaseLLM, BaseLLMCallback
from graphrag.query.llm.text_utils import num_tokens
from graphrag.query.structured_search.base import BaseSearch, SearchResult

from my_prompt import (
    LOCAL_SEARCH_SYSTEM_PROMPT,
)

DEFAULT_LLM_PARAMS = {
    "max_tokens": 400,
    "temperature": 0.0,
}

log = logging.getLogger(__name__)


class LocalSearch(BaseSearch):
    """Search orchestration for local search mode."""

    def search(self, query: str, conversation_history: ConversationHistory | None = None, **kwargs) -> SearchResult:
        pass

    def __init__(
            self,
            llm: BaseLLM,
            context_builder: LocalContextBuilder,
            token_encoder: tiktoken.Encoding | None = None,
            system_prompt: str = LOCAL_SEARCH_SYSTEM_PROMPT,
            response_type: str = "multiple paragraphs",
            callbacks: list[BaseLLMCallback] | None = None,
            llm_params: dict[str, Any] = DEFAULT_LLM_PARAMS,
            context_builder_params: dict | None = None,
    ):
        super().__init__(
            llm=llm,
            context_builder=context_builder,
            token_encoder=token_encoder,
            llm_params=llm_params,
            context_builder_params=context_builder_params or {},
        )
        self.system_prompt = system_prompt
        self.callbacks = callbacks
        self.response_type = response_type

    async def asearch(
            self,
            query: str,
            conversation_history: ConversationHistory | None = None,
            **kwargs,
    ) -> SearchResult:
        """Build local search context that fits a single context window and generate answer for the user query."""
        start_time = time.time()
        search_prompt = ""
        context_text, context_records = self.context_builder.build_context(
            query=query,
            conversation_history=conversation_history,
            **self.context_builder_params,
        )
        try:
            messages = self.reformat_message(context_text=context_text, message=kwargs['messages'])
            response = await self.llm.agenerate(
                messages=messages,
                streaming=True,
                callbacks=self.callbacks,
                **self.llm_params,
            )
            return SearchResult(
                response=response,
                context_data=context_records,
                context_text=context_text,
                completion_time=time.time() - start_time,
                llm_calls=1,
                prompt_tokens=num_tokens(search_prompt, self.token_encoder),
            )
        except Exception:
            log.exception("Exception in _asearch")
            return SearchResult(
                response="",
                context_data=context_records,
                context_text=context_text,
                completion_time=time.time() - start_time,
                llm_calls=1,
                prompt_tokens=num_tokens(search_prompt, self.token_encoder),
            )

    async def astream_search(
            self,
            query: str,
            conversation_history: ConversationHistory | None = None,
            **kwargs
    ) -> AsyncGenerator:
        """Build local search context that fits a single context window and generate answer for the user query."""
        context_text, context_records = self.context_builder.build_context(
            query=query,
            conversation_history=conversation_history,
            **self.context_builder_params,
        )
        messages = self.reformat_message(context_text=context_text, message=kwargs['messages'])
        yield context_records
        async for response in self.llm.astream_generate(  # type: ignore
                messages=messages,
                callbacks=self.callbacks,
                **self.llm_params,
        ):
            yield response

    def reformat_message(self, context_text: str, message: list) -> list:
        content = next((msg['content'] for msg in message if msg['role'] == 'system'), None)
        role = content or 'You are a helpful assistant responding to questions about data in the tables provided.'
        search_prompt = self.system_prompt.format(
            context_data=context_text, response_type=self.response_type, role=role
        )
        for msg in message:
            if msg['role'] == 'system':
                msg.update({"role": "system", "content": search_prompt})
                break
        else:
            message.insert(0, {"role": "system", "content": search_prompt})
        log.info("请求信息:\n" + json.dumps(message, indent=4, ensure_ascii=False))
        log.info("从向量数据库检索到的信息:\n" + context_text)
        return message
