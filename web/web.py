import os
import asyncio
import time
import uuid
import json
import re
import pandas as pd
import tiktoken
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(".env")

# GraphRAG 相关导入
from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
from graphrag.query.indexer_adapters import (
    read_indexer_covariates,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_reports,
    read_indexer_text_units,
)

from graphrag.query.input.loaders.dfs import store_entity_semantic_embeddings
from graphrag.query.llm.oai.chat_openai import ChatOpenAI
from graphrag.query.llm.oai.embedding import OpenAIEmbedding
from graphrag.query.llm.oai.typing import OpenaiApiType
from graphrag.query.question_gen.local_gen import LocalQuestionGen
from graphrag.query.structured_search.local_search.mixed_context import LocalSearchMixedContext
from my_search import LocalSearch
from graphrag.query.structured_search.global_search.community_context import GlobalCommunityContext
from graphrag.query.structured_search.global_search.search import GlobalSearch
from graphrag.vector_stores.lancedb import LanceDBVectorStore

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置常量和配置
INPUT_DIR = os.getenv('INPUT_DIR')
LANCEDB_URI = f"{INPUT_DIR}/lancedb"
COMMUNITY_REPORT_TABLE = "create_final_community_reports"
ENTITY_TABLE = "create_final_nodes"
ENTITY_EMBEDDING_TABLE = "create_final_entities"
RELATIONSHIP_TABLE = "create_final_relationships"
COVARIATE_TABLE = "create_final_covariates"
TEXT_UNIT_TABLE = "create_final_text_units"
COMMUNITY_LEVEL = 2
PORT = 8012

# 全局变量，用于存储搜索引擎和问题生成器
local_search_engine = None
global_search_engine = None
question_generator = None


# 数据模型
class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0
    frequency_penalty: Optional[float] = 0
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None


class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: Message
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: Usage
    system_fingerprint: Optional[str] = None


async def setup_llm_and_embedder():
    """
    设置语言模型（LLM）和嵌入模型
    """
    logger.info("正在设置LLM和嵌入器")

    # 获取API密钥和基础URL
    api_key = os.environ.get("GRAPHRAG_API_KEY", "")
    api_key_embedding = os.environ.get("GRAPHRAG_API_KEY_EMBEDDING", api_key)
    api_base = os.environ.get("API_BASE", "")
    api_base_embedding = os.environ.get("API_BASE_EMBEDDING", "")
    # 获取模型名称
    llm_model = os.environ.get("GRAPHRAG_LLM_MODEL", "")
    embedding_model = os.environ.get("GRAPHRAG_EMBEDDING_MODEL", "")

    # 初始化ChatOpenAI实例
    llm = ChatOpenAI(
        api_key=api_key,
        api_base=api_base,
        model=llm_model,
        api_type=OpenaiApiType.OpenAI,
        max_retries=20,
    )

    # 初始化token编码器
    token_encoder = tiktoken.get_encoding("cl100k_base")

    # 初始化文本嵌入模型
    text_embedder = OpenAIEmbedding(
        api_key=api_key_embedding,
        api_base=api_base_embedding,
        api_type=OpenaiApiType.OpenAI,
        model=embedding_model,
        deployment_name=embedding_model,
        max_retries=20,
    )

    logger.info("LLM和嵌入器设置完成")
    return llm, token_encoder, text_embedder


async def load_context():
    """
    加载上下文数据，包括实体、关系、报告、文本单元和协变量
    """
    logger.info("正在加载上下文数据")
    try:
        entity_df = pd.read_parquet(f"{INPUT_DIR}/{ENTITY_TABLE}.parquet")
        entity_embedding_df = pd.read_parquet(f"{INPUT_DIR}/{ENTITY_EMBEDDING_TABLE}.parquet")
        entities = read_indexer_entities(entity_df, entity_embedding_df, COMMUNITY_LEVEL)

        description_embedding_store = LanceDBVectorStore(collection_name="entity_description_embeddings")
        description_embedding_store.connect(db_uri=LANCEDB_URI)
        store_entity_semantic_embeddings(entities=entities, vectorstore=description_embedding_store)

        relationship_df = pd.read_parquet(f"{INPUT_DIR}/{RELATIONSHIP_TABLE}.parquet")
        relationships = read_indexer_relationships(relationship_df)

        report_df = pd.read_parquet(f"{INPUT_DIR}/{COMMUNITY_REPORT_TABLE}.parquet")
        reports = read_indexer_reports(report_df, entity_df, COMMUNITY_LEVEL)

        text_unit_df = pd.read_parquet(f"{INPUT_DIR}/{TEXT_UNIT_TABLE}.parquet")
        text_units = read_indexer_text_units(text_unit_df)

        covariate_df = pd.read_parquet(f"{INPUT_DIR}/{COVARIATE_TABLE}.parquet")
        claims = read_indexer_covariates(covariate_df)
        logger.info(f"声明记录数: {len(claims)}")
        covariates = {"claims": claims}

        logger.info("上下文数据加载完成")
        return entities, relationships, reports, text_units, description_embedding_store, covariates
    except Exception as e:
        logger.error(f"加载上下文数据时出错: {str(e)}")
        raise


