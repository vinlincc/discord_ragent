from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core import Settings
from llama_index.core.postprocessor import FixedRecencyPostprocessor

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.schema import TextNode, QueryBundle
from llama_index.core.vector_stores.types import (
    MetadataFilter,
    MetadataFilters,
    FilterOperator,
)
from llama_index.core import set_global_handler
import qdrant_client
from qdrant_client.models import CollectionConfig, OptimizersConfig

import settings
from models import Message
from prompts import prompt

import os
from datetime import datetime
import pickle
from pathlib import Path

set_global_handler("simple")

# initialize qdrant client
qd_client = qdrant_client.QdrantClient(
  url=settings.QDRANT_URL,
  api_key=settings.QDRANT_API_KEY
)

qd_collection = 'discord_llamabot'

logger = settings.logging.getLogger("bot")
# embed_model = GeminiEmbedding()
persist_dir = "./.persist"

messages_path = Path(persist_dir + "/messages.pkl")
listening_path = Path(persist_dir + "/listening.pkl")

messages_path.parent.mkdir(parents=True, exist_ok=True)

use_openai = bool(os.environ.get("USE_OPENAI", False))
use_cohere = bool(os.environ.get("USE_COHERE", False))

def persist_listening():
  global listening

  # print(listening)
  with open(listening_path, 'wb') as file:
    pickle.dump(listening, file)


def persist_messages():
  global messages

  # print(messages)
  with open(messages_path, 'wb') as file:
    pickle.dump(messages, file)
# print(use_openai)

# if os.environ.get("GOOGLE_API_KEY", None):
if use_openai:
  from llama_index.llms.openai import OpenAI
  from llama_index.embeddings.openai import OpenAIEmbedding
  print("Using GPT-4")
  llm=OpenAI(
    model="gpt-4-0125-preview",
  )
  embed_model = OpenAIEmbedding(model="text-embedding-3-small")
elif use_cohere:
  from llama_index.llms import Cohere
  print("Using Cohere")
  llm=Cohere(api_key=os.environ.get('COHERE_KEY'))
else:
  from llama_index.llms.gemini import Gemini
  print("Using Gemini Pro")
  llm=Gemini()

vector_store = QdrantVectorStore(client=qd_client,
                                collection_name=qd_collection)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

Settings.llm = llm
Settings.embed_model = embed_model


index = VectorStoreIndex([],
               storage_context=storage_context,
                         embed_model=embed_model)

def remember_message(message, save_only_message):
  when = message.created_at
  who=message.author
  msg_content = message.content

  # print(message)

  logger.info(
  f"Remembering new message \"{msg_content}\" from {who} on channel "
  f"{message.channel.name} at {datetime.now().strftime('%m-%d-%Y %H:%M:%S')}"
  )

  msg_str = f"[{when.strftime('%m-%d-%Y %H:%M:%S')}] - @{who} on #[{str(message.channel)[:15]}]: `{msg_content}`"

  if not save_only_message:
    node = TextNode(
      text=msg_str,
      metadata={
        'author': str(who),
        'posted_at': str(when),
        'channel_id': message.channel.id,
        'guild_id': message.guild.id
      },
      excluded_llm_metadata_keys=['author', 'posted_at', 'channel_id', 'guild_id'],
      excluded_embed_metadata_keys=['author', 'posted_at', 'channel_id', 'guild_id'],
    )

    index.insert_nodes([node])

  if not messages.get(message.guild.id, None):
    messages[message.guild.id] = []
  messages[message.guild.id].append(Message(
    is_in_thread=str(message.channel.type) == 'public_thread',
    posted_at=when,
    author=str(who),
    message_str=msg_str,
    channel_id=message.channel.id,
    just_msg=message.content
  ))
  persist_messages()

async def answer_query(query, ctx, bot):
  channel_id = ctx.channel.id
  thread_messages = [
    msg.message_str for msg in messages.get(ctx.guild.id, []) if msg.channel_id==channel_id
  ][-1*settings.LAST_N_MESSAGES:-1]
  partially_formatted_prompt = prompt.partial_format(
    replies="\n".join(thread_messages),
    user_asking=str(ctx.author),
    bot_name=str(bot.user)
  )

  filters = MetadataFilters(
    filters=[
      MetadataFilter(
        key="guild_id", operator=FilterOperator.EQ, value=ctx.guild.id
      ),
      MetadataFilter(
        key="author", operator=FilterOperator.NE, value=str(bot.user)
      ),
    ]
  )

  postprocessor = FixedRecencyPostprocessor(
      top_k=8, 
      date_key="posted_at", # the key in the metadata to find the date
      # service_context=service_context
  )
  query_engine = index.as_query_engine(
    # service_context=service_context,
    filters=filters,
    similarity_top_k=8,
    node_postprocessors=[postprocessor])
  query_engine.update_prompts(
      {"response_synthesizer:text_qa_template": partially_formatted_prompt}
  )

  replies_query = [
    msg.just_msg for msg in messages.get(ctx.guild.id, []) if msg.channel_id==channel_id
  ][-1*settings.LAST_N_MESSAGES:-1]
  replies_query.append(query)

  # print(replies_query)
  return query_engine.query(QueryBundle(
    query_str=query,
    custom_embedding_strs=replies_query
  ))

def forget_all_index(ctx):
  from qdrant_client.http import models as rest

  global qd_client

  try:
    messages.pop(ctx.guild.id)
    listening.pop(ctx.guild.id)
  except KeyError:
    pass
  persist_messages()
  persist_listening()


  qd_client.delete(
      collection_name=qd_collection,
      points_selector=rest.Filter(
        must=[
          rest.FieldCondition(
              key="guild_id", match=rest.MatchValue(value=ctx.guild.id)
          )
        ]
      ),
  )