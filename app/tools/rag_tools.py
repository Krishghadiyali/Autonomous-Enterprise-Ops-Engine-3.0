import os
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# 1. Initialize local HuggingFace embeddings (No GOOGLE_API_KEY required)
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# 2. Safely locate your chroma_db folder at the project root
db_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "chroma_db"
)

# 3. Connect to the 'company_policies' collection in ChromaDB
vectorstore = Chroma(
    collection_name="company_policies",
    embedding_function=embeddings,
    persist_directory=db_path,
)


@tool
def search_company_policies(query: str) -> str:
    """
    Search company policies for relevant information based on the given query.
    """
    try:
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
        retrieved_docs = retriever.invoke(query)

        if retrieved_docs:
            formatted_results = "\n\n".join(
                [
                    f"Document {i + 1}:\n{doc.page_content}"
                    for i, doc in enumerate(retrieved_docs)
                ]
            )
            return f"Found relevant policy information:\n\n{formatted_results}"
        else:
            return "No relevant policy information found for the given query."

    except Exception as e:
        return f"Error searching policies: {str(e)}"