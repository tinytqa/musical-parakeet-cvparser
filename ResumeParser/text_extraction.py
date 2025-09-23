import json
import os
from pathlib import Path
from pyexpat import model
from fastapi import HTTPException
from docx import Document
import fitz  # PyMuPDF
import numpy as np
from PIL import Image
import io
from paddleocr import PaddleOCR
from text_processing import process_text_ocr   
from prompt import post_parse_cv, prompt_to_parse_cv
from PyPDF2 import PdfReader
import google.generativeai as genai 
from dotenv import load_dotenv
from langdetect import detect
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


def extract_text_from_file(file_bytes: bytes, filename: str, postprocess: bool = True, to_json: bool = True) -> str:
    path = Path(filename)
    text = ""

    # ----------- DOCX -----------
    if path.suffix.lower() == ".docx":
        doc = Document(io.BytesIO(file_bytes))
        parts = []

        # Đọc tất cả paragraphs ngoài bảng
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text.strip())

        # Đọc thêm nội dung trong bảng
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    cell_text = " ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                    if cell_text:
                        row_text.append(cell_text)
                if row_text:
                    parts.append(" | ".join(row_text))  # nối các ô trong cùng 1 hàng

        formatted_text = "\n".join(parts)

        # Lưu ra file txt
    
        text = formatted_text

    # ----------- PDF -----------
    elif path.suffix.lower() == ".pdf":
        try:
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            
            for page in pdf_doc:
                page_text = page.get_text("text").strip()

                if page_text:
                    text += page_text + "\n"
                    
                else:
                    # PDF scan → OCR
                    ocr = easyocr.Reader(['vi'])
                    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                    # img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    pre_img = preprocess_for_easyocr(img)
                    
                    try:
                        results = ocr.readtext(pre_img, detail=0, paragraph=True)
                        print("OCR raw results:", results)
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")

                    page_ocr_text = []

                    # if results:
                    #     if hasattr(results, "rec_texts") and hasattr(results, "rec_scores"):
                    #         for txt, score in zip(results.rec_texts, results.rec_scores):
                    #             if score > 0.6:
                    #                 page_ocr_text.append(txt)
                    #     elif isinstance(results, list):
                    #         for res in results:
                    #             if isinstance(res, dict) and "rec_texts" in res and "rec_scores" in res:
                    #                 for txt, score in zip(res["rec_texts"], res["rec_scores"]):
                    #                     if score > 0.6:
                    #                         page_ocr_text.append(txt)
                    if results:
                        # for res in results:
                        #     # res = (bbox, text, confidence)
                        #     if len(res) >= 3:
                        #         text_rec, score = res[1], res[2]
                        #         if score > 0.6:  # confidence threshold
                        #             page_ocr_text.append(text_rec)
                        text += "\n".join(results) + "\n"
                    # if page_ocr_text:
                    #     text += "\n".join(page_ocr_text) + "\n"

                    # if page_ocr_text:
                    #     text += "\n".join(page_ocr_text) + "\n"

            print(text)
            pdf_doc.close()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing PDF file: {e}")

    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Only DOCX and PDF are supported.")

    # ----------- Postprocess -----------
    text = text.strip()
    if postprocess:
        try:
            text = process_text_ocr(text)   # hàm xử lý OCR của bạn
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM postprocess failed: {e}")
    
    # ----------- Lưu ra file TXT -----------
    # folder_name = "cv"
    # output_dir = os.path.join("output", folder_name)
    # os.makedirs(output_dir, exist_ok=True)

    # output_txt_path = os.path.join(output_dir, f"{path.stem}.txt")
    # with open(output_txt_path, "w", encoding="utf-8") as f:
    #     f.write(text)

    
    # ----------- Chuyển sang JSON + Lưu file -----------
    if to_json:
        try:
            prompt = prompt_to_parse_cv(text)
            response = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)
            
            parsed_json = post_parse_cv(response.text)
            #print (parsed_json)
            return parsed_json
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM JSON parse failed: {e}")

    return text