async def setup_search_engines(llm, token_encoder, text_embedder, entities, relationships, reports, text_units,
                               description_embedding_store, covariates):
    """
    设置本地搜索引擎和全局搜索引擎
    """
    logger.info("正在设置搜索引擎")

    # 设置本地搜索引擎
    local_context_builder = LocalSearchMixedContext(
        community_reports=reports,
        text_units=text_units,
        entities=entities,
        relationships=relationships,
        covariates=covariates,
        entity_text_embeddings=description_embedding_store,
        embedding_vectorstore_key=EntityVectorStoreKey.ID,
        text_embedder=text_embedder,
        token_encoder=token_encoder,
    )

    local_context_params = {
        "text_unit_prop": 0.5,
        "community_prop": 0.1,
        "conversation_history_max_turns": 5,
        "conversation_history_user_turns_only": True,
        "top_k_mapped_entities": 10,
        "top_k_relationships": 10,
        "include_entity_rank": True,
        "include_relationship_weight": True,
        "include_community_rank": False,
        "return_candidate_context": False,
        "embedding_vectorstore_key": EntityVectorStoreKey.ID,
        "max_tokens": 400,
    }

    local_llm_params = {
        "max_tokens": 2_000,
        "temperature": 0.0,
    }

    local_search_engine = LocalSearch(
        llm=llm,
        context_builder=local_context_builder,
        token_encoder=token_encoder,
        llm_params=local_llm_params,
        context_builder_params=local_context_params,
        response_type="multiple paragraphs",
    )

    # 设置全局搜索引擎
    global_context_builder = GlobalCommunityContext(
        community_reports=reports,
        entities=entities,
        token_encoder=token_encoder,
    )

    global_context_builder_params = {
        "use_community_summary": False,
        "shuffle_data": True,
        "include_community_rank": True,
        "min_community_rank": 0,
        "community_rank_name": "rank",
        "include_community_weight": True,
        "community_weight_name": "occurrence weight",
        "normalize_community_weight": True,
        "max_tokens": 12_000,
        "context_name": "Reports",
    }

    map_llm_params = {
        "max_tokens": 1000,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }

    reduce_llm_params = {
        "max_tokens": 2000,
        "temperature": 0.0,
    }

    global_search_engine = GlobalSearch(
        llm=llm,
        context_builder=global_context_builder,
        token_encoder=token_encoder,
        max_data_tokens=12_000,
        map_llm_params=map_llm_params,
        reduce_llm_params=reduce_llm_params,
        allow_general_knowledge=False,
        json_mode=True,
        context_builder_params=global_context_builder_params,
        concurrent_coroutines=32,
        response_type="multiple paragraphs",
    )

    logger.info("搜索引擎设置完成")
    return local_search_engine, global_search_engine, local_context_builder, local_llm_params, local_context_params


