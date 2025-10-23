
from dotenv import load_dotenv
import streamlit as st
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA, ConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain_community.embeddings import SentenceTransformerEmbeddings
from typing import List, Optional 
from langchain.memory import ConversationBufferMemory
import os
load_dotenv()

api_key = os.getenv("api_key")
# --- Hàm helper để lưu các chunks ---
def save_chunks_to_files(chunks: List[str], output_dir: str):
    """
    Lưu một danh sách các chunks thành các file .txt riêng biệt.

    Args:
        chunks (List[str]): Danh sách các đoạn văn bản.
        output_dir (str): Đường dẫn thư mục cha để lưu các chunks.
    """
    # Tạo một thư mục con bên trong thư mục output để chứa các chunks
    chunks_dir = os.path.join(output_dir, "chunks_data")
    os.makedirs(chunks_dir, exist_ok=True)

    # Lặp qua từng chunk và lưu thành file
    for i, chunk in enumerate(chunks):
        file_path = os.path.join(chunks_dir, f"chunk_{i+1}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(chunk)
    
    # Thông báo cho người dùng (tùy chọn)
    print(f"Đã lưu {len(chunks)} chunks vào thư mục: {chunks_dir}")


def chunk_text(text: str, output_dir: str = None) -> Optional[List[str]]:
    """
    Hàm 1: Nhận vào văn bản và chia thành các đoạn nhỏ (chunks).
    (Tùy chọn) Lưu các chunks ra file nếu có output_dir.
    """
    if not text or not text.strip():
        st.error("Nội dung đầu vào trống, không thể phân đoạn.")
        return None
        
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150, #chunk overlap để giữ ngữ cảnh
        length_function=len
    )
        # "Recursive" nghĩa là nó sẽ chia theo nhiều mức độ:
        # ưu tiên tách theo ngắt đoạn (newline \n)
        # nếu chưa đủ thì tách theo câu (dấu chấm, dấu chấm hỏi...)
        # nếu vẫn dài quá thì mới tách theo ký tự.
        # Mục tiêu là giữ được cấu trúc tự nhiên của văn bản (tránh cắt câu giữa chừng nếu không cần thiết).


    chunks = text_splitter.split_text(text)
    
    if not chunks:
        st.warning("Too short document after splitting, no chunks created.")
        return None
        
    if output_dir:
        try:
            save_chunks_to_files(chunks, output_dir)
            print(f"Đã lưu {len(chunks)} chunks vào thư mục để kiểm tra.")
        except Exception as e:
            st.warning(f"Không thể lưu các chunks ra file: {e}")
            
    return chunks

#create vector database
def create_vector_store(chunks: List[str]) -> Optional[FAISS]:
    """
    Hàm 2: Nhận vào các chunks, vector hóa và tạo ra một Vector Store (FAISS).
    """
    try:
        embedding_model = SentenceTransformerEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        
        # LangChain sẽ tự động dùng model này để tạo vector store
        vector_store = FAISS.from_texts(texts=chunks, embedding=embedding_model)
        
        
        return vector_store
    except Exception as e:
        st.error(f"Lỗi khi tạo Vector Store: {e}")
        return None

def create_qa_chain(vector_store: FAISS):
    
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            temperature=0.1, # random level in generating text process
            google_api_key=api_key
        )
        
        prompt_template = """
        You are a professional AI recruitment assistant.
        Your mission is to answer questions about the candidate accurately and concisely, based only on the provided CV context below.
        First, identify the language of the user's question. Your final answer must be in the same language as the question.
        If the requested information is not found in the CV, you must state that you cannot find the answer from the CV. Do not make up answers.

        CV Context:
        {context}

        Question: {question}

        Your Answer:
        """
        PROMPT = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=vector_store.as_retriever(search_kwargs={'k': 8}),
            chain_type="stuff", #đưa tất cả vào prompt
            chain_type_kwargs={"prompt": PROMPT}
        )
        
        return qa_chain
        
    except Exception as e:
        st.error(f"Lỗi khi tạo QA Chain: {e}")
        return None


def build_rag_pipeline(cv_text: str, output_dir: str = None):
    # Truyền output_dir vào hàm chunk_text
    chunks = chunk_text(cv_text, output_dir)
    if chunks is None:
        return None
        
    vector_store = create_vector_store(chunks)
    if vector_store is None:
        return None
        
    qa_chain = create_qa_chain(vector_store)
    
    return qa_chain


