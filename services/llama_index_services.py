# --- import
import os
from dotenv import load_dotenv

from llama_index.core import Document
from llama_index.core import VectorStoreIndex
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core import Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import LLMRerank
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter, FilterCondition

from llama_index.embeddings.mistralai import MistralAIEmbedding
from llama_index.llms.mistralai import MistralAI

# own import
from services.chapter_services import doc_to_chapter


def ingest(file: str, directory: str) -> None:
    """
    Main function to ingest and index documents.

    Args:
        file: Unique identifier for the document or project.
        directory: Path to the directory containing files to process or where to save results.
    """

    # API Mistral key
    load_dotenv()
    API_KEY = os.getenv('MISTRAL_API_KEY')

    # get the chapters
    chapter_txt_list = doc_to_chapter(file, directory)

    # store the chatpers
    document = []

    # Create a Document class object for each chapter
    for i in range(len(chapter_txt_list)):
        document.append(
            Document(
                text=f"{chapter_txt_list[i]}",
                doc_id=f"doc_{i}",
                metadata={
                    "num_chapitre": f"{i}"})
                        )

    # chapter chunking
    node_parser = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    nodes = node_parser.get_nodes_from_documents(document)

    # id formatting
    custom_id = 0
    for node in nodes:
        node.node_id = f"node_{custom_id}"
        custom_id += 1

    # --- Vector Store ---
    # Embedding
    model_name = "mistral-embed"
    embed_model = MistralAIEmbedding(model_name=model_name, api_key=API_KEY)
    Settings.embed_model = embed_model

    # Vector Store Index
    index = VectorStoreIndex(nodes, embed_model=embed_model)

    # LLM
    Settings.llm = MistralAI(model="mistral-large-latest", api_key=API_KEY, temperature=0.0, max_tokens=30000)

    # --- Store the index ---
    index.storage_context.persist(persist_dir=f'{directory}/index')


def llama_query(directory : str, Question_User : str) -> str :
    """
    Queries a pre-built vector index with a user question and returns the answer.

    Args:
        directory: Path to the directory containing the persisted index.
        Question_User: User's query in natural language.

    Returns:
        Answer to the query as a string.

    Process:
        1. Loads the persisted vector index.
        2. Retrieves relevant vectors and filters by chapter metadata.
        3. Reranks results using Mistral's reranker.
        4. Returns the answer based on the top reranked nodes.
    """

    # API Mistral key
    load_dotenv()
    API_KEY = os.getenv('MISTRAL_API_KEY')

    # Settings
    Settings.llm = MistralAI(model="mistral-large-latest", api_key=API_KEY, temperature=0.0, max_tokens=30000)
    Settings.embed_model = MistralAIEmbedding(model_name="mistral-embed", api_key=API_KEY)

    # Vector store index loading
    storage_context = StorageContext.from_defaults(persist_dir=f'{directory}/index/')
    index = load_index_from_storage(storage_context)

    query = Question_User

    # Vector retrieval 1
    meta_retriever = index.as_retriever(similarity_top_k=12)
    meta_retrieved = meta_retriever.retrieve(query)

    # store the chapter numbers
    meta_filter = []

    for vecteur in meta_retrieved :
        resultat = vecteur.metadata['num_chapitre']

        if resultat not in meta_filter :
            meta_filter.append(resultat)

    # Index filtering from chapter number 
    filters = MetadataFilters(
    filters=[
        ExactMatchFilter(key="num_chapitre", value=value)
        for value in meta_filter],
    condition=FilterCondition.OR)

    filtered_index = index.as_retriever(filters=filters, similarity_top_k= 500)
    filtered_retriever = filtered_index.retrieve(query)


    # Mistral reranking
    postprocessor = LLMRerank()
    Mistral_rerank = postprocessor.postprocess_nodes(filtered_retriever, query_str=query)

    # Reranked nodes
    rerank_list = []
    for ele in Mistral_rerank :
        rerank_list.append(ele.id_)

    # Generate a response with reranked nodes.
    ranked_nodes = index.docstore.get_nodes(rerank_list)
    ranked_index = VectorStoreIndex.from_documents(ranked_nodes)
    ma_reponse = ranked_index.as_query_engine().query(query)

    return ma_reponse