def format_response(response):
    """
    格式化响应，添加适当的换行和段落分隔。
    """
    paragraphs = re.split(r'\n{2,}', response)
    formatted_paragraphs = []
    for para in paragraphs:
        if '```' in para:
            parts = para.split('```')
            for i, part in enumerate(parts):
                if i % 2 == 1:  # 这是代码块
                    parts[i] = f"\n```\n{part.strip()}\n```\n"
            para = ''.join(parts)
        else:
            para = para.replace('. ', '.\n')
        formatted_paragraphs.append(para.strip())
    return '\n\n'.join(formatted_paragraphs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    global local_search_engine, global_search_engine, question_generator
    try:
        logger.info("正在初始化搜索引擎和问题生成器...")
        llm, token_encoder, text_embedder = await setup_llm_and_embedder()
        entities, relationships, reports, text_units, description_embedding_store, covariates = await load_context()
        local_search_engine, global_search_engine, local_context_builder, local_llm_params, local_context_params = await setup_search_engines(
            llm, token_encoder, text_embedder, entities, relationships, reports, text_units,
            description_embedding_store, covariates
        )
        question_generator = LocalQuestionGen(
            llm=llm,
            context_builder=local_context_builder,
            token_encoder=token_encoder,
            llm_params=local_llm_params,
            context_builder_params=local_context_params,
        )
        logger.info("初始化完成。")
    except Exception as e:
        logger.error(f"初始化过程中出错: {str(e)}")
        raise

    yield

    # 关闭时执行
    logger.info("正在关闭...")


app = FastAPI(lifespan=lifespan)


# 在 chat_completions 函数中添加以下代码

async def full_model_search(prompt: str):
    """
    执行全模型搜索，包括本地检索、全局检索和 Tavily 搜索
    """
    local_result = await local_search_engine.asearch(prompt)
    global_result = await global_search_engine.asearch(prompt)
    # tavily_result = await tavily_search(prompt)

    # 格式化结果
    formatted_result = "# 🔥🔥🔥综合搜索结果\n\n"

    formatted_result += "## 🔥🔥🔥本地检索结果\n"
    formatted_result += format_response(local_result.response) + "\n\n"

    formatted_result += "## 🔥🔥🔥全局检索结果\n"
    formatted_result += format_response(global_result.response) + "\n\n"

    formatted_result += "## 🔥🔥🔥Tavily 搜索结果\n"
    # formatted_result += tavily_result + "\n\n"

    return formatted_result


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    try:
        logger.info(f"收到聊天完成请求: {request}")
        prompt = request.messages[-1].content
        logger.info(f"处理提示: {prompt}")
        conversation_turns = [
            {"role": "system", "content": "你是湖南平安医械科技有限公司的智能助手"}
        ]
        # 判断 request.messages 的长度是否大于 20，如果大于 20，则取最后 20 个元素
        if len(request.messages) > 21:
            messages_to_add = request.messages[-21:]
        else:
            messages_to_add = request.messages
        conversation_turns += [
            {"role": message.role, "content": message.content}
            for message in messages_to_add
        ]
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
        if request.stream:
            async def event_stream():
                try:
                    async for response in local_search_engine.astream_search(query=prompt, messages=conversation_turns):
                        if isinstance(response, str):
                            yield f"data: {json.dumps(build_response(chunk_id, request.model, response, None))}\n\n"
                except Exception as e:
                    logger.error(f"Error in event_stream: {str(e)}")
                finally:
                    final_chunk = build_response(chunk_id, request.model, None, "stop")
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"

        else:
            result = await local_search_engine.asearch(query=prompt, messages=conversation_turns)
            formatted_response = format_response(result.response)
            logger.info(f"格式化的搜索结果: {formatted_response}")

            async def event_stream():
                lines = formatted_response.split('\n')
                try:
                    for i, line in enumerate(lines):
                        yield f"data: {json.dumps(build_response(chunk_id, request.model, line, None))}\n\n"
                        await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"Error in event_stream: {str(e)}")
                finally:
                    final_chunk = build_response(chunk_id, request.model, None, "stop")
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"处理聊天完成时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
async def list_models():
    """
    返回可用模型列表
    """
    logger.info("收到模型列表请求")
    current_time = int(time.time())
    models = [
        {"id": "graphrag-www_hnpamd_com_1", "object": "model", "created": current_time - 100000, "owned_by": "graphrag"}
    ]
    response = {
        "object": "list",
        "data": models
    }
    logger.info(f"发送模型列表: {response}")
    return JSONResponse(content=response)


# 拼接返回json
def build_response(chunk_id: object, model: object, line: object, reason: object) -> object:
    if line:
        content = {"content": line}
    else:
        content = {}
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": content,
                "finish_reason": reason
            }
        ]
    }
    return chunk


if __name__ == "__main__":
    import uvicorn

    logger.info(f"在端口 {PORT} 上启动服务器")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
