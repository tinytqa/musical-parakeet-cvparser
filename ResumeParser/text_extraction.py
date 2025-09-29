import json
import os
from pathlib import Path
from pyexpat import model
import tempfile
from fastapi import HTTPException
from docx import Document
import fitz  # PyMuPDF
from docx2pdf import convert
import numpy as np
from PIL import Image
import io
from text_processing import process_text_ocr   
from prompt import post_parse_cv, prompt_to_parse_cv
from PyPDF2 import PdfReader
import google.generativeai as genai 
from dotenv import load_dotenv
import easyocr

load_dotenv()

api_key = os.getenv("api_key")

genai.configure(api_key=api_key)

import cv2

def preprocess_for_easyocr(pil_img):
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Resize lớn hơn để OCR dễ đọc
    scale = 2
    resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

    # Không dùng threshold cứng, chỉ normalize độ sáng
    norm = cv2.normalize(resized, None, 0, 255, cv2.NORM_MINMAX)

    return norm

def convert_docx_to_pdf(file_bytes):
    # Tạo file tạm docx
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
        tmp_docx.write(file_bytes)
        tmp_docx_path = tmp_docx.name

    tmp_pdf_path = tmp_docx_path.replace(".docx", ".pdf")

    # Chuyển đổi
    convert(tmp_docx_path, tmp_pdf_path)

    # Đọc pdf ra bytes
    with open(tmp_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # Cleanup thủ công
    try:
        os.remove(tmp_docx_path)
        os.remove(tmp_pdf_path)
    except Exception as e:
        print("Cleanup error:", e)

    return pdf_bytes

def extract_text_from_file(file_bytes: bytes, filename: str, postprocess: bool = True, to_json: bool = True) -> str:
    path = Path(filename)
    text = ""

    # ----------- DOCX -> convert sang PDF bytes -----------
    if path.suffix.lower() == ".docx":
        file_bytes = convert_docx_to_pdf(file_bytes)  # nhận về pdf_bytes
        file_type = "pdf"
    else:
        file_type = path.suffix.lower().lstrip(".")

    # ----------- PDF xử lý -----------
    if file_type == "pdf":
        try:
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            ocr = easyocr.Reader(['vi'])  # init 1 lần duy nhất

            for page in pdf_doc:
                page_text = page.get_text("text").strip()
                if page_text:
                    text += page_text + "\n"
                else:
                    # PDF scan → OCR
                    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    pre_img = preprocess_for_easyocr(img)

                    try:
                        results = ocr.readtext(pre_img, detail=0, paragraph=True)
                        print("OCR raw results:", results)
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")

                    if results:
                        text += "\n".join(results) + "\n"

            pdf_doc.close()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing PDF file: {e}")

    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Only DOCX and PDF are supported.")

    # ----------- Postprocess -----------
    text = text.strip()
    if postprocess:
        try:
            text = process_text_ocr(text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM postprocess failed: {e}")
   # ----------- Save raw text vào folder output theo tên CV -----------

    cv_name = path.stem  
    save_dir = Path("output") / cv_name
    save_dir.mkdir(parents=True, exist_ok=True)

    raw_text_path = save_dir / "raw_text.md"
    try:
        with open(raw_text_path, "w", encoding="utf-8") as f:
            f.write("# Raw Text Extracted from CV\n\n")
            f.write("```\n")
            f.write(text.strip())
            f.write("\n```")
        print(f"✅ Raw CV text saved to {raw_text_path}")
    except Exception as e:
        print("⚠️ Could not save raw text:", e)


    # ----------- Parse JSON bằng LLM -----------
    if to_json:
        try:
            prompt = prompt_to_parse_cv(text)
            response = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)

            parsed_json = post_parse_cv(response.text)
            print(parsed_json)
            return parsed_json
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM JSON parse failed: {e}")

    return text
