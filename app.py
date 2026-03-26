import streamlit as st
import os
from pathlib import Path
from services.llama_index_services import ingest, llama_query

# Page title
st.title("Application RAG avec Streamlit")

# Vector repository
vectors_dir = "vectors"
os.makedirs(vectors_dir, exist_ok=True)

# PDF uploading
st.header("Charger un PDF")
uploaded_file = st.file_uploader("Choisir un PDF", type="pdf")

if uploaded_file:
    file_path = os.path.join("temp", uploaded_file.name)
    os.makedirs("temp", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success(f"Fichier {uploaded_file.name} chargé avec succès.")

    # Vector storing
    target_dir = os.path.join(vectors_dir, Path(uploaded_file.name).stem)
    if st.button("Vectoriser le PDF"):
        ingest(file_path, target_dir)
        os.remove(file_path)
        st.success(f"PDF vectorisé et sauvegardé dans {target_dir}/index/.")

# Load stored vectors
st.header("Sélectionner un PDF vectorisé")
vectorized_docs = [d for d in os.listdir(vectors_dir)
                   if os.path.isdir(os.path.join(vectors_dir, d))]
selected_doc = st.selectbox("Choisir un PDF vectorisé", vectorized_docs)

# Question
st.header("Poser une question")
question = st.text_input("Entrez votre question ici")

col1, col2 = st.columns(2)

with col1 :
    gen_button = st.button("Générer la réponse")

with col2 :
    if question and not gen_button :
        st.info('Vous devez cliquez sur "Générer la réponse"')

if gen_button:
    if not vectorized_docs:
        st.error("Aucun document vectorisé disponible.")
    else:
        target_dir = os.path.join(vectors_dir, selected_doc)
        response = llama_query(target_dir, question)
        st.write("Réponse :")
        
        # print txt only
        if isinstance(response, str):
            st.write(response)
        else:
            st.write(response.response)