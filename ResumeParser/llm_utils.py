import google.generativeai as genai
import streamlit as st
from api_key import api_key

def call_gemini(prompt: str) -> str:
    """Gọi Gemini 2.5 để sinh text từ prompt."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Gemini API error: {e}")
        return ""