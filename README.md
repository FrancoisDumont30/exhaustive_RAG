# Exhaustive RAG

A RAG (Retrieval-Augmented Generation) app for long contractual documents (construction contracts), designed to give **complete** answers rather than the most similar passages only.
Stack: Mistral LLM (structured output, OCR, prompting),  
LlamaIndex (metadata, reranking, vector storage), Streamlit.  

### Disclaimer
There is currently a bug in the LlamaIndex library.
You can find how to fix it here:
[My fix](https://github.com/run-llama/llama_index/pull/21126)

### .env
```
MISTRAL_API_KEY="your_mistral_api_key"
```
### Run the app
```bash
streamlit run app.py
```
### In this repo
[App screenshots](./screens/)  
[RAG: how it works and the exhaustiveness problem](RAG_limit.md)
